# Synthetic Fixtures

Synthetic fixtures are the correctness baseline for the Oracle PL/SQL lineage engine.

Each fixture directory contains:

- `input.sql`: the SQL/PLSQL source.
- `expected.objects.json`: expected inventory objects.
- `expected.relationships.json`: expected lineage or call graph relationships.
- `expected.diagnostics.json`: expected warnings, unresolved dynamic SQL, and unsupported constructs.

These fixtures intentionally use simple schemas and stable identifiers so test assertions can be exact.

