#!/usr/bin/env bash
# Start MCP stdio + loopback UI HTTP in one process (what Cursor mcp.json launches).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PLSQL_LINEAGE_PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="${PYTHON:-python3}"
fi

engine_candidates=()
if [[ -n "${PLSQL_LINEAGE_ENGINE:-}" ]]; then
  engine_candidates+=("$PLSQL_LINEAGE_ENGINE")
fi
engine_candidates+=(
  "$ROOT/engine.json"
  "$ROOT/plsql-lineage-corpus/out/engine.json"
  "$ROOT/plsql-lineage-engine/tests/fixtures/engine_sample.json"
)

ENGINE=""
for candidate in "${engine_candidates[@]}"; do
  if [[ -f "$candidate" ]]; then
    ENGINE="$candidate"
    break
  fi
done

if [[ -z "$ENGINE" ]]; then
  echo "No engine JSON. Set PLSQL_LINEAGE_ENGINE or run:" >&2
  echo "  python3 -m plsqllineage.engine --input <sql-or-corpus> --out engine.json" >&2
  exit 1
fi

UI="${PLSQL_LINEAGE_UI:-127.0.0.1:8765}"
export PYTHONPATH="${ROOT}/plsql-lineage-engine${PYTHONPATH:+:$PYTHONPATH}"

echo "lineage-serve engine=$ENGINE ui=$UI" >&2
exec "$PYTHON" -m plsqllineage.serve --input "$ENGINE" --ui "$UI" "$@"
