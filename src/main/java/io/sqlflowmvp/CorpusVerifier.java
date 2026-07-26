package io.sqlflowmvp;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

final class CorpusVerifier {
    private final OracleLineageAnalyzer analyzer = new OracleLineageAnalyzer();

    int verify(Path root) throws IOException {
        var failures = new ArrayList<String>();
        verifyCorpus(
            "public",
            root.resolve("fixtures").resolve("public"),
            15,
            200,
            75,
            Set.of("table", "view", "package", "procedure", "function", "trigger"),
            Set.of("direct", "indirect", "call"),
            failures);
        verifyCorpus(
            "parser",
            root.resolve("fixtures").resolve("parser"),
            10,
            8,
            1,
            Set.of("package", "procedure", "function", "trigger"),
            Set.of("call"),
            failures);

        if (!failures.isEmpty()) {
            failures.forEach(System.err::println);
            System.err.printf("corpus verification failed: %d failure(s)%n", failures.size());
            return 1;
        }
        return 0;
    }

    private void verifyCorpus(
        String label,
        Path corpusRoot,
        int minimumFiles,
        int minimumObjects,
        int minimumRelationships,
        Set<String> requiredObjectTypes,
        Set<String> requiredRelationshipTypes,
        List<String> failures
    ) throws IOException {
        if (!Files.isDirectory(corpusRoot)) {
            failures.add(label + ": missing corpus directory " + corpusRoot);
            return;
        }

        List<Path> sqlFiles;
        try (var paths = Files.walk(corpusRoot)) {
            sqlFiles = paths
                .filter(Files::isRegularFile)
                .filter(path -> path.getFileName().toString().toLowerCase().endsWith(".sql"))
                .sorted(Comparator.comparing(Path::toString))
                .toList();
        }
        var combined = new AnalysisResult();
        for (var sqlFile : sqlFiles) {
            try {
                combined.merge(analyzer.analyze(Files.readString(sqlFile)));
            } catch (RuntimeException exception) {
                failures.add(label + ": analyzer crashed for " + sqlFile + ": " + exception.getMessage());
            }
        }

        requireAtLeast(label, "SQL files", sqlFiles.size(), minimumFiles, failures);
        requireAtLeast(label, "objects", combined.objects.size(), minimumObjects, failures);
        requireAtLeast(
            label, "relationships", combined.relationships.size(), minimumRelationships, failures);

        var objectTypes = combined.objects.values().stream()
            .map(LineageObject::type)
            .collect(java.util.stream.Collectors.toSet());
        for (var type : requiredObjectTypes) {
            if (!objectTypes.contains(type)) {
                failures.add(label + ": missing required object type " + type);
            }
        }

        var relationshipTypes = combined.relationships.stream()
            .map(Relationship::type)
            .collect(java.util.stream.Collectors.toSet());
        for (var type : requiredRelationshipTypes) {
            if (!relationshipTypes.contains(type)) {
                failures.add(label + ": missing required relationship type " + type);
            }
        }

        for (var relationship : combined.relationships) {
            if (!combined.objects.containsKey(relationship.source())) {
                failures.add(label + ": relationship source has no object " + relationship.source());
            }
            if (!combined.objects.containsKey(relationship.target())) {
                failures.add(label + ": relationship target has no object " + relationship.target());
            }
        }

        System.out.printf(
            "verified %s corpus: %d SQL file(s), %d object(s), %d relationship(s), %d diagnostic(s)%n",
            label,
            sqlFiles.size(),
            combined.objects.size(),
            combined.relationships.size(),
            combined.diagnostics.size());
    }

    private void requireAtLeast(
        String label,
        String metric,
        int actual,
        int expected,
        List<String> failures
    ) {
        if (actual < expected) {
            failures.add(
                "%s: expected at least %d %s, got %d".formatted(
                    label, expected, metric, actual));
        }
    }
}
