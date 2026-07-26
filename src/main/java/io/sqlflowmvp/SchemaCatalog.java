package io.sqlflowmvp;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

final class SchemaCatalog {
    private final AnalysisResult result;
    private final Map<String, Relation> relations = new LinkedHashMap<>();

    SchemaCatalog(AnalysisResult result) {
        this.result = result;
    }

    Relation ensureTable(String name) {
        return ensureRelation(name, "table");
    }

    Relation ensureView(String name) {
        return ensureRelation(name, "view");
    }

    Relation ensureRelation(String name, String preferredType) {
        var normalized = NameUtil.normalize(name);
        var key = normalized.toLowerCase(Locale.ROOT);
        var existing = relations.get(key);
        if (existing != null) {
            return existing;
        }
        var relation = new Relation(normalized, preferredType, new ArrayList<>());
        relations.put(key, relation);
        result.addObject(relation.id(), preferredType, normalized);
        return relation;
    }

    String ensureColumn(String relationName, String columnName) {
        var relation = ensureTable(relationName);
        return ensureColumn(relation, columnName);
    }

    String ensureColumn(Relation relation, String columnName) {
        var normalized = NameUtil.normalize(columnName);
        if (relation.columns.stream().noneMatch(existing -> existing.equalsIgnoreCase(normalized))) {
            relation.columns.add(normalized);
        }
        var id = NameUtil.columnId(relation.name, normalized);
        result.addObject(id, "column", relation.name + "." + normalized);
        return id;
    }

    Relation find(String name) {
        if (name == null) {
            return null;
        }
        return relations.get(NameUtil.idPart(name));
    }

    boolean hasColumn(Relation relation, String columnName) {
        return relation.columns.stream().anyMatch(column -> column.equalsIgnoreCase(NameUtil.normalize(columnName)));
    }

    List<String> columns(Relation relation) {
        return List.copyOf(relation.columns);
    }

    final class Relation {
        private final String name;
        private final String type;
        private final ArrayList<String> columns;

        private Relation(String name, String type, ArrayList<String> columns) {
            this.name = name;
            this.type = type;
            this.columns = columns;
        }

        String name() {
            return name;
        }

        String type() {
            return type;
        }

        String id() {
            return type.equals("view") ? NameUtil.viewId(name) : NameUtil.tableId(name);
        }
    }
}
