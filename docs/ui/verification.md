# UI verification

Verified locally in Chrome on 2026-09-06. Reference interactions are recorded in
[palantir-reference.md](palantir-reference.md).

## Automated checks

From `web/`, run `npm ci`, `npm test`, and `npm run build`.
The test suite covers the repository's real engine/export fixtures, source evidence,
DB links, validation errors, fictional provenance, directed paths, cycles, traversal
limits, dataset aggregation, FILTER isolation, intra-table transformations, and
stable layout identity across selection changes. GitHub Actions repeats these checks.

## Browser checks performed

- Opened the fictional demo and switched from dataset cards to column rows.
- Imported `plsql-lineage-engine/tests/fixtures/engine_sample.json` through the native
  file picker: 22 normalized objects, 8 expanded source-target edges, 2 diagnostics.
- Inspected `PARSE_FAILED` and `SQL_NOT_ANALYZED` with their file and line locations.
- Selected `SYNWMS.OUT_ALLOC`, selected FILTER and upstream: only its two predicate
  source datasets and the selected target remained in the displayed graph.
- Imported invalid JSON: the UI displayed an error and retained the current graph.
- Imported a generated 1,000-dataset / 999-relationship legacy file. The browser
  rendered 160 dataset nodes and 159 edges, with an explicit truncation message.
  Searching for `999` exposed `SCALE_0999`, outside the initial rendered subset.
- Found the fictional 3-hop path from `ERP.SALES_ORDER_LINE.NET_AMOUNT` to
  `MART.EXECUTIVE_KPI.REVENUE_TOTAL`, including all three expressions and source locations.
- Exported the demo: checked the downloaded file parses as JSON, retains fictional
  metadata, and contains the expected 17 edges and one demo diagnostic.
- Checked narrow viewport layouts, the scrollable toolbar, inspector overlay,
  panel collapse, and Help / Escape behavior. Restored the original browser viewport.

Chrome's extension file-chooser API was unavailable in this session. Native macOS
file selection worked. No extension permissions were changed.

## Context menu and selection regression (2026-09-07)

- Reproduced the original issue: selecting another node in a downstream graph
  reduced the visible graph from four datasets to one.
- Verified the fix in Chrome: selecting another node preserves all four nodes,
  three edges, node positions, and the viewport transform exactly.
- Verified dataset and column context menus, explicit upstream/downstream scope,
  and Show all resources restoring the 14-dataset demo.
- Verified column Shift+F10, keyboard menu navigation, copying a column's fully
  qualified name, and Escape restoring focus to the triggering column.
- All 18 unit tests and the production build pass. Browser warning/error logs
  were empty during these checks.

## Canvas redesign verification (2026-09-07)

- Compared the running Palantir reference's compact nodes, straight arrows,
  selection, downstream expansion, Columns inspector, and collapsed bottom tabs.
- Verified the local 14-dataset demo on the flat canvas, with perimeter arrows,
  distinct schema colors, and no default grid, animation, or minimap.
- A four-dataset downstream scope retained the same four nodes, three edges,
  positions, and viewport after selecting a different dataset.
- Dragging a dataset moved only that dataset, updated its three incident paths,
  and retained the viewport. Subsequent selection preserved dragged positions.
- Column mode displayed 16 exact connections across 14 datasets. Column selection
  retained node positions and viewport; measured SVG endpoints were stable within
  0.001 graph units after zoom and initial handle measurement had settled.
- Verified About/Columns, Trace column, real transform evidence, persistent bottom
  tabs, minimap toggle, and Shift+F10 / Escape focus restoration.
- Checked a narrow viewport: no document overflow, compact legend, accessible
  inspector reopen button, and persistent tabs. Restored the default viewport.
- All 22 tests and the production build pass. Regression coverage includes parallel
  column edges, explicit overflow attachments, active edge filters, and stable scope.

## Operational limits

- Local file import is capped at 25 MiB. Parsing runs in the browser.
- Graph rendering is bounded to 160 datasets, 500 visual edges, and 8 visible
  connected-column rows per dataset. Additional rendered-edge endpoints attach to
  a labelled overflow row; their count is shown. Full column lists remain in the inspector.
- Path search is bounded to 12 hops, 20 paths, and 10,000 visited states. A truncated
  negative result is explicitly inconclusive.
- Search and detail lists are also bounded; source JSON export preserves the original
  imported payload instead of exporting a partial displayed subgraph.
- The 1,000-dataset test demonstrates bounded local rendering, not production capacity
  for an enterprise catalog. Server-side search/subgraph serving, authentication,
  access control, audit history, and load testing remain deployment integration work.
- No live database records, inferred job health, or fabricated source edges are used
  as operational evidence. The included demo is fictional.
