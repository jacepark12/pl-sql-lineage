#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for the Oracle PL/SQL lineage workspace.
#
# Creates a repo-local virtualenv, installs the lineage engine's runtime
# dependencies, builds the generated ANTLR PL/SQL parser (needs java + network),
# and generates the synthetic corpus the engine analyzes. Safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VENV="$REPO_ROOT/.venv"

# The default image ships python3.12 but not the stdlib venv/ensurepip module.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  echo "[install] installing python3-venv"
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv
fi

if [ ! -x "$VENV/bin/python" ]; then
  echo "[install] creating virtualenv at $VENV"
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip >/dev/null

# Runtime deps come straight from the engine's pyproject so this stays in sync.
echo "[install] installing lineage engine dependencies"
mapfile -t DEPS < <(cd plsql-lineage-engine && python3 -c \
  "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))")
pip install "${DEPS[@]}"

# Generate the ANTLR PL/SQL parser (~8 MB, gitignored, cached under .parser-build).
echo "[install] building PL/SQL parser"
( cd plsql-lineage-engine && python3 scripts/build_parser.py )

# Generate + merge the synthetic PL/SQL + EAI corpus (deterministic, gitignored under out/).
echo "[install] generating synthetic corpus"
( cd plsql-lineage-corpus \
    && python3 -m synplsql.generate --out out \
    && python3 -m syneai.generate --out out/eai --merge out )

echo "[install] done — activate with: source .venv/bin/activate"
