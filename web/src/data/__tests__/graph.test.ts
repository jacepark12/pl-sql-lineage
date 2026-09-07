import { describe, expect, it } from "vitest";
import { aggregateDatasets, createGraphIndex, findColumnPaths, parseLineage, traverseLineage } from "../index";

function graphFor(edges: Array<[string, string]>) {
  const result = parseLineage({
    objects: [...new Set(edges.flat())].map((id) => ({ id, type: "column", name: id.slice("column.".length) })),
    relationships: edges.map(([source, target]) => ({ source, target, type: "direct", expression: source })),
    diagnostics: [],
  });
  if (!result.ok) throw new Error("test graph failed validation");
  return result.graph;
}

describe("graph helpers", () => {
  it("indexes and traverses upstream/downstream deterministically through cycles", () => {
    const graph = graphFor([
      ["column.a.id", "column.b.id"],
      ["column.b.id", "column.c.id"],
      ["column.c.id", "column.a.id"],
    ]);
    const index = createGraphIndex(graph);
    const downstream = traverseLineage(index, "column.a.id", "downstream");
    expect(downstream.nodeIds).toEqual(["column.a.id", "column.b.id", "column.c.id"]);
    expect(new Set(downstream.edgeIds).size).toBe(3);
    expect(downstream.truncated).toBe(false);
    expect(traverseLineage(index, "column.c.id", "upstream").nodeIds).toEqual(["column.c.id", "column.b.id", "column.a.id"]);
  });

  it("enforces bounds without returning edges whose endpoints were excluded", () => {
    const graph = graphFor([
      ["column.a.id", "column.b.id"],
      ["column.b.id", "column.c.id"],
      ["column.c.id", "column.d.id"],
    ]);
    const index = createGraphIndex(graph);
    const result = traverseLineage(index, "column.a.id", "downstream", { maxNodes: 2, maxEdges: 20, maxDepth: 20 });
    expect(result.nodeIds).toEqual(["column.a.id", "column.b.id"]);
    expect(result.truncated).toBe(true);
    for (const edgeId of result.edgeIds) {
      const edge = index.edgeById.get(edgeId)!;
      expect(result.nodeIds).toContain(edge.sourceId);
      expect(result.nodeIds).toContain(edge.targetId);
    }
  });

  it("finds bounded directed column paths and avoids cycles", () => {
    const graph = graphFor([
      ["column.a.id", "column.b.id"],
      ["column.a.id", "column.c.id"],
      ["column.b.id", "column.d.id"],
      ["column.c.id", "column.d.id"],
      ["column.d.id", "column.a.id"],
    ]);
    const index = createGraphIndex(graph);
    const result = findColumnPaths(index, "column.a.id", "column.d.id", { maxDepth: 4, maxPaths: 10 });
    expect(result.paths.map((path) => path.nodeIds)).toEqual([
      ["column.a.id", "column.b.id", "column.d.id"],
      ["column.a.id", "column.c.id", "column.d.id"],
    ]);
    expect(findColumnPaths(index, "column.a.id", "column.d.id", { maxDepth: 1 }).truncated).toBe(true);
  });

  it("aggregates columns and cross-dataset edge counts", () => {
    const graph = graphFor([
      ["column.erp.orders.id", "column.dwh.fact.order_id"],
      ["column.erp.orders.amount", "column.dwh.fact.amount"],
    ]);
    const aggregates = aggregateDatasets(graph);
    expect(aggregates.map((item) => item.id)).toEqual(["table.dwh.fact", "table.erp.orders"]);
    expect(aggregates[0]).toMatchObject({ incomingEdgeCount: 2, outgoingEdgeCount: 0 });
    expect(aggregates[1]).toMatchObject({ incomingEdgeCount: 0, outgoingEdgeCount: 2 });
    expect(aggregates[1].columnIds).toHaveLength(2);
  });
});
