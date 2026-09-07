# Data Lineage UI reference

Inspected interactively in the user's existing Chrome session on 2026-09-06.
Reference: Palantir Foundry → Data Lineage. No Foundry data, screenshots, credentials,
or resource identifiers are bundled with this application.

## Observed interactions

1. Empty graph opens with Add resources and Open graph actions.
2. Add resources opens a right sidebar with Basic / Advanced search. Search produces
   resource names and folder context; selecting a result adds the dataset to the graph.
3. Dataset selection enables expansion. A dataset's hidden-children action adds a
   downstream level. Expansion menus distinguish upstream and downstream levels.
4. Selecting one dataset enables its properties sidebar with About and Columns tabs.
5. Columns supports text filtering and individually expandable rows.
6. Preview opens a bottom panel with a dense tabular dataset view. Other tabs include
   code, history, build timeline, and data health.
7. The working canvas has a compact top toolbar, resource coloring / legend, lower-left
   zoom and fit controls, and a narrow right sidebar tool rail.

## Application translation

Retain the canvas-first layout, compact visual density, selection treatment,
progressive graph exploration, searchable properties and column lists, and bottom
inspection panel. Render this repository's source evidence and diagnostics instead
of pretending it supplies live dataset rows, builds, permissions, or health metrics.

The new UI has its own branding and implementation. It does not depend on Foundry
or copy its assets. Demo content is fictional and explicitly identified as such.
Actual supported inputs are this repository's engine and legacy viewer contracts.

## Scope of verification

The reference operations above were performed in the running application. This is
not a claim of parity with every Foundry feature. Production deployment still needs
the enterprise's identity, authorization, data-serving, operational and capacity
requirements; a browser UI cannot establish those guarantees on its own.

## Context menu follow-up (2026-09-07)

Right-clicked a dataset in the live reference. The menu includes Expand node,
Color node, Group node, Remove node, Move node here, Open in new graph, dataset
operations, and Copy RID. Expand node exposes upstream/downstream level controls.

The local UI exposes applicable actions on both datasets and column rows: details,
explicit upstream-only/downstream-only views, show all, centering, and copying.
It does not expose Foundry build or scheduling operations that the engine cannot
perform. Selection is separate from exploration scope: ordinary clicks update
selection and evidence without changing the visible resources or viewport.
