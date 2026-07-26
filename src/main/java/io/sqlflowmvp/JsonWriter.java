package io.sqlflowmvp;

import java.util.Collection;

final class JsonWriter {
    private JsonWriter() {
    }

    static String write(AnalysisResult result) {
        var out = new StringBuilder();
        out.append("{\n");
        out.append("  \"objects\": ");
        writeObjects(out, result.sortedObjects(), 2);
        out.append(",\n");
        out.append("  \"relationships\": ");
        writeRelationships(out, result.sortedRelationships(), 2);
        out.append(",\n");
        out.append("  \"diagnostics\": ");
        writeDiagnostics(out, result.diagnostics, 2);
        out.append("\n}\n");
        return out.toString();
    }

    private static void writeObjects(StringBuilder out, Collection<LineageObject> objects, int indent) {
        out.append("[");
        var first = true;
        for (var object : objects) {
            if (!first) {
                out.append(",");
            }
            first = false;
            out.append("\n").append(spaces(indent + 2)).append("{");
            field(out, "id", object.id(), true);
            field(out, "type", object.type(), false);
            field(out, "name", object.name(), false);
            out.append("}");
        }
        if (!objects.isEmpty()) {
            out.append("\n").append(spaces(indent));
        }
        out.append("]");
    }

    private static void writeRelationships(StringBuilder out, Collection<Relationship> relationships, int indent) {
        out.append("[");
        var first = true;
        for (var relationship : relationships) {
            if (!first) {
                out.append(",");
            }
            first = false;
            out.append("\n").append(spaces(indent + 2)).append("{");
            field(out, "type", relationship.type(), true);
            field(out, "source", relationship.source(), false);
            field(out, "target", relationship.target(), false);
            field(out, "expression", relationship.expression(), false);
            out.append("}");
        }
        if (!relationships.isEmpty()) {
            out.append("\n").append(spaces(indent));
        }
        out.append("]");
    }

    private static void writeDiagnostics(StringBuilder out, Collection<Diagnostic> diagnostics, int indent) {
        out.append("[");
        var first = true;
        for (var diagnostic : diagnostics) {
            if (!first) {
                out.append(",");
            }
            first = false;
            out.append("\n").append(spaces(indent + 2)).append("{");
            field(out, "severity", diagnostic.severity(), true);
            field(out, "code", diagnostic.code(), false);
            field(out, "message", diagnostic.message(), false);
            field(out, "spanText", diagnostic.spanText(), false);
            out.append("}");
        }
        if (!diagnostics.isEmpty()) {
            out.append("\n").append(spaces(indent));
        }
        out.append("]");
    }

    private static void field(StringBuilder out, String name, String value, boolean first) {
        if (!first) {
            out.append(",");
        }
        out.append("\"").append(escape(name)).append("\": \"").append(escape(value)).append("\"");
    }

    private static String spaces(int count) {
        return " ".repeat(count);
    }

    private static String escape(String value) {
        return value
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t");
    }
}

