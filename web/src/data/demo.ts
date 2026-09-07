import { parseLineage } from "./adapter";
import type { NormalizedLineageGraph } from "./types";

type DemoRef = { table: string; column?: string; dblink?: string };

function demoEdge(source: DemoRef, target: DemoRef, kind: string, transform: string, line: number) {
  const stage = target.table.startsWith("STAGE.") ? "STAGE" : target.table.startsWith("DWH.") ? "WAREHOUSE" : "MART";
  return {
    sources: [source], target, kind, transform, hops: 1,
    location: { file: `demo/fictional_${stage.toLowerCase()}_load.pkb`, package: `DEMO_${stage}_ETL`, procedure: "LOAD", line },
  };
}

/** Four-stage, fourteen-dataset fictional example. It is not production analysis output. */
export const DEMO_PAYLOAD = {
  metadata: { demo: true, fictional: true, label: "Fictional enterprise lineage demo" },
  edges: [
    demoEdge({ table: "CRM.CUSTOMER", column: "CUSTOMER_ID" }, { table: "STAGE.ORDER_ENRICHED", column: "CUSTOMER_ID" }, "DIRECT", "c.customer_id", 11),
    demoEdge({ table: "ERP.SALES_ORDER", column: "ORDER_ID" }, { table: "STAGE.ORDER_ENRICHED", column: "ORDER_ID" }, "DIRECT", "o.order_id", 12),
    demoEdge({ table: "ERP.SALES_ORDER_LINE", column: "PRODUCT_ID" }, { table: "STAGE.ORDER_ENRICHED", column: "PRODUCT_ID" }, "DIRECT", "l.product_id", 13),
    demoEdge({ table: "ERP.SALES_ORDER_LINE", column: "NET_AMOUNT" }, { table: "STAGE.ORDER_ENRICHED", column: "NET_AMOUNT" }, "DIRECT", "l.net_amount", 14),
    demoEdge({ table: "MDM.PRODUCT", column: "CATEGORY_CODE" }, { table: "STAGE.ORDER_ENRICHED", column: "CATEGORY_CODE" }, "DIRECT", "p.category_code", 15),
    demoEdge({ table: "FIN.INVOICE", column: "CURRENCY_CODE" }, { table: "STAGE.ORDER_ENRICHED", column: "CURRENCY_CODE" }, "DIRECT", "i.currency_code", 16),
    demoEdge({ table: "STAGE.ORDER_ENRICHED", column: "CUSTOMER_ID" }, { table: "DWH.DIM_CUSTOMER", column: "CUSTOMER_KEY" }, "TRANSFORM", "customer_key(customer_id)", 31),
    demoEdge({ table: "STAGE.ORDER_ENRICHED", column: "PRODUCT_ID" }, { table: "DWH.DIM_PRODUCT", column: "PRODUCT_KEY" }, "TRANSFORM", "product_key(product_id)", 32),
    demoEdge({ table: "STAGE.ORDER_ENRICHED", column: "ORDER_ID" }, { table: "DWH.FACT_REVENUE", column: "ORDER_ID" }, "DIRECT", "s.order_id", 33),
    demoEdge({ table: "STAGE.ORDER_ENRICHED", column: "NET_AMOUNT" }, { table: "DWH.FACT_REVENUE", column: "REVENUE_AMOUNT" }, "TRANSFORM", "ROUND(s.net_amount * fx.rate, 2)", 34),
    demoEdge({ table: "REF.FX_RATE", column: "RATE", dblink: "FINANCE_LINK" }, { table: "DWH.FACT_REVENUE", column: "REVENUE_AMOUNT" }, "TRANSFORM", "ROUND(s.net_amount * fx.rate, 2)", 34),
    demoEdge({ table: "SCM.SHIPMENT", column: "DELIVERED_AT" }, { table: "DWH.FACT_FULFILLMENT", column: "DELIVERY_DAYS" }, "TRANSFORM", "delivered_at - shipped_at", 35),
    demoEdge({ table: "DWH.FACT_REVENUE", column: "REVENUE_AMOUNT" }, { table: "MART.EXECUTIVE_KPI", column: "REVENUE_TOTAL" }, "AGGREGATE", "SUM(revenue_amount)", 51),
    demoEdge({ table: "DWH.FACT_FULFILLMENT", column: "DELIVERY_DAYS" }, { table: "MART.EXECUTIVE_KPI", column: "AVG_DELIVERY_DAYS" }, "AGGREGATE", "AVG(delivery_days)", 52),
    demoEdge({ table: "DWH.DIM_CUSTOMER", column: "CUSTOMER_KEY" }, { table: "MART.CUSTOMER_360", column: "CUSTOMER_KEY" }, "DIRECT", "c.customer_key", 53),
    demoEdge({ table: "DWH.FACT_REVENUE", column: "REVENUE_AMOUNT" }, { table: "MART.CUSTOMER_360", column: "LIFETIME_VALUE" }, "AGGREGATE", "SUM(revenue_amount)", 54),
    demoEdge({ table: "DWH.FACT_REVENUE", column: "POSTING_STATUS" }, { table: "MART.EXECUTIVE_KPI" }, "INDIRECT_FILTER", "WHERE posting_status = 'POSTED'", 55),
  ],
  diagnostics: [{ severity: "warning", code: "DEMO_NOTICE", message: "Fictional demonstration data; no production system was analyzed.", location: { file: "demo/README", line: 1 } }],
};

const parsed = parseLineage(DEMO_PAYLOAD, { label: "Fictional enterprise lineage demo", demo: true, fictional: true });
if (!parsed.ok) throw new Error("built-in fictional demo failed validation");
export const DEMO_LINEAGE: NormalizedLineageGraph = parsed.graph;
