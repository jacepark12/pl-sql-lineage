-- SQLite first cut of docs/column-lineage-schema.md §8 (the three tables
-- column_ref, evidence, column_lineage_assertion, plus the edge view).
--
-- Assumptions (the design is PostgreSQL 16; this file is the sqlite stand-in
-- so a smoke loader can run without a hosted DB):
-- * ENUM → TEXT + CHECK (same labels as the design)
-- * JSONB → TEXT holding JSON
-- * BIGINT[] → JSON array of integers
-- * TIMESTAMPTZ → TEXT (ISO-8601); DEFAULT datetime('now')
-- * BIGSERIAL → INTEGER PRIMARY KEY AUTOINCREMENT
-- * GIN (from_columns) omitted; sqlite has no GIN
-- * LATERAL unnest(from_columns) → json_each(from_columns)
-- * UNIQUE (schema_, table_, column_) uses IFNULL(column_, '') because
--   sqlite treats NULLs as distinct in UNIQUE indexes
-- * db_link (doc §2 open question) is not a fourth column: remote objects
--   keep TABLE@LINK in table_ so SYN.T and SYN.T@REMOTE stay distinct
-- * This stub has no promote workflow; the loader writes status='accepted'
--   so column_lineage_edge (which filters accepted + valid_to IS NULL) is
--   queryable. Human review / supersedes is out of scope.

CREATE TABLE column_ref (
  id       INTEGER       PRIMARY KEY AUTOINCREMENT,
  schema_  VARCHAR(128)  NOT NULL,
  table_   VARCHAR(128)  NOT NULL,
  column_  VARCHAR(128)
);

CREATE UNIQUE INDEX column_ref_ident
  ON column_ref (schema_, table_, IFNULL(column_, ''));

CREATE TABLE evidence (
  id          CHAR(32)     PRIMARY KEY,
  source_rev  VARCHAR(64)  NOT NULL,
  path        TEXT         NOT NULL,
  container   TEXT,
  body        TEXT         NOT NULL
);

CREATE TABLE column_lineage_assertion (
  id            CHAR(32)     PRIMARY KEY,
  to_column     INTEGER      NOT NULL REFERENCES column_ref(id),
  from_columns  TEXT         NOT NULL,
  kind          TEXT         NOT NULL
                  CHECK (kind IN (
                    'DIRECT','TRANSFORM','AGGREGATE','ANALYTIC',
                    'VIA_VARIABLE','VIA_CTE','VIA_PIPELINE',
                    'FILTER','CONSTANT','SEVERED','UNRESOLVED'
                  )),
  expression    TEXT,
  evidence_id   CHAR(32)     REFERENCES evidence(id),
  span          TEXT,
  method        TEXT         NOT NULL
                  CHECK (method IN (
                    'static-parse','runtime-log','native','agent','human'
                  )),
  confidence    REAL,
  status        TEXT         NOT NULL DEFAULT 'proposed'
                  CHECK (status IN ('proposed','accepted','rejected')),
  asserted_by   TEXT         NOT NULL,
  supersedes    CHAR(32)     REFERENCES column_lineage_assertion(id),
  valid_from    TEXT         NOT NULL DEFAULT (datetime('now')),
  valid_to      TEXT
);

CREATE INDEX column_lineage_assertion_to_column
  ON column_lineage_assertion (to_column) WHERE valid_to IS NULL;
CREATE INDEX column_lineage_assertion_evidence
  ON column_lineage_assertion (evidence_id);

CREATE VIEW column_lineage_edge AS
SELECT a.id, a.kind, a.expression, a.confidence,
       s.schema_ || '.' || s.table_ || '.' || coalesce(s.column_, '*') AS from_fqn,
       t.schema_ || '.' || t.table_ || '.' || coalesce(t.column_, '*') AS to_fqn
FROM   column_lineage_assertion a
JOIN   json_each(a.from_columns) AS src
JOIN   column_ref s ON s.id = src.value
JOIN   column_ref t ON t.id = a.to_column
WHERE  a.valid_to IS NULL
  AND  a.status = 'accepted';
