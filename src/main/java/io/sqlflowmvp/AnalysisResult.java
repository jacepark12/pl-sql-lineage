package io.sqlflowmvp;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class AnalysisResult {
    final Map<String, LineageObject> objects = new LinkedHashMap<>();
    final List<Relationship> relationships = new ArrayList<>();
    final List<Diagnostic> diagnostics = new ArrayList<>();

    void addObject(String id, String type, String name) {
        objects.putIfAbsent(id, new LineageObject(id, type, name));
    }

    void addRelationship(String type, String source, String target, String expression) {
        var relationship = new Relationship(type, source, target, expression);
        if (!relationships.contains(relationship)) {
            relationships.add(relationship);
        }
    }

    void addDiagnostic(String severity, String code, String message, String spanText) {
        var diagnostic = new Diagnostic(severity, code, message, spanText);
        if (!diagnostics.contains(diagnostic)) {
            diagnostics.add(diagnostic);
        }
    }

    void merge(AnalysisResult other) {
        other.objects.values().forEach(object ->
            addObject(object.id(), object.type(), object.name()));
        other.relationships.forEach(relationship ->
            addRelationship(
                relationship.type(),
                relationship.source(),
                relationship.target(),
                relationship.expression()));
        other.diagnostics.forEach(diagnostic ->
            addDiagnostic(
                diagnostic.severity(),
                diagnostic.code(),
                diagnostic.message(),
                diagnostic.spanText()));
    }

    List<LineageObject> sortedObjects() {
        return objects.values().stream()
            .sorted(Comparator.comparing(LineageObject::id))
            .toList();
    }

    List<Relationship> sortedRelationships() {
        return relationships.stream()
            .sorted(Comparator
                .comparing(Relationship::type)
                .thenComparing(Relationship::source)
                .thenComparing(Relationship::target)
                .thenComparing(Relationship::expression))
            .toList();
    }
}
