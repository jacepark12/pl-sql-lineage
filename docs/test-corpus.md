# Oracle PL/SQL Test SQL Acquisition

## Source Tiers

1. Synthetic correctness fixtures
   - Hand-written SQL/PLSQL under `fixtures/synthetic`.
   - Each case has `input.sql`, `expected.objects.json`, `expected.relationships.json`, and `expected.diagnostics.json`.
   - These are the source of truth for lineage correctness.

2. Oracle official sample schemas
   - Downloaded into `fixtures/public/oracle-sample-schemas`.
   - Used for schema, table, column, view, and object-resolution coverage.
   - Upstream: `oracle-samples/db-sample-schemas`.

3. Oracle official database examples
   - Downloaded into `fixtures/public/oracle-db-examples`.
   - Used for PL/SQL language coverage: packages, procedures, functions, cursors, dynamic SQL, exception blocks, triggers.
   - Upstream: `oracle-samples/oracle-db-examples`.

4. ANTLR PL/SQL examples
   - Downloaded into `fixtures/parser/antlr-plsql`.
   - Used as parser stress tests, not as lineage ground truth.
   - Upstream: `antlr/grammars-v4/sql/plsql`.

5. Private anonymized samples
   - Reserved path: `fixtures/private/anonymized`.
   - Only deterministic pseudonyms are allowed for schema, table, column, package, procedure, function, literal, and comment content.
   - Raw production SQL must not be stored in this workspace.

## Validation Rules

- A fixture without expected JSON is not a correctness test.
- Public third-party examples are parser and coverage tests unless a human writes expected lineage.
- Unsupported syntax must produce diagnostics rather than silent omission.
- SQLFlow comparison samples must be synthetic or public, never private production SQL.

## Automated Gates

Run all gates with:

```sh
./gradlew check
```

The fixture gate analyzes every synthetic `input.sql`, compares expected objects, relationships, and diagnostics, then reruns each case after deterministic domain-name replacement. The renamed pass proves that extraction is not tied to names such as `CUSTOMERS`, `CATEGORY_SALES_V`, or `LOAD_SALES`.

The corpus gate analyzes all pinned public and parser SQL files. It verifies minimum file/object/relationship counts, required Oracle object and edge types, no analyzer crashes, and that every relationship endpoint exists in the object inventory.

To inspect the aggregate public result manually:

```sh
./gradlew run --args="analyze \
  --input fixtures/public \
  --out reports/demo/public-corpus.json"
open web/index.html
```

## Update Process

1. Run `python3 scripts/fetch_public_fixtures.py`.
2. Review each generated `SOURCE.md`.
3. Add new synthetic fixtures for any real bug or missing lineage behavior.
4. Keep SQLFlow differential outputs under `reports/sqlflow-diff`.
5. Run `./gradlew check` before accepting an analyzer change.
