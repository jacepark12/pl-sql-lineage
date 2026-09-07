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

## Canvas and visual hierarchy follow-up (2026-09-07)

Revisited the running Chrome reference after feedback that the first implementation
resembled an ERD. Inspected an existing dataset graph, selected a dataset, expanded
its downstream resources, fitted the graph, and opened and expanded a Columns row.

- The canvas is a flat, cool gray surface without a dot grid.
- Dataset nodes are compact pastel rectangles with a centered name. Column counts,
  schema rows, and metadata do not occupy the default graph nodes.
- Connections are direct, diagonal or horizontal arrow segments. They attach to
  the node perimeter instead of passing through a visible port or an elbow bundle.
- Selection uses an orange outline and orange connected arrows. Other resources
  remain on the graph. Flow animation is an explicit option, initially off.
- A small legend explains node colors. The lower-left zoom controls are vertical;
  the minimap is an optional toggle, initially off.
- About and Columns are separate inspector tabs. Expanding a column reveals its
  metadata in the inspector; the dataset canvas remains intact.
- Bottom inspection tools remain available as a collapsed tab strip.

The local translation colors nodes by the source schema actually present in the
imported graph, with an explicit schema legend. It does not infer Foundry resource
types, build state, or business stages. Column mode remains a separate way to see
the engine's exact column endpoints and trace a selected column's value flow.
