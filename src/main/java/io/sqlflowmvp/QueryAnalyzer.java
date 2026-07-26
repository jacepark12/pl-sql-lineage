package io.sqlflowmvp;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class QueryAnalyzer {
    private static final Pattern SOURCE_PATTERN = Pattern.compile(
        "(?is)\\b(?:FROM|JOIN)\\s+([\\w$#.\"]+)"
            + "(?:\\s+(?:AS\\s+)?(?!JOIN\\b|ON\\b|WHERE\\b|GROUP\\b|HAVING\\b|ORDER\\b|UNION\\b)"
            + "([\\w$#\"]+))?");
    private static final Pattern QUALIFIED_COLUMN = Pattern.compile(
        "(?i)([A-Za-z_][\\w$#]*|\"[^\"]+\")\\s*\\.\\s*([A-Za-z_][\\w$#]*|\"[^\"]+\")");
    private static final Pattern TOKEN = Pattern.compile("(?i):?[A-Za-z_][\\w$#]*");
    private static final Pattern EXPLICIT_ALIAS = Pattern.compile(
        "(?is)^(.*)\\s+AS\\s+([A-Za-z_][\\w$#]*|\"[^\"]+\")\\s*$");
    private static final Pattern IMPLICIT_ALIAS = Pattern.compile(
        "(?is)^(.*\\S)\\s+([A-Za-z_][\\w$#]*|\"[^\"]+\")\\s*$");
    private static final Pattern AGGREGATE = Pattern.compile("(?i)\\b(?:SUM|COUNT|AVG|MIN|MAX)\\s*\\(");
    private static final Set<String> KEYWORDS = Set.of(
        "ALL", "AND", "AS", "ASC", "BETWEEN", "BY", "CASE", "CONNECT", "CURRENT",
        "DATE", "DESC", "DISTINCT", "ELSE", "END", "FALSE", "FROM", "GROUP", "HAVING",
        "IN", "IS", "JOIN", "LEFT", "LIKE", "NOT", "NULL", "ON", "OR", "ORDER", "OUTER",
        "OVER", "PARTITION", "RIGHT", "SELECT", "SYSDATE", "THEN", "TRUE", "UNION",
        "WHEN", "WHERE"
    );

    private final SchemaCatalog catalog;
    private final Map<String, String> symbols;

    QueryAnalyzer(SchemaCatalog catalog, Map<String, String> symbols) {
        this.catalog = catalog;
        this.symbols = new LinkedHashMap<>();
        symbols.forEach((name, id) -> this.symbols.put(normalizeKey(name), id));
    }

    QueryInfo analyze(String query) {
        return analyze(query, new LinkedHashMap<>());
    }

    ResolvedExpression resolveAgainstRelations(String expression, Map<String, SchemaCatalog.Relation> aliases) {
        var bindings = new LinkedHashMap<String, SourceBinding>();
        aliases.forEach((alias, relation) ->
            bindings.put(normalizeKey(alias), new SourceBinding(relation, null)));
        return resolveExpression(expression, bindings);
    }

    private QueryInfo analyze(String query, Map<String, QueryInfo> inheritedCtes) {
        var cteResult = parseCtes(query, inheritedCtes);
        var sql = cteResult.outerQuery();
        var ctes = cteResult.ctes();
        var selectIndex = SqlText.topLevelKeyword(sql, "SELECT", 0);
        var fromIndex = SqlText.topLevelKeyword(sql, "FROM", Math.max(0, selectIndex + 6));
        if (selectIndex < 0) {
            return QueryInfo.empty();
        }

        var selectEnd = fromIndex < 0 ? sql.length() : fromIndex;
        var selectList = sql.substring(selectIndex + 6, selectEnd);
        var whereIndex = fromIndex < 0 ? -1 : SqlText.topLevelKeyword(sql, "WHERE", fromIndex + 4);
        var groupIndex = fromIndex < 0 ? -1 : SqlText.topLevelKeyword(sql, "GROUP BY", fromIndex + 4);
        var havingIndex = fromIndex < 0 ? -1 : SqlText.topLevelKeyword(sql, "HAVING", fromIndex + 4);
        var orderIndex = fromIndex < 0 ? -1 : SqlText.topLevelKeyword(sql, "ORDER BY", fromIndex + 4);
        var unionIndex = fromIndex < 0 ? -1 : SqlText.topLevelKeyword(sql, "UNION", fromIndex + 4);

        var fromEnd = minimumPositive(sql.length(), whereIndex, groupIndex, havingIndex, orderIndex, unionIndex);
        var fromClause = fromIndex < 0 ? "" : sql.substring(fromIndex, fromEnd);
        var bindings = parseBindings(fromClause, ctes);
        var outputs = parseOutputs(selectList, bindings);
        var joins = parseJoinConditions(fromClause, bindings);
        var where = parseWhereConditions(sql, whereIndex, groupIndex, havingIndex, orderIndex, unionIndex, bindings);
        bindings.values().stream()
            .map(SourceBinding::cte)
            .filter(cte -> cte != null)
            .distinct()
            .forEach(cte -> {
                joins.addAll(cte.joins());
                where.addAll(cte.where());
            });
        var groupSources = parseGroupSources(sql, groupIndex, havingIndex, orderIndex, unionIndex, bindings);
        return new QueryInfo(outputs, joins, where, groupSources);
    }

    private CteParse parseCtes(String query, Map<String, QueryInfo> inheritedCtes) {
        var firstKeyword = firstKeyword(query);
        if (!firstKeyword.equals("WITH")) {
            return new CteParse(query, new LinkedHashMap<>(inheritedCtes));
        }

        var ctes = new LinkedHashMap<>(inheritedCtes);
        var masked = SqlText.maskLiteralsAndComments(query);
        var cursor = skipWhitespace(masked, masked.toUpperCase(Locale.ROOT).indexOf("WITH") + 4);
        while (cursor < masked.length()) {
            var name = SqlText.identifierAt(masked, cursor);
            if (name.isBlank()) {
                break;
            }
            cursor = skipWhitespace(masked, cursor + name.length());
            if (cursor < masked.length() && masked.charAt(cursor) == '(') {
                var closeColumns = SqlText.matchingParen(masked, cursor);
                if (closeColumns < 0) {
                    break;
                }
                cursor = skipWhitespace(masked, closeColumns + 1);
            }
            if (!wordAt(masked, cursor, "AS")) {
                break;
            }
            cursor = skipWhitespace(masked, cursor + 2);
            if (cursor >= masked.length() || masked.charAt(cursor) != '(') {
                break;
            }
            var close = SqlText.matchingParen(masked, cursor);
            if (close < 0) {
                break;
            }
            var cteQuery = query.substring(cursor + 1, close);
            ctes.put(normalizeKey(name), analyze(cteQuery, ctes));
            cursor = skipWhitespace(masked, close + 1);
            if (cursor >= masked.length() || masked.charAt(cursor) != ',') {
                return new CteParse(query.substring(cursor), ctes);
            }
            cursor = skipWhitespace(masked, cursor + 1);
        }
        return new CteParse(query, ctes);
    }

    private Map<String, SourceBinding> parseBindings(String fromClause, Map<String, QueryInfo> ctes) {
        var bindings = new LinkedHashMap<String, SourceBinding>();
        var matcher = SOURCE_PATTERN.matcher(SqlText.maskLiteralsAndComments(fromClause));
        while (matcher.find()) {
            var sourceName = NameUtil.normalize(matcher.group(1));
            var alias = matcher.group(2) == null ? lastNamePart(sourceName) : NameUtil.normalize(matcher.group(2));
            var cte = ctes.get(normalizeKey(sourceName));
            if (cte != null) {
                bindings.put(normalizeKey(alias), new SourceBinding(null, cte));
                bindings.putIfAbsent(normalizeKey(sourceName), new SourceBinding(null, cte));
            } else {
                var relation = catalog.find(sourceName);
                if (relation == null) {
                    relation = catalog.ensureTable(sourceName);
                }
                bindings.put(normalizeKey(alias), new SourceBinding(relation, null));
                bindings.putIfAbsent(normalizeKey(sourceName), new SourceBinding(relation, null));
            }
        }
        return bindings;
    }

    private List<QueryOutput> parseOutputs(String selectList, Map<String, SourceBinding> bindings) {
        var outputs = new ArrayList<QueryOutput>();
        var ordinal = 1;
        for (var rawItem : SqlText.splitTopLevel(selectList, ',')) {
            var item = SqlText.normalizeWhitespace(rawItem);
            if (item.isBlank()) {
                continue;
            }
            var aliasAndExpression = splitAlias(item);
            var expression = aliasAndExpression.expression();
            var outputName = aliasAndExpression.alias();
            if (outputName == null) {
                outputName = deriveOutputName(expression, ordinal);
            }
            var resolved = resolveExpression(expression, bindings);
            var expanded = AGGREGATE.matcher(expression).find()
                ? expandCteExpression(expression, bindings)
                : expression;
            outputs.add(new QueryOutput(
                NameUtil.normalize(outputName),
                expression,
                SqlText.normalizeWhitespace(expanded),
                resolved.sources(),
                AGGREGATE.matcher(expression).find()));
            ordinal++;
        }
        return outputs;
    }

    private List<Condition> parseJoinConditions(
        String fromClause,
        Map<String, SourceBinding> bindings
    ) {
        var conditions = new ArrayList<Condition>();
        var cursor = 0;
        while (true) {
            var onIndex = SqlText.topLevelKeyword(fromClause, "ON", cursor);
            if (onIndex < 0) {
                break;
            }
            var nextJoin = SqlText.topLevelKeyword(fromClause, "JOIN", onIndex + 2);
            var end = nextJoin < 0 ? fromClause.length() : nextJoin;
            var expression = stripOuterParens(SqlText.normalizeWhitespace(fromClause.substring(onIndex + 2, end)));
            var resolved = resolveExpression(expression, bindings);
            if (!resolved.sources().isEmpty()) {
                conditions.add(new Condition(expression, resolved.sources()));
            }
            cursor = end;
        }
        return conditions;
    }

    private List<Condition> parseWhereConditions(
        String sql,
        int whereIndex,
        int groupIndex,
        int havingIndex,
        int orderIndex,
        int unionIndex,
        Map<String, SourceBinding> bindings
    ) {
        var conditions = new ArrayList<Condition>();
        if (whereIndex < 0) {
            return conditions;
        }
        var end = minimumPositive(sql.length(), positiveAfter(groupIndex, whereIndex),
            positiveAfter(havingIndex, whereIndex), positiveAfter(orderIndex, whereIndex),
            positiveAfter(unionIndex, whereIndex));
        var clause = sql.substring(whereIndex + 5, end);
        for (var rawCondition : SqlText.splitTopLevelAnd(clause)) {
            var expression = stripOuterParens(SqlText.normalizeWhitespace(rawCondition));
            var resolved = resolveExpression(expression, bindings);
            if (!resolved.sources().isEmpty()) {
                conditions.add(new Condition(expression, resolved.sources()));
            }
        }
        return conditions;
    }

    private Set<String> parseGroupSources(
        String sql,
        int groupIndex,
        int havingIndex,
        int orderIndex,
        int unionIndex,
        Map<String, SourceBinding> bindings
    ) {
        var sources = new LinkedHashSet<String>();
        if (groupIndex < 0) {
            return sources;
        }
        var end = minimumPositive(sql.length(), positiveAfter(havingIndex, groupIndex),
            positiveAfter(orderIndex, groupIndex), positiveAfter(unionIndex, groupIndex));
        var clause = sql.substring(groupIndex + "GROUP BY".length(), end);
        for (var expression : SqlText.splitTopLevel(clause, ',')) {
            sources.addAll(resolveExpression(expression, bindings).sources());
        }
        return sources;
    }

    private ResolvedExpression resolveExpression(String expression, Map<String, SourceBinding> bindings) {
        var sources = new LinkedHashSet<String>();
        var masked = SqlText.maskLiteralsAndComments(expression);
        var covered = new boolean[masked.length()];
        var qualified = QUALIFIED_COLUMN.matcher(masked);
        while (qualified.find()) {
            markCovered(covered, qualified.start(), qualified.end());
            var binding = bindings.get(normalizeKey(qualified.group(1)));
            if (binding != null) {
                sources.addAll(resolveColumn(binding, qualified.group(2)));
            }
        }

        var tokens = TOKEN.matcher(masked);
        while (tokens.find()) {
            if (isCovered(covered, tokens.start(), tokens.end())) {
                continue;
            }
            var token = tokens.group();
            var key = normalizeKey(token);
            if (symbols.containsKey(key)) {
                sources.add(symbols.get(key));
                continue;
            }
            var bareToken = token.startsWith(":") ? token.substring(1) : token;
            if (token.startsWith(":") && symbols.containsKey(normalizeKey(bareToken))) {
                sources.add(symbols.get(normalizeKey(bareToken)));
                continue;
            }
            if (KEYWORDS.contains(bareToken.toUpperCase(Locale.ROOT)) || followedByParen(masked, tokens.end())) {
                continue;
            }
            sources.addAll(resolveUnqualified(bindings, bareToken));
        }
        return new ResolvedExpression(List.copyOf(sources));
    }

    private List<String> resolveUnqualified(Map<String, SourceBinding> bindings, String columnName) {
        var candidates = new LinkedHashSet<String>();
        var uniqueBindings = new LinkedHashSet<>(bindings.values());
        for (var binding : uniqueBindings) {
            if (binding.relation() != null && catalog.hasColumn(binding.relation(), columnName)) {
                candidates.add(catalog.ensureColumn(binding.relation(), columnName));
            } else if (binding.cte() != null) {
                var output = binding.cte().output(columnName);
                if (output != null) {
                    candidates.addAll(output.sources());
                }
            }
        }
        if (candidates.isEmpty() && uniqueBindings.size() == 1) {
            var only = uniqueBindings.iterator().next();
            if (only.relation() != null) {
                candidates.add(catalog.ensureColumn(only.relation(), columnName));
            }
        }
        return List.copyOf(candidates);
    }

    private List<String> resolveColumn(SourceBinding binding, String columnName) {
        if (binding.relation() != null) {
            return List.of(catalog.ensureColumn(binding.relation(), columnName));
        }
        var output = binding.cte().output(columnName);
        return output == null ? List.of() : output.sources();
    }

    private String expandCteExpression(String expression, Map<String, SourceBinding> bindings) {
        var expanded = expression;
        var uniqueBindings = new LinkedHashSet<>(bindings.entrySet());
        for (var entry : uniqueBindings) {
            var binding = entry.getValue();
            if (binding.cte() == null) {
                continue;
            }
            for (var output : binding.cte().outputs()) {
                var qualifiedPattern = Pattern.compile(
                    "(?i)\\b" + Pattern.quote(entry.getKey()) + "\\s*\\.\\s*"
                        + Pattern.quote(output.name()) + "\\b");
                expanded = qualifiedPattern.matcher(expanded)
                    .replaceAll(Matcher.quoteReplacement(output.expandedExpression()));
            }
        }

        var distinctCtes = bindings.values().stream()
            .filter(binding -> binding.cte() != null)
            .map(SourceBinding::cte)
            .distinct()
            .toList();
        if (distinctCtes.size() == 1) {
            for (var output : distinctCtes.getFirst().outputs()) {
                var unqualifiedPattern = Pattern.compile("(?i)\\b" + Pattern.quote(output.name()) + "\\b");
                expanded = unqualifiedPattern.matcher(expanded)
                    .replaceAll(Matcher.quoteReplacement(output.expandedExpression()));
            }
        }
        return expanded;
    }

    private AliasAndExpression splitAlias(String item) {
        var explicit = EXPLICIT_ALIAS.matcher(item);
        if (explicit.matches()) {
            return new AliasAndExpression(
                SqlText.normalizeWhitespace(explicit.group(1)),
                NameUtil.normalize(explicit.group(2)));
        }
        var implicit = IMPLICIT_ALIAS.matcher(item);
        if (implicit.matches()) {
            var candidate = NameUtil.normalize(implicit.group(2));
            var prefix = SqlText.normalizeWhitespace(implicit.group(1));
            if (!KEYWORDS.contains(candidate) && !prefix.matches("(?i)[\\w$#\".]+")) {
                return new AliasAndExpression(prefix, candidate);
            }
        }
        return new AliasAndExpression(item, null);
    }

    private String deriveOutputName(String expression, int ordinal) {
        var normalized = SqlText.normalizeWhitespace(expression);
        if (normalized.matches("(?i)[\\w$#\".]+")) {
            return lastNamePart(normalized);
        }
        return "EXPR_" + ordinal;
    }

    private String firstKeyword(String query) {
        var masked = SqlText.maskLiteralsAndComments(query).stripLeading();
        var end = 0;
        while (end < masked.length() && Character.isLetter(masked.charAt(end))) {
            end++;
        }
        return masked.substring(0, end).toUpperCase(Locale.ROOT);
    }

    private int skipWhitespace(String value, int start) {
        var cursor = Math.max(0, start);
        while (cursor < value.length() && Character.isWhitespace(value.charAt(cursor))) {
            cursor++;
        }
        return cursor;
    }

    private boolean wordAt(String value, int index, String word) {
        return index >= 0
            && index + word.length() <= value.length()
            && value.regionMatches(true, index, word, 0, word.length())
            && (index == 0 || !SqlText.isIdentifierPart(value.charAt(index - 1)))
            && (index + word.length() == value.length()
                || !SqlText.isIdentifierPart(value.charAt(index + word.length())));
    }

    private static int minimumPositive(int fallback, int... values) {
        var result = fallback;
        for (var value : values) {
            if (value >= 0 && value < result) {
                result = value;
            }
        }
        return result;
    }

    private static int positiveAfter(int value, int boundary) {
        return value > boundary ? value : -1;
    }

    private static String normalizeKey(String name) {
        return NameUtil.idPart(name);
    }

    private static String lastNamePart(String name) {
        var normalized = NameUtil.normalize(name);
        var dot = normalized.lastIndexOf('.');
        return dot < 0 ? normalized : normalized.substring(dot + 1);
    }

    private static String stripOuterParens(String value) {
        var stripped = value.strip();
        while (stripped.startsWith("(") && stripped.endsWith(")")) {
            var close = SqlText.matchingParen(SqlText.maskLiteralsAndComments(stripped), 0);
            if (close != stripped.length() - 1) {
                break;
            }
            stripped = stripped.substring(1, stripped.length() - 1).strip();
        }
        return stripped;
    }

    private static void markCovered(boolean[] covered, int start, int end) {
        for (var i = start; i < end && i < covered.length; i++) {
            covered[i] = true;
        }
    }

    private static boolean isCovered(boolean[] covered, int start, int end) {
        for (var i = start; i < end && i < covered.length; i++) {
            if (covered[i]) {
                return true;
            }
        }
        return false;
    }

    private static boolean followedByParen(String masked, int end) {
        var cursor = end;
        while (cursor < masked.length() && Character.isWhitespace(masked.charAt(cursor))) {
            cursor++;
        }
        return cursor < masked.length() && masked.charAt(cursor) == '(';
    }

    private record SourceBinding(SchemaCatalog.Relation relation, QueryInfo cte) {
    }

    private record CteParse(String outerQuery, Map<String, QueryInfo> ctes) {
    }

    private record AliasAndExpression(String expression, String alias) {
    }

    record ResolvedExpression(List<String> sources) {
    }

    record QueryOutput(
        String name,
        String expression,
        String expandedExpression,
        List<String> sources,
        boolean aggregate
    ) {
    }

    record Condition(String expression, List<String> sources) {
    }

    record QueryInfo(
        List<QueryOutput> outputs,
        List<Condition> joins,
        List<Condition> where,
        Set<String> groupSources
    ) {
        static QueryInfo empty() {
            return new QueryInfo(List.of(), List.of(), List.of(), Set.of());
        }

        QueryOutput output(String name) {
            return outputs.stream()
                .filter(output -> output.name().equalsIgnoreCase(NameUtil.normalize(name)))
                .findFirst()
                .orElse(null);
        }

        QueryOutput aggregateOutput() {
            return outputs.stream().filter(QueryOutput::aggregate).findFirst().orElse(null);
        }
    }
}
