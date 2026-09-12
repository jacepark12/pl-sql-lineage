import { describe, expect, it } from "vitest";
import { fqnToNodeId } from "../data/adapter";
import { graphsMatch, parseFocusEvent, parseLiveOrigin } from "../live";

describe("parseLiveOrigin", () => {
  it("accepts loopback http origins", () => {
    expect(parseLiveOrigin("?live=http://127.0.0.1:8765")).toBe("http://127.0.0.1:8765");
    expect(parseLiveOrigin("live=http://localhost:8765/")).toBe("http://localhost:8765");
  });

  it("rejects non-loopback hosts", () => {
    expect(parseLiveOrigin("?live=http://0.0.0.0:8765")).toBeNull();
    expect(parseLiveOrigin("?live=https://example.com")).toBeNull();
    expect(parseLiveOrigin("")).toBeNull();
  });
});

describe("fqnToNodeId", () => {
  it("maps schema.table.column and table.*", () => {
    expect(fqnToNodeId("SYNWMS.OUT_ALLOC.ORD_QTY")).toBe("column.synwms.out_alloc.ord_qty");
    expect(fqnToNodeId("SYNWMS.OUT_ALLOC.*")).toBe("table.synwms.out_alloc");
    expect(fqnToNodeId("FIN.RATES@REMOTE_FIN.RATE")).toBe("column.fin.rates@remote_fin.rate");
    expect(fqnToNodeId("(unresolved)")).toBeNull();
  });
});

describe("parseFocusEvent", () => {
  it("keeps columns and edges", () => {
    const focus = parseFocusEvent({
      v: 1,
      tool: "query_lineage",
      seed: "SYNWMS.OUT_ALLOC.ORD_QTY",
      columns: ["SYNWMS.OUT_ALLOC.ORD_QTY", "SYNWMS.OUT_ORDER_D.ORD_QTY"],
      edges: [{ kind: "DIRECT", source: "SYNWMS.OUT_ORDER_D.ORD_QTY", target: "SYNWMS.OUT_ALLOC.ORD_QTY" }],
      graph: "sha256:abc",
    });
    expect(focus?.seed).toBe("SYNWMS.OUT_ALLOC.ORD_QTY");
    expect(focus?.edges).toHaveLength(1);
    expect(graphsMatch("sha256:abc", focus?.graph ?? null)).toBe(true);
    expect(graphsMatch("sha256:abc", "sha256:def")).toBe(false);
  });
});
