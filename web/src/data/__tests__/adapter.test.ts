import { describe, expect, it } from "vitest";
import { DEMO_LINEAGE, DEMO_PAYLOAD, parseLineage } from "../index";
import engineFixture from "../../../../plsql-lineage-engine/tests/fixtures/engine_sample.json";
import viewerFixture from "../../../../plsql-lineage-engine/tests/fixtures/viewer_sample.json";

describe("parseLineage", () => {
  it("normalizes the repository engine fixture while retaining evidence", () => {
    const result = parseLineage(engineFixture);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.graph.metadata.sourceFormat).toBe("engine");
    expect(result.graph.edges.length).toBeGreaterThan(0);
    expect(result.graph.edges.some((edge) => edge.expression.length > 0)).toBe(true);
    expect(result.graph.edges.some((edge) => edge.evidence?.file && edge.evidence.line)).toBe(true);
    expect(result.graph.diagnostics.every((item) => typeof item.message === "string")).toBe(true);
  });

  it("normalizes the repository legacy viewer fixture", () => {
    const result = parseLineage(viewerFixture);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.graph.metadata.sourceFormat).toBe("legacy-viewer");
    expect(result.graph.nodes.length).toBeGreaterThan(0);
    expect(result.graph.edges.every((edge) => edge.sourceId && edge.targetId)).toBe(true);
  });

  it("preserves DB links, kinds, expressions, hops, and diagnostic locations", () => {
    const result = parseLineage({
      edges: [{
        sources: [{ table: "FIN.RATES", column: "RATE", dblink: "REMOTE_FIN" }],
        target: { table: "DWH.FACT", column: "AMOUNT" },
        kind: "VIA_PIPELINE", transform: "amount * rate", hops: 3,
        location: { file: "load.pkb", package: "ETL", procedure: "LOAD", line: 27 },
      }],
      diagnostics: [{ severity: "warning", code: "CHECK", message: "review", location: { file: "load.pkb", line: 27 } }],
    });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const edge = result.graph.edges[0];
    expect(edge.sourceId).toBe("column.fin.rates@remote_fin.rate");
    expect(edge.sourceRef?.dblink).toBe("REMOTE_FIN");
    expect(edge).toMatchObject({ kind: "VIA_PIPELINE", category: "value", expression: "amount * rate", hops: 3 });
    expect(edge.evidence).toMatchObject({ file: "load.pkb", package: "ETL", procedure: "LOAD", line: 27 });
    expect(result.graph.diagnostics[0].spanText).toBe("load.pkb:27");
  });

  it("returns safe validation errors without reflecting input values", () => {
    const secret = "do-not-reflect-this";
    const result = parseLineage({ objects: [{ id: secret }], relationships: "bad" });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(JSON.stringify(result.errors)).not.toContain(secret);
    expect(result.errors[0]).toMatchObject({ path: "relationships", code: "invalid_type" });
  });

  it("ships an explicitly fictional, deterministic multi-dataset demo", () => {
    expect(DEMO_LINEAGE.metadata).toMatchObject({ demo: true, fictional: true });
    expect(new Set(DEMO_LINEAGE.nodes.map((node) => node.datasetId).filter(Boolean)).size).toBe(14);
    expect(DEMO_LINEAGE.diagnostics.some((item) => item.code === "DEMO_NOTICE")).toBe(true);
  });
});

it("retains fictional provenance when the exported demo is reimported", () => {
  const result = parseLineage(JSON.parse(JSON.stringify(DEMO_PAYLOAD)), { label: "uploaded.json" });
  expect(result.ok).toBe(true);
  if (result.ok) expect(result.graph.metadata).toMatchObject({ demo: true, fictional: true });
});
