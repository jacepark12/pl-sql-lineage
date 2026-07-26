package io.sqlflowmvp;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0 || args[0].equals("--help") || args[0].equals("help")) {
            printHelp();
            return;
        }

        var command = args[0];
        switch (command) {
            case "analyze" -> analyze(args);
            case "verify-fixtures" -> System.exit(verifyFixtures(args));
            case "verify-corpus" -> System.exit(verifyCorpus(args));
            default -> {
                System.err.println("unknown command: " + command);
                printHelp();
                System.exit(2);
            }
        }
    }

    private static void analyze(String[] args) throws IOException {
        var input = valueAfter(args, "--input");
        if (input == null) {
            throw new IllegalArgumentException("analyze requires --input <sql-file>");
        }

        var inputPath = Path.of(input);
        var result = analyzePath(inputPath);
        var json = JsonWriter.write(result);

        var out = valueAfter(args, "--out");
        if (out == null) {
            System.out.print(json);
        } else {
            var outPath = Path.of(out);
            if (outPath.getParent() != null) {
                Files.createDirectories(outPath.getParent());
            }
            Files.writeString(outPath, json);
            System.out.println("wrote " + outPath);
        }
    }

    private static AnalysisResult analyzePath(Path input) throws IOException {
        var analyzer = new OracleLineageAnalyzer();
        if (Files.isRegularFile(input)) {
            return analyzer.analyze(Files.readString(input));
        }
        if (!Files.isDirectory(input)) {
            throw new IllegalArgumentException("input does not exist: " + input);
        }

        var combined = new AnalysisResult();
        var count = 0;
        try (var paths = Files.walk(input)) {
            var sqlFiles = paths
                .filter(Files::isRegularFile)
                .filter(path -> path.getFileName().toString().toLowerCase().endsWith(".sql"))
                .sorted(Comparator.comparing(Path::toString))
                .toList();
            for (var sqlFile : sqlFiles) {
                combined.merge(analyzer.analyze(Files.readString(sqlFile)));
                count++;
            }
        }
        System.err.printf("analyzed %d SQL file(s) under %s%n", count, input);
        return combined;
    }

    private static int verifyFixtures(String[] args) throws IOException {
        var root = valueAfter(args, "--root");
        var rootPath = root == null ? Path.of(".").toAbsolutePath().normalize() : Path.of(root).toAbsolutePath().normalize();
        return new FixtureVerifier().verify(rootPath);
    }

    private static int verifyCorpus(String[] args) throws IOException {
        var root = valueAfter(args, "--root");
        var rootPath = root == null
            ? Path.of(".").toAbsolutePath().normalize()
            : Path.of(root).toAbsolutePath().normalize();
        return new CorpusVerifier().verify(rootPath);
    }

    private static String valueAfter(String[] args, String flag) {
        for (var i = 0; i < args.length - 1; i++) {
            if (args[i].equals(flag)) {
                return args[i + 1];
            }
        }
        return null;
    }

    private static void printHelp() {
        System.out.println("""
            Oracle PL/SQL Lineage MVP

            Commands:
              analyze --input <sql-file-or-directory> [--out <json-file>]
              verify-fixtures [--root <repo-root>]
              verify-corpus [--root <repo-root>]

            Examples:
              ./gradlew run --args="analyze --input fixtures/synthetic/lineage/basic_insert_select/input.sql"
              ./gradlew verifyFixtures
            """);
    }
}
