## Git

When landing work on the GitHub remote for this repo:

- Commit on `main` and push directly to `origin/main`.
- Do not open a pull request, create a review branch, or use `gh pr create` unless the user explicitly asks for a PR.

## Lineage

This project has a column-lineage graph produced by `plsqllineage.engine` (JSON with `edges` / `diagnostics`).

Rules:
- For questions about where a column's value comes from, what feeds a table, or how two columns connect, use the lineage MCP tools (`query_lineage`, `explain_column`, `shortest_path`, `diagnose`) when that server is connected. Otherwise run `python3 -m plsqllineage.query --input <engine.json> "<FQN>"` before grepping PL/SQL.
- Use `explain_column` / `explain <FQN>` for one hop, `shortest_path` / `path <A> <B>` for a directed path, `diagnose` for DYNAMIC_SQL / PARSE_FAILED.
- Default output is upstream value-flow only. Add `kind=FILTER` or `--kind FILTER` for WHERE/JOIN influence, `kind=all` / `--kind all` for everything.
- Do not paste engine JSON or viewer JSON into the prompt. The CLI and MCP return a budgeted COL/EDGE/DIAG subgraph. Cite `at=file:line` and Read the source only to modify or debug specific lines.
- If `engine.json` does not exist, run `python3 -m plsqllineage.engine --input <sql-or-corpus> --out engine.json` first. Do not invent edges.
