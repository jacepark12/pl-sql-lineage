import { describe, expect, it } from "vitest";
import { buildCanvasModel, type BuildOptions } from "../../GraphCanvas";
import { DEMO_LINEAGE, parseLineage } from "../index";

const baseOptions: BuildOptions = {
  selectedId: null,
  scopeId: null,
  onSelect: () => undefined,
  mode: "datasets",
  direction: "all",
  depth: 8,
  kind: "all",
  query: "",
};

function legacyGraph(nodeCount: number, cycle = false) {
  const ids = Array.from({ length: nodeCount }, (_, index) => `table.scale_${String(index).padStart(4, "0")}`);
  const pairs = ids.slice(0, -1).map((id, index) => [id, ids[index + 1]] as const);
  if (cycle) pairs.push([ids.at(-1)!, ids[0]]);
  const result = parseLineage({
    objects: ids.map((id) => ({ id, type: "table", name: id.slice("table.".length) })),
    relationships: pairs.map(([source, target]) => ({ type: "direct", source, target, expression: `${source}->${target}` })),
    diagnostics: [],
  });
  if (!result.ok) throw new Error("model fixture failed validation");
  return result.graph;
}

function engineGraph(edges: Array<{ source: [string, string]; target: [string, string]; kind?: string }>) {
  const result = parseLineage({
    edges: edges.map(({ source, target, kind = "DIRECT" }) => ({
      sources: [{ table: source[0], column: source[1] }],
      target: { table: target[0], column: target[1] },
      kind,
    })),
  });
  if (!result.ok) throw new Error("engine fixture failed validation");
  return result.graph;
}

describe("buildCanvasModel", () => {
  it("walks upstream from a selected dataset across its column relationships", () => {
    const model = buildCanvasModel(DEMO_LINEAGE, {
      ...baseOptions, scopeId: "table.mart.customer_360", direction: "upstream", kind: "VALUE", depth: 4,
    });
    const ids = new Set(model.nodes.map((node) => node.id));
    expect(ids).toContain("table.mart.customer_360");
    expect(ids).toContain("table.dwh.fact_revenue");
    expect(ids).toContain("table.stage.order_enriched");
    expect(model.edges.length).toBeGreaterThanOrEqual(4);
  });

  it("includes a FILTER edge that terminates at the selected dataset node", () => {
    const model = buildCanvasModel(DEMO_LINEAGE, {
      ...baseOptions, scopeId: "table.mart.executive_kpi", direction: "upstream", kind: "FILTER", depth: 1,
    });
    expect(new Set(model.nodes.map((node) => node.id))).toEqual(new Set([
      "table.mart.executive_kpi", "table.dwh.fact_revenue",
    ]));
    expect(model.edges).toHaveLength(1);
    expect(model.edges[0]).toMatchObject({ source: "table.dwh.fact_revenue", target: "table.mart.executive_kpi" });
  });

  it("is cycle-safe and retains each connection in a small cycle", () => {
    const model = buildCanvasModel(legacyGraph(3, true), {
      ...baseOptions, scopeId: "table.scale_0000", direction: "downstream", depth: 10,
    });
    expect(model.nodes).toHaveLength(3);
    expect(model.edges).toHaveLength(3);
    expect(model.truncated).toBe(false);
  });

  it("caps a 200-dataset chain with no edge outside the visible node set", () => {
    const model = buildCanvasModel(legacyGraph(200), {
      ...baseOptions, scopeId: "table.scale_0000", direction: "downstream", depth: 500,
    });
    expect(model.nodes).toHaveLength(160);
    expect(model.edges).toHaveLength(159);
    expect(model.truncated).toBe(true);
    const ids = new Set(model.nodes.map((node) => node.id));
    for (const edge of model.edges) {
      expect(ids.has(edge.source)).toBe(true);
      expect(ids.has(edge.target)).toBe(true);
    }
  });
});

it("preserves layout identity when selection changes without changing visible topology", () => {
  const first = buildCanvasModel(DEMO_LINEAGE, { ...baseOptions, selectedId: "table.dwh.fact_revenue" });
  const second = buildCanvasModel(DEMO_LINEAGE, { ...baseOptions, selectedId: "column.erp.sales_order_line.net_amount" });
  expect(first.topologyKey).toBe(second.topologyKey);
  expect(first.nodes.map(node => [node.id, node.position])).toEqual(second.nodes.map(node => [node.id, node.position]));
});

it("keeps a frozen directional scope when selection changes or clears", () => {
  const scoped = { ...baseOptions, scopeId: "table.stage.order_enriched", direction: "downstream" as const, depth: 4 };
  const before = buildCanvasModel(DEMO_LINEAGE, { ...scoped, selectedId: "column.erp.sales_order_line.net_amount" });
  const after = buildCanvasModel(DEMO_LINEAGE, { ...scoped, selectedId: "table.mart.customer_360" });
  const cleared = buildCanvasModel(DEMO_LINEAGE, { ...scoped, selectedId: null });
  expect(after.nodes.map((node) => node.id)).toEqual(before.nodes.map((node) => node.id));
  expect(after.edges.map((edge) => edge.id)).toEqual(before.edges.map((edge) => edge.id));
  expect(after.topologyKey).toBe(before.topologyKey);
  expect(cleared.nodes.map((node) => node.id)).toEqual(before.nodes.map((node) => node.id));
  expect(cleared.edges.map((edge) => edge.id)).toEqual(before.edges.map((edge) => edge.id));
});

it("does not swap capped nodes to include a new selection", () => {
  const graph = legacyGraph(200);
  const first = buildCanvasModel(graph, { ...baseOptions, selectedId: "table.scale_0000" });
  const last = buildCanvasModel(graph, { ...baseOptions, selectedId: "table.scale_0199" });
  expect(last.nodes.map((node) => node.id)).toEqual(first.nodes.map((node) => node.id));
  expect(last.edges.map((edge) => edge.id)).toEqual(first.edges.map((edge) => edge.id));
  expect(last.topologyKey).toBe(first.topologyKey);
});

it("retains intra-table column transformations", () => {
  const parsed = parseLineage({ edges: [{ sources: [{ table: "T", column: "RAW" }], target: { table: "T", column: "CLEAN" }, kind: "TRANSFORM", transform: "TRIM(RAW)" }] });
  expect(parsed.ok).toBe(true);
  if (!parsed.ok) return;
  const model = buildCanvasModel(parsed.graph, { ...baseOptions, mode: "columns" });
  expect(model.nodes).toHaveLength(1);
  expect(model.edges).toHaveLength(1);
  expect(model.edges[0].sourceHandle).toBe("column.t.raw");
  expect(model.edges[0].targetHandle).toBe("column.t.clean::self");
  expect(model.edges[0].type).toBe("intraDataset");
  expect(model.edges[0].data).toEqual({ lane: 0 });
});

it("keeps parallel column flows exact while dataset mode groups them", () => {
  const graph = engineGraph([
    { source: ["SRC", "ID"], target: ["DST", "ID"] },
    { source: ["SRC", "AMOUNT"], target: ["DST", "AMOUNT"] },
  ]);
  const columns = buildCanvasModel(graph, { ...baseOptions, mode: "columns" });
  expect(columns.edges).toHaveLength(2);
  expect(new Set(columns.edges.map((edge) => `${edge.sourceHandle}->${edge.targetHandle}`))).toEqual(new Set([
    "column.src.amount->column.dst.amount",
    "column.src.id->column.dst.id",
  ]));

  const datasets = buildCanvasModel(graph, { ...baseOptions, mode: "datasets" });
  expect(datasets.edges).toHaveLength(1);
  expect(datasets.edges[0]).toMatchObject({ source: "table.src", target: "table.dst" });
  expect(datasets.edges[0].sourceHandle).toBeUndefined();
  expect(datasets.edges[0].targetHandle).toBeUndefined();
});

it("attaches overflow flows only to their labelled hidden endpoint handles", () => {
  const graph = engineGraph(Array.from({ length: 17 }, (_, index) => ({
    source: ["SRC", `C${String(index).padStart(2, "0")}`] as [string, string],
    target: ["DST", `C${String(index).padStart(2, "0")}`] as [string, string],
  })));
  const model = buildCanvasModel(graph, { ...baseOptions, mode: "columns" });
  const source = model.nodes.find((node) => node.id === "table.src");
  const target = model.nodes.find((node) => node.id === "table.dst");
  expect(source?.data.columns).toHaveLength(8);
  expect(target?.data.columns).toHaveLength(8);
  expect(source?.data.hiddenColumns.map((column) => column.id)).toContain("column.src.c16");
  expect(target?.data.hiddenColumns.map((column) => column.id)).toContain("column.dst.c16");

  const overflow = model.edges.find((edge) => edge.sourceHandle === "column.src.c16");
  expect(overflow).toMatchObject({
    source: "table.src", target: "table.dst",
    sourceHandle: "column.src.c16", targetHandle: "column.dst.c16",
  });
  expect(overflow?.sourceHandle).not.toBe(source?.data.columns.at(-1)?.id);
  expect(overflow?.targetHandle).not.toBe(target?.data.columns.at(-1)?.id);
});

it("expands overflow columns into exact visible endpoint rows", () => {
  const graph = engineGraph(Array.from({ length: 10 }, (_, index) => ({
    source: ["SRC", `C${String(index).padStart(2, "0")}`] as [string, string],
    target: ["DST", `C${String(index).padStart(2, "0")}`] as [string, string],
  })));
  const collapsed = buildCanvasModel(graph, { ...baseOptions, mode: "columns" });
  const expanded = buildCanvasModel(graph, {
    ...baseOptions, mode: "columns", expandedDatasetIds: new Set(["table.src"]),
  });
  const collapsedSource = collapsed.nodes.find((node) => node.id === "table.src");
  const expandedSource = expanded.nodes.find((node) => node.id === "table.src");

  expect(collapsedSource?.data.columns).toHaveLength(8);
  expect(collapsedSource?.data.hiddenColumnCount).toBe(2);
  expect(expandedSource?.data.columns).toHaveLength(10);
  expect(expandedSource?.data.hiddenColumns).toHaveLength(0);
  expect(expandedSource?.data.overflowExpanded).toBe(true);
  expect(expandedSource?.height).toBeGreaterThan(collapsedSource?.height ?? 0);
});

it("does not change disconnected edges or topology when a column is selected", () => {
  const graph = engineGraph([
    { source: ["A", "ID"], target: ["B", "ID"] },
    { source: ["X", "ID"], target: ["Y", "ID"] },
  ]);
  const before = buildCanvasModel(graph, { ...baseOptions, mode: "columns" });
  const after = buildCanvasModel(graph, { ...baseOptions, mode: "columns", selectedId: "column.a.id" });
  const disconnectedBefore = before.edges.find((edge) => edge.source === "table.x");
  const disconnectedAfter = after.edges.find((edge) => edge.source === "table.x");
  expect(disconnectedAfter).toEqual(disconnectedBefore);
  expect(after.topologyKey).toBe(before.topologyKey);
  expect(after.nodes.map((node) => [node.id, node.position])).toEqual(before.nodes.map((node) => [node.id, node.position]));
});

it("preserves exact endpoints while filtering value and control categories", () => {
  const graph = engineGraph([
    { source: ["SRC", "VALUE_COL"], target: ["DST", "VALUE_COL"], kind: "DIRECT" },
    { source: ["SRC", "FILTER_COL"], target: ["DST", "VALUE_COL"], kind: "INDIRECT_FILTER" },
  ]);
  const value = buildCanvasModel(graph, { ...baseOptions, mode: "columns", kind: "VALUE" });
  const filter = buildCanvasModel(graph, { ...baseOptions, mode: "columns", kind: "FILTER" });
  const all = buildCanvasModel(graph, { ...baseOptions, mode: "columns", kind: "all" });

  expect(value.edges).toHaveLength(1);
  expect(value.edges[0]).toMatchObject({
    source: "table.src", target: "table.dst",
    sourceHandle: "column.src.value_col", targetHandle: "column.dst.value_col",
  });
  expect(filter.edges).toHaveLength(1);
  expect(filter.edges[0]).toMatchObject({
    source: "table.src", target: "table.dst",
    sourceHandle: "column.src.filter_col", targetHandle: "column.dst.value_col",
  });
  expect(all.edges).toHaveLength(2);
  expect(new Set(all.edges.map((edge) => `${edge.sourceHandle}->${edge.targetHandle}`))).toEqual(new Set([
    "column.src.value_col->column.dst.value_col",
    "column.src.filter_col->column.dst.value_col",
  ]));
});
