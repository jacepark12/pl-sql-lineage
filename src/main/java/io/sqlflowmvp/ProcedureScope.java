package io.sqlflowmvp;

import java.util.LinkedHashMap;
import java.util.Map;

record ProcedureScope(
    String name,
    String type,
    int start,
    int end,
    Map<String, String> symbols
) {
    ProcedureScope {
        symbols = new LinkedHashMap<>(symbols);
    }

    String id() {
        return type.equals("function") ? NameUtil.functionId(name) : NameUtil.procedureId(name);
    }
}
