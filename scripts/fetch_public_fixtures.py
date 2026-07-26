#!/usr/bin/env python3
"""Fetch selected public Oracle/PLSQL SQL fixtures at pinned commits."""

from __future__ import annotations

import dataclasses
import pathlib
import textwrap
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]


@dataclasses.dataclass(frozen=True)
class RepoSource:
    owner: str
    repo: str
    commit: str
    license_name: str
    source_url: str
    target_dir: pathlib.Path
    files: tuple[str, ...]
    purpose: str


SOURCES = (
    RepoSource(
        owner="oracle-samples",
        repo="db-sample-schemas",
        commit="6660bad68c07bd143430ace58565b3f727e17263",
        license_name="MIT",
        source_url="https://github.com/oracle-samples/db-sample-schemas",
        target_dir=ROOT / "fixtures/public/oracle-sample-schemas",
        purpose="Official Oracle sample schemas for object and schema-resolution coverage.",
        files=(
            "README.md",
            "human_resources/hr_create.sql",
            "human_resources/hr_code.sql",
            "customer_orders/co_create.sql",
            "order_entry/oe_cre.sql",
            "order_entry/oe_views.sql",
            "sales_history/sh_create.sql",
        ),
    ),
    RepoSource(
        owner="oracle-samples",
        repo="oracle-db-examples",
        commit="9c6f8f4e371bc2ef35fc70293797a42d8e84c2aa",
        license_name="Apache-2.0",
        source_url="https://github.com/oracle-samples/oracle-db-examples",
        target_dir=ROOT / "fixtures/public/oracle-db-examples",
        purpose="Official Oracle examples for PL/SQL syntax and feature coverage.",
        files=(
            "plsql/README.md",
            "plsql/sql-in-plsql/cursor-for-loop.sql",
            "plsql/sql-in-plsql/cursors-in-plsql.sql",
            "plsql/sql-in-plsql/trigger-predicates.sql",
            "plsql/dynamic-sql/dynamic-sql-method-2.sql",
            "plsql/dynamic-sql/dynamic-method-3.sql",
            "plsql/dynamic-sql/bind-not-concatenate.sql",
            "plsql/error-management/basic-error-logging-package.sql",
            "plsql/performance/forall-inserts-comparison.sql",
            "plsql/utilities/string-tracker.sql",
        ),
    ),
    RepoSource(
        owner="antlr",
        repo="grammars-v4",
        commit="e756f2a2ee5565a9300666f100ba6acd874664f7",
        license_name="BSD-3-Clause",
        source_url="https://github.com/antlr/grammars-v4/tree/master/sql/plsql",
        target_dir=ROOT / "fixtures/parser/antlr-plsql",
        purpose="ANTLR PL/SQL examples for parser stress and regression coverage.",
        files=(
            "sql/plsql/examples/examples-sql-script/anonymous_block.sql",
            "sql/plsql/examples/examples-sql-script/package_with_cursor.sql",
            "sql/plsql/examples/examples-sql-script/procedure_with_cursor_and_limit.sql",
            "sql/plsql/examples/examples-sql-script/trigger_examples.sql",
            "sql/plsql/examples/examples-sql-script/with_clause_in_exists_block_in_procedure.sql",
            "sql/plsql/more-examples/create_package01.sql",
            "sql/plsql/more-examples/package_body.sql",
            "sql/plsql/more-examples/merge01.sql",
            "sql/plsql/more-examples/query_factoring01.sql",
            "sql/plsql/more-examples/dblink.sql",
        ),
    ),
)


def raw_url(source: RepoSource, path: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{source.owner}/{source.repo}/"
        f"{source.commit}/{path}"
    )


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "sqlflow-fixture-fetcher/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def write_source_doc(source: RepoSource) -> None:
    content = textwrap.dedent(
        f"""\
        # Source

        Purpose: {source.purpose}

        Upstream: {source.source_url}

        Commit: `{source.commit}`

        License: {source.license_name}

        Fetched files:
        {chr(10).join(f"- `{path}`" for path in source.files)}
        """
    )
    (source.target_dir / "SOURCE.md").write_text(content, encoding="utf-8")


def fetch_source(source: RepoSource) -> None:
    source.target_dir.mkdir(parents=True, exist_ok=True)
    for path in source.files:
        target = source.target_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(fetch_text(raw_url(source, path)), encoding="utf-8")
        print(f"fetched {source.repo}:{path} -> {target.relative_to(ROOT)}")
    write_source_doc(source)


def main() -> None:
    for source in SOURCES:
        fetch_source(source)


if __name__ == "__main__":
    main()

