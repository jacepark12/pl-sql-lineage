package io.sqlflowmvp;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

final class OracleLineageAnalyzer {
    private static final Pattern CREATE_TABLE = Pattern.compile(
        "(?is)\\bCREATE\\s+(?:GLOBAL\\s+TEMPORARY\\s+)?TABLE\\s+([\\w$#.\"]+)\\s*\\((.*?)\\)\\s*;");
    private static final Pattern CREATE_VIEW = Pattern.compile(
        "(?is)\\bCREATE\\s+(?:OR\\s+REPLACE\\s+)?(?:FORCE\\s+)?VIEW\\s+([\\w$#.\"]+)"
            + "(?:\\s*\\([^;]*?\\))?\\s+AS\\b");
    private static final Pattern CREATE_PACKAGE = Pattern.compile(
        "(?is)\\bCREATE\\s+(?:OR\\s+REPLACE\\s+)?PACKAGE\\s+(?!BODY\\b)([\\w$#.\"]+)");
    private static final Pattern CREATE_PACKAGE_BODY = Pattern.compile(
        "(?is)\\bCREATE\\s+(?:OR\\s+REPLACE\\s+)?PACKAGE\\s+BODY\\s+([\\w$#.\"]+)");
    private static final Pattern CREATE_PROCEDURE = Pattern.compile(
        "(?is)\\bCREATE\\s+(?:OR\\s+REPLACE\\s+)?PROCEDURE\\s+([\\w$#.\"]+)\\s*(\\()?");
    private static final Pattern CREATE_FUNCTION = Pattern.compile(
        "(?is)\\bCREATE\\s+(?:OR\\s+REPLACE\\s+)?FUNCTION\\s+([\\w$#.\"]+)\\s*(\\()?");
    private static final Pattern CREATE_TRIGGER = Pattern.compile(
        "(?is)\\bCREATE\\s+(?:OR\\s+REPLACE\\s+)?TRIGGER\\s+([\\w$#.\"]+)");
    private static final Pattern SUBPROGRAM_DECLARATION = Pattern.compile(
        "(?is)\\b(PROCEDURE|FUNCTION)\\s+([\\w$#\"]+)\\s*(\\()?");
    private static final Pattern INSERT_START = Pattern.compile(
        "(?is)\\bINSERT\\s+INTO\\s+([\\w$#.\"]+)");
    private static final Pattern MERGE_START = Pattern.compile(
        "(?is)\\bMERGE\\s+INTO\\s+([\\w$#.\"]+)"
            + "(?:\\s+(?!USING\\b)([\\w$#\"]+))?\\s+USING\\s+([\\w$#.\"]+)"
            + "(?:\\s+(?!ON\\b)([\\w$#\"]+))?");
    private static final Pattern UPDATE_START = Pattern.compile(
        "(?is)\\bUPDATE\\s+([\\w$#.\"]+)(?:\\s+(?!SET\\b)([\\w$#\"]+))?\\s+SET\\b");
    private static final Pattern QUALIFIED_CALL = Pattern.compile(
        "(?is)\\b([A-Za-z_][\\w$#]*)\\s*\\.\\s*([A-Za-z_][\\w$#]*)\\s*\\(");
    private static final Pattern ASSIGNMENT = Pattern.compile(
        "(?is)\\b([A-Za-z_][\\w$#]*)\\s*:=");
    private static final Pattern EXECUTE_IMMEDIATE = Pattern.compile("(?is)\\bEXECUTE\\s+IMMEDIATE\\b");
    private static final Pattern SEQUENCE_REFERENCE = Pattern.compile(
        "(?i)\\b[A-Za-z_][\\w$#]*(?:\\.[A-Za-z_][\\w$#]*)*\\.NEXTVAL\\b");
    private static final Pattern BIND_REFERENCE = Pattern.compile("(?i):([A-Za-z_][\\w$#]*)");

    AnalysisResult analyze(String sql) {
        var result = new AnalysisResult();
        var catalog = new SchemaCatalog(result);
        var masked = SqlText.maskLiteralsAndComments(sql);

        inventoryTables(sql, masked, catalog);
        var scopes = inventoryPackagesAndProcedures(sql, masked, result);
        inventoryTriggers(masked, result);
        analyzeViews(sql, masked, catalog, result);
        var mergeRanges = analyzeMerges(sql, masked, catalog, result, scopes);
        analyzeInserts(sql, masked, 0, catalog, result, scopes, Map.of());
        analyzeUpdates(sql, masked, catalog, result, scopes, mergeRanges);
        analyzeProcedureCalls(sql, masked, scopes, result);
        analyzeDynamicSql(sql, masked, catalog, result, scopes);
        return result;
    }

    private void inventoryTables(String sql, String masked, SchemaCatalog catalog) {
        var matcher = CREATE_TABLE.matcher(masked);
        while (matcher.find()) {
            var relation = catalog.ensureTable(matcher.group(1));
            var body = sql.substring(matcher.start(2), matcher.end(2));
            for (var column : parseColumnNames(body)) {
                catalog.ensureColumn(relation, column);
            }
        }
    }

    private List<String> parseColumnNames(String createTableBody) {
        var columns = new ArrayList<String>();
        for (var part : SqlText.splitTopLevel(createTableBody, ',')) {
            var trimmed = part.strip();
            if (trimmed.isEmpty()) {
                continue;
            }
            var firstToken = SqlText.identifierAt(trimmed, 0);
            var keyword = NameUtil.normalize(firstToken);
            if (Set.of("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "SUPPLEMENTAL")
                .contains(keyword)) {
                continue;
            }
            if (!firstToken.isBlank()) {
                columns.add(firstToken);
            }
        }
        return columns;
    }

    private List<ProcedureScope> inventoryPackagesAndProcedures(
        String sql,
        String masked,
        AnalysisResult result
    ) {
        var scopes = new ArrayList<ProcedureScope>();
        var bodyRanges = new ArrayList<Range>();

        var packageMatcher = CREATE_PACKAGE.matcher(masked);
        while (packageMatcher.find()) {
            var packageName = NameUtil.normalize(packageMatcher.group(1));
            result.addObject(NameUtil.packageId(packageName), "package", packageName);
            var end = nextCreateIndex(masked, packageMatcher.end());
            inventoryPackageProcedures(
                sql, masked, packageName, packageMatcher.end(), end < 0 ? sql.length() : end, false, result, scopes);
        }

        var bodyMatcher = CREATE_PACKAGE_BODY.matcher(masked);
        while (bodyMatcher.find()) {
            var packageName = NameUtil.normalize(bodyMatcher.group(1));
            result.addObject(NameUtil.packageId(packageName), "package", packageName);
            var end = nextCreateIndex(masked, bodyMatcher.end());
            var bodyEnd = end < 0 ? sql.length() : end;
            bodyRanges.add(new Range(bodyMatcher.start(), bodyEnd));
            inventoryPackageProcedures(
                sql, masked, packageName, bodyMatcher.end(), bodyEnd, true, result, scopes);
        }

        var standalone = CREATE_PROCEDURE.matcher(masked);
        while (standalone.find()) {
            if (insideAny(standalone.start(), bodyRanges)) {
                continue;
            }
            var procedureName = NameUtil.normalize(standalone.group(1));
            var params = parseDeclarationParameters(sql, masked, standalone.end(1));
            var end = nextCreateIndex(masked, standalone.end());
            var scopeEnd = end < 0 ? sql.length() : end;
            var symbols = registerSubprogram(result, procedureName, "procedure", params);
            scopes.add(new ProcedureScope(
                procedureName, "procedure", standalone.start(), scopeEnd, symbols));
        }

        var standaloneFunction = CREATE_FUNCTION.matcher(masked);
        while (standaloneFunction.find()) {
            if (insideAny(standaloneFunction.start(), bodyRanges)) {
                continue;
            }
            var functionName = NameUtil.normalize(standaloneFunction.group(1));
            var params = parseDeclarationParameters(sql, masked, standaloneFunction.end(1));
            var end = nextCreateIndex(masked, standaloneFunction.end());
            var scopeEnd = end < 0 ? sql.length() : end;
            var symbols = registerSubprogram(result, functionName, "function", params);
            scopes.add(new ProcedureScope(
                functionName, "function", standaloneFunction.start(), scopeEnd, symbols));
        }
        scopes.sort(Comparator.comparingInt(ProcedureScope::start));
        return scopes;
    }

    private void inventoryPackageProcedures(
        String sql,
        String masked,
        String packageName,
        int start,
        int end,
        boolean createScopes,
        AnalysisResult result,
        List<ProcedureScope> scopes
    ) {
        var declarations = new ArrayList<ProcedureDeclaration>();
        var matcher = SUBPROGRAM_DECLARATION.matcher(masked);
        matcher.region(start, end);
        while (matcher.find()) {
            var type = matcher.group(1).toLowerCase(Locale.ROOT);
            var subprogramName = NameUtil.normalize(packageName + "." + matcher.group(2));
            var parsed = parseDeclarationParameters(sql, masked, matcher.end(2));
            var afterParams = parsed.end();
            var symbols = registerSubprogram(result, subprogramName, type, parsed);
            if (createScopes && hasBodyIntroducer(masked, afterParams)) {
                declarations.add(new ProcedureDeclaration(
                    subprogramName, type, matcher.start(), symbols));
            }
        }

        for (var i = 0; i < declarations.size(); i++) {
            var declaration = declarations.get(i);
            var scopeEnd = i + 1 < declarations.size() ? declarations.get(i + 1).start() : end;
            scopes.add(new ProcedureScope(
                declaration.name(),
                declaration.type(),
                declaration.start(),
                scopeEnd,
                declaration.symbols()));
        }
    }

    private ParsedParameters parseDeclarationParameters(String sql, String masked, int afterName) {
        var cursor = skipWhitespace(masked, afterName);
        if (cursor >= masked.length() || masked.charAt(cursor) != '(') {
            return new ParsedParameters(List.of(), cursor);
        }
        var close = SqlText.matchingParen(masked, cursor);
        if (close < 0) {
            return new ParsedParameters(List.of(), cursor);
        }
        var parameters = new ArrayList<String>();
        for (var rawParameter : SqlText.splitTopLevel(sql.substring(cursor + 1, close), ',')) {
            var name = SqlText.identifierAt(rawParameter, 0);
            if (!name.isBlank()) {
                parameters.add(NameUtil.normalize(name));
            }
        }
        return new ParsedParameters(parameters, close + 1);
    }

    private Map<String, String> registerSubprogram(
        AnalysisResult result,
        String subprogramName,
        String type,
        ParsedParameters parsed
    ) {
        var id = type.equals("function")
            ? NameUtil.functionId(subprogramName)
            : NameUtil.procedureId(subprogramName);
        result.addObject(id, type, subprogramName);
        var symbols = new LinkedHashMap<String, String>();
        for (var parameter : parsed.names()) {
            var parameterId = "parameter." + NameUtil.idPart(subprogramName) + "." + NameUtil.idPart(parameter);
            result.addObject(parameterId, "parameter", subprogramName + "." + parameter);
            symbols.put(NameUtil.idPart(parameter), parameterId);
        }
        return symbols;
    }

    private void inventoryTriggers(String masked, AnalysisResult result) {
        var matcher = CREATE_TRIGGER.matcher(masked);
        while (matcher.find()) {
            var triggerName = NameUtil.normalize(matcher.group(1));
            result.addObject("trigger." + NameUtil.idPart(triggerName), "trigger", triggerName);
        }
    }

    private void analyzeViews(
        String sql,
        String masked,
        SchemaCatalog catalog,
        AnalysisResult result
    ) {
        var matcher = CREATE_VIEW.matcher(masked);
        while (matcher.find()) {
            var end = SqlText.statementEnd(masked, matcher.end());
            var view = catalog.ensureView(matcher.group(1));
            var query = sql.substring(matcher.end(), end);
            var queryInfo = new QueryAnalyzer(catalog, Map.of()).analyze(query);
            for (var output : queryInfo.outputs()) {
                var target = catalog.ensureColumn(view, output.name());
                var expression = output.aggregate() ? output.expandedExpression() : output.expression();
                for (var source : output.sources()) {
                    result.addRelationship("direct", source, target, expression);
                }
            }
            for (var join : queryInfo.joins()) {
                for (var source : join.sources()) {
                    result.addRelationship("indirect", source, view.id(), "JOIN");
                }
            }
            for (var condition : queryInfo.where()) {
                for (var source : condition.sources()) {
                    result.addRelationship("indirect", source, view.id(), "WHERE " + condition.expression());
                }
            }
        }
    }

    private void analyzeInserts(
        String sql,
        String masked,
        int baseOffset,
        SchemaCatalog catalog,
        AnalysisResult result,
        List<ProcedureScope> scopes,
        Map<String, String> extraSymbols
    ) {
        var matcher = INSERT_START.matcher(masked);
        while (matcher.find()) {
            var absoluteStart = baseOffset + matcher.start();
            var scope = containingScope(absoluteStart, scopes);
            var symbols = new LinkedHashMap<String, String>();
            if (scope != null) {
                symbols.putAll(scope.symbols());
            }
            symbols.putAll(extraSymbols);
            analyzeInsertStatement(
                sql, masked, matcher.start(), matcher.end(), matcher.group(1),
                catalog, result, scope, symbols);
        }
    }

    private void analyzeInsertStatement(
        String sql,
        String masked,
        int statementStart,
        int afterTarget,
        String targetName,
        SchemaCatalog catalog,
        AnalysisResult result,
        ProcedureScope scope,
        Map<String, String> symbols
    ) {
        var statementEnd = SqlText.statementEnd(masked, statementStart);
        var cursor = skipWhitespace(masked, afterTarget);
        var targetColumns = new ArrayList<String>();
        if (cursor < masked.length() && masked.charAt(cursor) == '(') {
            var close = SqlText.matchingParen(masked, cursor);
            if (close < 0 || close > statementEnd) {
                addUnsupported(result, sql.substring(statementStart, Math.min(sql.length(), statementEnd)), "INSERT");
                return;
            }
            for (var column : SqlText.splitTopLevel(sql.substring(cursor + 1, close), ',')) {
                targetColumns.add(NameUtil.normalize(lastNamePart(column)));
            }
            cursor = skipWhitespace(masked, close + 1);
        }

        var target = catalog.ensureTable(targetName);
        if (targetColumns.isEmpty()) {
            targetColumns.addAll(catalog.columns(target));
        }
        if (wordAt(masked, cursor, "VALUES")) {
            analyzeInsertValues(sql, masked, cursor + 6, statementEnd, target, targetColumns, catalog, result, symbols);
            return;
        }

        var queryText = sql.substring(cursor, statementEnd);
        if (!(startsWithWord(masked, cursor, "SELECT") || startsWithWord(masked, cursor, "WITH"))) {
            addUnsupported(result, sql.substring(statementStart, Math.min(sql.length(), statementEnd)), "INSERT");
            return;
        }
        var queryInfo = new QueryAnalyzer(catalog, symbols).analyze(queryText);
        var outputCount = Math.min(targetColumns.size(), queryInfo.outputs().size());
        for (var i = 0; i < outputCount; i++) {
            var output = queryInfo.outputs().get(i);
            var targetColumn = catalog.ensureColumn(target, targetColumns.get(i));
            var expression = output.aggregate() ? output.expandedExpression() : output.expression();
            for (var source : output.sources()) {
                result.addRelationship("direct", source, targetColumn, expression);
            }
        }

        var aggregate = queryInfo.aggregateOutput();
        var indirectTarget = aggregate == null
            ? target.id()
            : catalog.ensureColumn(target, targetColumns.get(queryInfo.outputs().indexOf(aggregate)));
        for (var join : queryInfo.joins()) {
            for (var source : join.sources()) {
                var type = queryInfo.groupSources().contains(source) ? "JOIN/GROUP BY" : "JOIN";
                result.addRelationship("indirect", source, indirectTarget, type);
            }
        }
        for (var condition : queryInfo.where()) {
            for (var source : condition.sources()) {
                result.addRelationship(
                    "indirect", source, target.id(), "WHERE " + condition.expression());
            }
        }
    }

    private void analyzeInsertValues(
        String sql,
        String masked,
        int afterValues,
        int statementEnd,
        SchemaCatalog.Relation target,
        List<String> targetColumns,
        SchemaCatalog catalog,
        AnalysisResult result,
        Map<String, String> symbols
    ) {
        var cursor = skipWhitespace(masked, afterValues);
        if (cursor >= masked.length() || masked.charAt(cursor) != '(') {
            addUnsupported(result, sql.substring(afterValues, Math.min(sql.length(), statementEnd)), "INSERT VALUES");
            return;
        }
        var close = SqlText.matchingParen(masked, cursor);
        if (close < 0 || close > statementEnd) {
            addUnsupported(result, sql.substring(afterValues, Math.min(sql.length(), statementEnd)), "INSERT VALUES");
            return;
        }
        var values = SqlText.splitTopLevel(sql.substring(cursor + 1, close), ',');
        var resolver = new QueryAnalyzer(catalog, symbols);
        var count = Math.min(targetColumns.size(), values.size());
        for (var i = 0; i < count; i++) {
            var expression = SqlText.normalizeWhitespace(values.get(i));
            var targetColumn = catalog.ensureColumn(target, targetColumns.get(i));
            var resolved = resolver.resolveAgainstRelations(expression, Map.of());
            for (var source : resolved.sources()) {
                result.addRelationship("direct", source, targetColumn, expression);
            }
            addSequenceDiagnostics(expression, result);
        }
    }

    private List<Range> analyzeMerges(
        String sql,
        String masked,
        SchemaCatalog catalog,
        AnalysisResult result,
        List<ProcedureScope> scopes
    ) {
        var ranges = new ArrayList<Range>();
        var matcher = MERGE_START.matcher(masked);
        while (matcher.find()) {
            var end = SqlText.statementEnd(masked, matcher.start());
            ranges.add(new Range(matcher.start(), end));
            var statement = sql.substring(matcher.start(), end);
            var statementMasked = masked.substring(matcher.start(), end);
            var target = catalog.ensureTable(matcher.group(1));
            var source = catalog.ensureTable(matcher.group(3));
            var targetAlias = matcher.group(2) == null ? lastNamePart(matcher.group(1)) : matcher.group(2);
            var sourceAlias = matcher.group(4) == null ? lastNamePart(matcher.group(3)) : matcher.group(4);
            var aliases = new LinkedHashMap<String, SchemaCatalog.Relation>();
            aliases.put(NameUtil.idPart(targetAlias), target);
            aliases.put(NameUtil.idPart(sourceAlias), source);
            aliases.put(NameUtil.idPart(target.name()), target);
            aliases.put(NameUtil.idPart(source.name()), source);
            var scope = containingScope(matcher.start(), scopes);
            var resolver = new QueryAnalyzer(catalog, scope == null ? Map.of() : scope.symbols());

            analyzeMergeOn(statement, statementMasked, target, aliases, resolver, result);
            analyzeMergeUpdate(statement, target, aliases, resolver, catalog, result);
            analyzeMergeInsert(statement, target, aliases, resolver, catalog, result);
        }
        return ranges;
    }

    private void analyzeMergeOn(
        String statement,
        String statementMasked,
        SchemaCatalog.Relation target,
        Map<String, SchemaCatalog.Relation> aliases,
        QueryAnalyzer resolver,
        AnalysisResult result
    ) {
        var onIndex = SqlText.topLevelKeyword(statement, "ON", 0);
        if (onIndex < 0) {
            return;
        }
        var open = skipWhitespace(statementMasked, onIndex + 2);
        if (open >= statementMasked.length() || statementMasked.charAt(open) != '(') {
            return;
        }
        var close = SqlText.matchingParen(statementMasked, open);
        if (close < 0) {
            return;
        }
        var expression = statement.substring(open + 1, close);
        var resolved = resolver.resolveAgainstRelations(expression, aliases);
        for (var source : resolved.sources()) {
            result.addRelationship("indirect", source, target.id(), "MERGE ON");
        }
    }

    private void analyzeMergeUpdate(
        String statement,
        SchemaCatalog.Relation target,
        Map<String, SchemaCatalog.Relation> aliases,
        QueryAnalyzer resolver,
        SchemaCatalog catalog,
        AnalysisResult result
    ) {
        var updateIndex = SqlText.topLevelKeyword(statement, "UPDATE SET", 0);
        if (updateIndex < 0) {
            return;
        }
        var notMatched = SqlText.topLevelKeyword(statement, "WHEN NOT MATCHED", updateIndex);
        var end = notMatched < 0 ? statement.length() : notMatched;
        var assignments = statement.substring(updateIndex + "UPDATE SET".length(), end);
        for (var rawAssignment : SqlText.splitTopLevel(assignments, ',')) {
            addAssignmentLineage(rawAssignment, target, aliases, resolver, catalog, result);
        }
    }

    private void analyzeMergeInsert(
        String statement,
        SchemaCatalog.Relation target,
        Map<String, SchemaCatalog.Relation> aliases,
        QueryAnalyzer resolver,
        SchemaCatalog catalog,
        AnalysisResult result
    ) {
        var notMatched = SqlText.topLevelKeyword(statement, "WHEN NOT MATCHED", 0);
        var insertIndex = notMatched < 0 ? -1 : SqlText.topLevelKeyword(statement, "INSERT", notMatched);
        if (insertIndex < 0) {
            return;
        }
        var masked = SqlText.maskLiteralsAndComments(statement);
        var columnsOpen = masked.indexOf('(', insertIndex);
        if (columnsOpen < 0) {
            return;
        }
        var columnsClose = SqlText.matchingParen(masked, columnsOpen);
        var valuesIndex = SqlText.topLevelKeyword(statement, "VALUES", columnsClose);
        if (columnsClose < 0 || valuesIndex < 0) {
            return;
        }
        var valuesOpen = masked.indexOf('(', valuesIndex);
        var valuesClose = valuesOpen < 0 ? -1 : SqlText.matchingParen(masked, valuesOpen);
        if (valuesClose < 0) {
            return;
        }
        var columns = SqlText.splitTopLevel(statement.substring(columnsOpen + 1, columnsClose), ',');
        var values = SqlText.splitTopLevel(statement.substring(valuesOpen + 1, valuesClose), ',');
        var count = Math.min(columns.size(), values.size());
        for (var i = 0; i < count; i++) {
            var targetColumn = catalog.ensureColumn(target, lastNamePart(columns.get(i)));
            var expression = SqlText.normalizeWhitespace(values.get(i));
            var resolved = resolver.resolveAgainstRelations(expression, aliases);
            for (var source : resolved.sources()) {
                result.addRelationship("direct", source, targetColumn, expression);
            }
        }
    }

    private void analyzeUpdates(
        String sql,
        String masked,
        SchemaCatalog catalog,
        AnalysisResult result,
        List<ProcedureScope> scopes,
        List<Range> mergeRanges
    ) {
        var matcher = UPDATE_START.matcher(masked);
        while (matcher.find()) {
            if (insideAny(matcher.start(), mergeRanges)) {
                continue;
            }
            var end = SqlText.statementEnd(masked, matcher.start());
            var statement = sql.substring(matcher.start(), end);
            var target = catalog.ensureTable(matcher.group(1));
            var alias = matcher.group(2) == null ? lastNamePart(matcher.group(1)) : matcher.group(2);
            var aliases = new LinkedHashMap<String, SchemaCatalog.Relation>();
            aliases.put(NameUtil.idPart(alias), target);
            aliases.put(NameUtil.idPart(target.name()), target);
            var scope = containingScope(matcher.start(), scopes);
            var resolver = new QueryAnalyzer(catalog, scope == null ? Map.of() : scope.symbols());
            var setIndex = SqlText.topLevelKeyword(statement, "SET", 0);
            var whereIndex = SqlText.topLevelKeyword(statement, "WHERE", setIndex);
            var setEnd = whereIndex < 0 ? statement.length() : whereIndex;
            var targetIds = new LinkedHashSet<String>();
            for (var assignment : SqlText.splitTopLevel(
                statement.substring(setIndex + 3, setEnd), ',')) {
                var targetId = addAssignmentLineage(
                    assignment, target, aliases, resolver, catalog, result);
                if (targetId != null) {
                    targetIds.add(targetId);
                }
            }
            if (whereIndex >= 0) {
                var where = statement.substring(whereIndex + 5);
                var resolved = resolver.resolveAgainstRelations(where, aliases);
                for (var source : resolved.sources()) {
                    for (var targetId : targetIds) {
                        result.addRelationship("indirect", source, targetId, "UPDATE WHERE");
                    }
                }
            }
        }
    }

    private String addAssignmentLineage(
        String rawAssignment,
        SchemaCatalog.Relation target,
        Map<String, SchemaCatalog.Relation> aliases,
        QueryAnalyzer resolver,
        SchemaCatalog catalog,
        AnalysisResult result
    ) {
        var assignment = SqlText.normalizeWhitespace(rawAssignment);
        var equals = assignment.indexOf('=');
        if (equals < 0) {
            return null;
        }
        var targetColumn = catalog.ensureColumn(target, lastNamePart(assignment.substring(0, equals)));
        var expression = SqlText.normalizeWhitespace(assignment.substring(equals + 1));
        var resolved = resolver.resolveAgainstRelations(expression, aliases);
        for (var source : resolved.sources()) {
            result.addRelationship("direct", source, targetColumn, expression);
        }
        return targetColumn;
    }

    private void analyzeProcedureCalls(
        String sql,
        String masked,
        List<ProcedureScope> scopes,
        AnalysisResult result
    ) {
        for (var scope : scopes) {
            var matcher = QUALIFIED_CALL.matcher(masked);
            matcher.region(scope.start(), Math.min(scope.end(), masked.length()));
            while (matcher.find()) {
                var close = SqlText.matchingParen(masked, matcher.end() - 1);
                if (close < 0 || close > scope.end()) {
                    continue;
                }
                var targetName = NameUtil.normalize(matcher.group(1) + "." + matcher.group(2));
                var functionId = NameUtil.functionId(targetName);
                var targetType = result.objects.containsKey(functionId) ? "function" : "procedure";
                var targetId = targetType.equals("function")
                    ? functionId
                    : NameUtil.procedureId(targetName);
                result.addObject(targetId, targetType, targetName);
                var expression = SqlText.normalizeWhitespace(sql.substring(matcher.start(), close + 1));
                result.addRelationship("call", scope.id(), targetId, expression);
            }
        }
    }

    private void analyzeDynamicSql(
        String sql,
        String masked,
        SchemaCatalog catalog,
        AnalysisResult result,
        List<ProcedureScope> scopes
    ) {
        for (var scope : scopes) {
            var assignments = collectAssignments(sql, masked, scope);
            var executions = EXECUTE_IMMEDIATE.matcher(masked);
            executions.region(scope.start(), Math.min(scope.end(), masked.length()));
            var ordinal = 1;
            while (executions.find()) {
                var end = SqlText.statementEnd(masked, executions.start());
                var expressionStart = skipWhitespace(masked, executions.end());
                var usingIndex = topLevelKeywordInRange(sql, "USING", expressionStart, end);
                var expressionEnd = usingIndex < 0 ? end : usingIndex;
                var executeExpression = SqlText.normalizeWhitespace(
                    sql.substring(expressionStart, expressionEnd));
                var variable = simpleIdentifier(executeExpression);
                var assignment = variable == null
                    ? new Assignment(executions.start(), "", executeExpression)
                    : latestAssignment(assignments, variable, executions.start());
                String evaluated = assignment == null ? null : evaluateStringExpression(assignment.expression());
                var span = variable == null ? "literal_" + ordinal : variable;

                if (evaluated == null) {
                    result.addDiagnostic(
                        "warning",
                        "UNRESOLVED_DYNAMIC_SQL",
                        "Dynamic SQL contains non-literal object name input and cannot be resolved statically.",
                        span);
                    ordinal++;
                    continue;
                }

                var statementId = "statement.dynamic." + NameUtil.idPart(scope.name()) + "." + NameUtil.idPart(span);
                result.addObject(statementId, "dynamic_statement", scope.name() + "." + NameUtil.normalize(span));
                result.addRelationship(
                    "dynamic_sql", scope.id(), statementId, "literal concatenation resolved");

                var bindSymbols = bindSymbols(
                    evaluated,
                    usingIndex < 0 ? "" : sql.substring(usingIndex + 5, end),
                    scope.symbols());
                var dynamicScope = new ProcedureScope(
                    scope.name(),
                    scope.type(),
                    0,
                    evaluated.length(),
                    mergeSymbols(scope.symbols(), bindSymbols));
                var dynamicMasked = SqlText.maskLiteralsAndComments(evaluated);
                analyzeInserts(
                    evaluated, dynamicMasked, 0, catalog, result,
                    List.of(dynamicScope), bindSymbols);
                ordinal++;
            }
        }
    }

    private List<Assignment> collectAssignments(String sql, String masked, ProcedureScope scope) {
        var assignments = new ArrayList<Assignment>();
        var matcher = ASSIGNMENT.matcher(masked);
        matcher.region(scope.start(), Math.min(scope.end(), masked.length()));
        while (matcher.find()) {
            var end = SqlText.statementEnd(masked, matcher.start());
            assignments.add(new Assignment(
                matcher.start(),
                NameUtil.idPart(matcher.group(1)),
                SqlText.normalizeWhitespace(sql.substring(matcher.end(), end))));
        }
        return assignments;
    }

    private Assignment latestAssignment(List<Assignment> assignments, String variable, int before) {
        Assignment latest = null;
        for (var assignment : assignments) {
            if (assignment.position() < before
                && assignment.variable().equals(NameUtil.idPart(variable))
                && (latest == null || assignment.position() > latest.position())) {
                latest = assignment;
            }
        }
        return latest;
    }

    private String evaluateStringExpression(String expression) {
        var pieces = splitConcatenation(expression);
        if (pieces.isEmpty()) {
            return null;
        }
        var out = new StringBuilder();
        for (var rawPiece : pieces) {
            var piece = rawPiece.strip();
            if (piece.length() < 2 || piece.charAt(0) != '\'' || piece.charAt(piece.length() - 1) != '\'') {
                return null;
            }
            out.append(piece.substring(1, piece.length() - 1).replace("''", "'"));
        }
        return out.toString();
    }

    private List<String> splitConcatenation(String expression) {
        var pieces = new ArrayList<String>();
        var start = 0;
        var inString = false;
        for (var i = 0; i < expression.length() - 1; i++) {
            var ch = expression.charAt(i);
            var next = expression.charAt(i + 1);
            if (ch == '\'') {
                if (inString && next == '\'') {
                    i++;
                    continue;
                }
                inString = !inString;
            } else if (!inString && ch == '|' && next == '|') {
                pieces.add(expression.substring(start, i));
                start = i + 2;
                i++;
            }
        }
        pieces.add(expression.substring(start));
        return pieces;
    }

    private Map<String, String> bindSymbols(
        String dynamicSql,
        String usingClause,
        Map<String, String> procedureSymbols
    ) {
        var bindNames = new ArrayList<String>();
        var matcher = BIND_REFERENCE.matcher(SqlText.maskLiteralsAndComments(dynamicSql));
        while (matcher.find()) {
            var bind = NameUtil.idPart(matcher.group(1));
            if (!bindNames.contains(bind)) {
                bindNames.add(bind);
            }
        }
        var usingValues = SqlText.splitTopLevel(usingClause, ',');
        var result = new LinkedHashMap<String, String>();
        var count = Math.min(bindNames.size(), usingValues.size());
        for (var i = 0; i < count; i++) {
            var symbol = procedureSymbols.get(NameUtil.idPart(usingValues.get(i)));
            if (symbol != null) {
                result.put(":" + bindNames.get(i), symbol);
            }
        }
        return result;
    }

    private Map<String, String> mergeSymbols(Map<String, String> first, Map<String, String> second) {
        var merged = new LinkedHashMap<>(first);
        merged.putAll(second);
        return merged;
    }

    private void addSequenceDiagnostics(String expression, AnalysisResult result) {
        var matcher = SEQUENCE_REFERENCE.matcher(expression);
        while (matcher.find()) {
            result.addDiagnostic(
                "info",
                "UNRESOLVED_SEQUENCE",
                "Sequence references are inventoried only when schema metadata includes them.",
                matcher.group());
        }
    }

    private void addUnsupported(AnalysisResult result, String sql, String kind) {
        var span = SqlText.normalizeWhitespace(sql);
        if (span.length() > 120) {
            span = span.substring(0, 120);
        }
        result.addDiagnostic(
            "warning",
            "UNSUPPORTED_STATEMENT",
            kind + " statement could not be projected into the MVP lineage model.",
            span);
    }

    private ProcedureScope containingScope(int position, List<ProcedureScope> scopes) {
        return scopes.stream()
            .filter(scope -> position >= scope.start() && position < scope.end())
            .min(Comparator.comparingInt(scope -> scope.end() - scope.start()))
            .orElse(null);
    }

    private int nextCreateIndex(String masked, int fromIndex) {
        var matcher = Pattern.compile("(?is)\\bCREATE\\s+(?:OR\\s+REPLACE\\s+)?").matcher(masked);
        return matcher.find(fromIndex) ? matcher.start() : -1;
    }

    private int topLevelKeywordInRange(String sql, String keyword, int start, int end) {
        if (start >= end) {
            return -1;
        }
        var relative = SqlText.topLevelKeyword(sql.substring(start, end), keyword, 0);
        return relative < 0 ? -1 : start + relative;
    }

    private int skipWhitespace(String value, int start) {
        var cursor = Math.max(0, start);
        while (cursor < value.length() && Character.isWhitespace(value.charAt(cursor))) {
            cursor++;
        }
        return cursor;
    }

    private boolean wordAt(String value, int index, String word) {
        return startsWithWord(value, index, word);
    }

    private boolean startsWithWord(String value, int index, String word) {
        return index >= 0
            && index + word.length() <= value.length()
            && value.regionMatches(true, index, word, 0, word.length())
            && (index == 0 || !SqlText.isIdentifierPart(value.charAt(index - 1)))
            && (index + word.length() == value.length()
                || !SqlText.isIdentifierPart(value.charAt(index + word.length())));
    }

    private boolean hasBodyIntroducer(String masked, int start) {
        var end = SqlText.statementEnd(masked, start);
        var matcher = Pattern.compile("(?is)\\b(?:IS|AS)\\b").matcher(masked);
        matcher.region(start, Math.min(end, masked.length()));
        return matcher.find();
    }

    private String lastNamePart(String name) {
        var normalized = NameUtil.normalize(name);
        var dot = normalized.lastIndexOf('.');
        return dot < 0 ? normalized : normalized.substring(dot + 1);
    }

    private String simpleIdentifier(String expression) {
        var stripped = expression.strip();
        return stripped.matches("(?i)[A-Za-z_][\\w$#]*") ? stripped : null;
    }

    private boolean insideAny(int position, List<Range> ranges) {
        return ranges.stream().anyMatch(range -> position >= range.start() && position < range.end());
    }

    private record Range(int start, int end) {
    }

    private record ParsedParameters(List<String> names, int end) {
    }

    private record ProcedureDeclaration(
        String name,
        String type,
        int start,
        Map<String, String> symbols
    ) {
    }

    private record Assignment(int position, String variable, String expression) {
    }
}
