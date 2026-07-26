package io.sqlflowmvp;

import java.util.Locale;

final class NameUtil {
    private NameUtil() {
    }

    static String normalize(String name) {
        return name
            .replace("\"", "")
            .trim()
            .replaceAll("\\s+", " ")
            .toUpperCase(Locale.ROOT);
    }

    static String idPart(String name) {
        return normalize(name).toLowerCase(Locale.ROOT);
    }

    static String tableId(String tableName) {
        return "table." + idPart(tableName);
    }

    static String viewId(String viewName) {
        return "view." + idPart(viewName);
    }

    static String columnId(String ownerName, String columnName) {
        return "column." + idPart(ownerName) + "." + idPart(columnName);
    }

    static String packageId(String packageName) {
        return "package." + idPart(packageName);
    }

    static String procedureId(String procedureName) {
        return "procedure." + idPart(procedureName);
    }

    static String functionId(String functionName) {
        return "function." + idPart(functionName);
    }
}
