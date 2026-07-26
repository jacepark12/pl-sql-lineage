package io.sqlflowmvp;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class FixtureVerifier {
    private final OracleLineageAnalyzer analyzer = new OracleLineageAnalyzer();

    int verify(Path root) throws IOException {
        var syntheticRoot = root.resolve("fixtures").resolve("synthetic");
        var caseDirs = new ArrayList<Path>();
        try (var paths = Files.walk(syntheticRoot)) {
            paths.filter(path -> path.getFileName().toString().equals("input.sql"))
                .map(Path::getParent)
                .sorted(Comparator.comparing(Path::toString))
                .forEach(caseDirs::add);
        }

        var failures = new ArrayList<String>();
        for (var caseDir : caseDirs) {
            var sql = Files.readString(caseDir.resolve("input.sql"));
            var actual = analyzer.analyze(sql);
            var expected = ExpectedFixture.load(caseDir);
            verifyCase(root, caseDir, expected, actual, failures);
            verifyRenamedCase(root, caseDir, sql, expected, failures);
        }

        if (!failures.isEmpty()) {
            failures.forEach(System.err::println);
            System.err.printf("fixture verification failed: %d failure(s)%n", failures.size());
            return 1;
        }

        System.out.printf(
            "verified %d synthetic fixture(s) and %d renamed generalization variant(s)%n",
            caseDirs.size(),
            caseDirs.size());
        return 0;
    }

    private void verifyRenamedCase(
        Path root,
        Path caseDir,
        String sql,
        ExpectedFixture expected,
        ArrayList<String> failures
    ) {
        var replacements = replacementsFor(caseDir);
        if (replacements.isEmpty()) {
            failures.add(root.relativize(caseDir) + ": no generalization rename map configured");
            return;
        }
        var renamedSql = replaceIdentifiers(sql, replacements);
        var renamedExpected = transformExpected(expected, replacements);
        var actual = analyzer.analyze(renamedSql);
        verifyCase(
            root,
            caseDir.resolve("renamed-generalization"),
            renamedExpected,
            actual,
            failures);
    }

    private Map<String, String> replacementsFor(Path caseDir) {
        var name = caseDir.getFileName().toString();
        var replacements = new LinkedHashMap<String, String>();
        switch (name) {
            case "basic_insert_select" -> {
                replacements.put("CUSTOMER_ORDER_SUMMARY", "ACCOUNT_METRIC");
                replacements.put("CUSTOMERS", "ACCOUNTS_SRC");
                replacements.put("ORDERS", "TXN_SRC");
            }
            case "create_view" -> {
                replacements.put("CATEGORY_SALES_V", "PRODUCT_REVENUE_V");
                replacements.put("ORDER_LINES", "ITEM_ROWS");
                replacements.put("PRODUCTS", "CATALOG_ITEMS");
            }
            case "merge_update" -> {
                replacements.put("CUSTOMER_STAGE", "MEMBER_STAGE");
                replacements.put("CUSTOMER_DIM", "MEMBER_DIM");
            }
            case "package_calls" -> {
                replacements.put("CUSTOMER_EVENT_PKG", "MEMBER_SIGNAL_PKG");
                replacements.put("CUSTOMER_EVENTS", "MEMBER_SIGNALS");
                replacements.put("AUDIT_PKG", "TRACE_PKG");
                replacements.put("AUDIT_LOG", "TRACE_LOG");
            }
            case "dynamic_sql" -> {
                replacements.put("LOAD_SALES", "LOAD_METRICS");
                replacements.put("SALES_STAGE", "METRIC_STAGE");
                replacements.put("SALES_FACT", "METRIC_FACT");
            }
            case "function_calls" -> {
                replacements.put("PRICING_PKG", "RATING_PKG");
                replacements.put("ORDER_TOTALS", "INVOICE_TOTALS");
                replacements.put("NET_AMOUNT", "FINAL_AMOUNT");
                replacements.put("STORE_TOTAL", "SAVE_TOTAL");
            }
            default -> {
            }
        }
        return replacements;
    }

    private ExpectedFixture transformExpected(
        ExpectedFixture expected,
        Map<String, String> replacements
    ) {
        var objects = expected.objects.stream()
            .map(object -> new LineageObject(
                replaceIdentifiers(object.id(), replacements),
                object.type(),
                replaceIdentifiers(object.name(), replacements)))
            .toList();
        var relationships = expected.relationships.stream()
            .map(relationship -> new Relationship(
                relationship.type(),
                replaceIdentifiers(relationship.source(), replacements),
                replaceIdentifiers(relationship.target(), replacements),
                replaceIdentifiers(relationship.expression(), replacements)))
            .toList();
        var diagnostics = expected.diagnostics.stream()
            .map(diagnostic -> new Diagnostic(
                diagnostic.severity(),
                diagnostic.code(),
                replaceIdentifiers(diagnostic.message(), replacements),
                replaceIdentifiers(diagnostic.spanText(), replacements)))
            .toList();
        return new ExpectedFixture(objects, relationships, diagnostics);
    }

    private String replaceIdentifiers(String value, Map<String, String> replacements) {
        var replaced = value;
        var entries = replacements.entrySet().stream()
            .sorted(Map.Entry.<String, String>comparingByKey(
                Comparator.comparingInt(String::length).reversed()))
            .toList();
        for (var entry : entries) {
            var pattern = Pattern.compile("(?i)\\b" + Pattern.quote(entry.getKey()) + "\\b");
            replaced = pattern.matcher(replaced).replaceAll(match ->
                Matcher.quoteReplacement(matchCase(match.group(), entry.getValue())));
        }
        return replaced;
    }

    private String matchCase(String original, String replacement) {
        if (original.equals(original.toUpperCase(Locale.ROOT))) {
            return replacement.toUpperCase(Locale.ROOT);
        }
        if (original.equals(original.toLowerCase(Locale.ROOT))) {
            return replacement.toLowerCase(Locale.ROOT);
        }
        return replacement;
    }

    private void verifyCase(
        Path root,
        Path caseDir,
        ExpectedFixture expected,
        AnalysisResult actual,
        ArrayList<String> failures
    ) {
        var label = root.relativize(caseDir).toString();
        for (var object : expected.objects) {
            var actualObject = actual.objects.get(object.id());
            if (!object.equals(actualObject)) {
                failures.add(label + ": missing object " + object);
            }
        }
        for (var object : actual.objects.values()) {
            if (!expected.objects.contains(object)) {
                failures.add(label + ": unexpected object " + object);
            }
        }
        for (var relationship : expected.relationships) {
            if (!actual.relationships.contains(relationship)) {
                failures.add(label + ": missing relationship " + relationship);
            }
        }
        for (var relationship : actual.relationships) {
            if (!expected.relationships.contains(relationship)) {
                failures.add(label + ": unexpected relationship " + relationship);
            }
        }
        for (var diagnostic : expected.diagnostics) {
            if (!actual.diagnostics.contains(diagnostic)) {
                failures.add(label + ": missing diagnostic " + diagnostic);
            }
        }
        for (var diagnostic : actual.diagnostics) {
            if (!expected.diagnostics.contains(diagnostic)) {
                failures.add(label + ": unexpected diagnostic " + diagnostic);
            }
        }
    }
}
