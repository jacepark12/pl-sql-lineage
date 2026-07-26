package io.sqlflowmvp;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

final class ExpectedFixture {
    private static final Pattern OBJECT_PATTERN = Pattern.compile(
        "\\{\\s*\"id\"\\s*:\\s*\"([^\"]+)\"\\s*,\\s*\"type\"\\s*:\\s*\"([^\"]+)\"\\s*,\\s*\"name\"\\s*:\\s*\"([^\"]+)\"\\s*}", Pattern.DOTALL);
    private static final Pattern RELATIONSHIP_PATTERN = Pattern.compile(
        "\\{\\s*\"type\"\\s*:\\s*\"([^\"]+)\"\\s*,\\s*\"source\"\\s*:\\s*\"([^\"]+)\"\\s*,\\s*\"target\"\\s*:\\s*\"([^\"]+)\"\\s*,\\s*\"expression\"\\s*:\\s*\"([^\"]+)\"\\s*}", Pattern.DOTALL);
    private static final Pattern DIAGNOSTIC_PATTERN = Pattern.compile(
        "\\{\\s*\"severity\"\\s*:\\s*\"([^\"]+)\"\\s*,\\s*\"code\"\\s*:\\s*\"([^\"]+)\"\\s*,\\s*\"message\"\\s*:\\s*\"([^\"]+)\"\\s*,\\s*\"spanText\"\\s*:\\s*\"([^\"]+)\"\\s*}", Pattern.DOTALL);

    final List<LineageObject> objects;
    final List<Relationship> relationships;
    final List<Diagnostic> diagnostics;

    ExpectedFixture(List<LineageObject> objects, List<Relationship> relationships, List<Diagnostic> diagnostics) {
        this.objects = objects;
        this.relationships = relationships;
        this.diagnostics = diagnostics;
    }

    static ExpectedFixture load(Path caseDir) throws IOException {
        return new ExpectedFixture(
            loadObjects(caseDir.resolve("expected.objects.json")),
            loadRelationships(caseDir.resolve("expected.relationships.json")),
            loadDiagnostics(caseDir.resolve("expected.diagnostics.json")));
    }

    private static List<LineageObject> loadObjects(Path path) throws IOException {
        var text = Files.readString(path);
        var matcher = OBJECT_PATTERN.matcher(text);
        var objects = new ArrayList<LineageObject>();
        while (matcher.find()) {
            objects.add(new LineageObject(matcher.group(1), matcher.group(2), matcher.group(3)));
        }
        return objects;
    }

    private static List<Relationship> loadRelationships(Path path) throws IOException {
        var text = Files.readString(path);
        var matcher = RELATIONSHIP_PATTERN.matcher(text);
        var relationships = new ArrayList<Relationship>();
        while (matcher.find()) {
            relationships.add(new Relationship(matcher.group(1), matcher.group(2), matcher.group(3), matcher.group(4)));
        }
        return relationships;
    }

    private static List<Diagnostic> loadDiagnostics(Path path) throws IOException {
        var text = Files.readString(path);
        var matcher = DIAGNOSTIC_PATTERN.matcher(text);
        var diagnostics = new ArrayList<Diagnostic>();
        while (matcher.find()) {
            diagnostics.add(new Diagnostic(matcher.group(1), matcher.group(2), matcher.group(3), matcher.group(4)));
        }
        return diagnostics;
    }
}

