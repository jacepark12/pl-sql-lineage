## Git

When landing work on the GitHub remote for this repo:

- Commit on `main` and push directly to `origin/main`.
- Do not open a pull request, create a review branch, or use `gh pr create` unless the user explicitly asks for a PR.

## Lineage

The product graph is table-to-table. `plsqllineage.engine` writes `relations` next to the archived column `edges`. A relation's ends are tables. The procedure is `location` on that relation (`package`, `procedure`, `file`, `line`), not a node.

Rules:
- For questions about what feeds a table, use `query_lineage` or `python3 -m plsqllineage.query --input <engine.json> "<TABLE>"` before grepping PL/SQL. The seed is `OUT_ALLOC` or `SYNWMS.OUT_ALLOC`.
- Default output is upstream `TABLE` / `REL` / `DIAG`. `REL` carries the operation, `method` (`static` or `dynamic-literal`), and `at=file:line`.
- `--grain column` reads the archived column `edges`. Use it only when a column mapping is explicitly required.
- `diagnose` still reports `DYNAMIC_SQL` for statements whose table name is not a literal.
- Do not paste engine JSON into the prompt. Cite `at=file:line` and Read the source only to modify or debug specific lines.
- If `engine.json` does not exist, run `python3 -m plsqllineage.engine --input <sql-or-corpus> --out engine.json` first. Do not invent edges.
