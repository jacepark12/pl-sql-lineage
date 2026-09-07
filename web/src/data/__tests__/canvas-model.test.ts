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
  expect(model.edges[0].targetHandle).toBe("column.t.clean");
});
