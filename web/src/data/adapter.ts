import type {
  EdgeCategory,
  LineageDiagnostic,
  LineageEdge,
  LineageMetadata,
  LineageNode,
  NodeType,
  NormalizedLineageGraph,
  ParseResult,
  SourceLocation,
  SourceRef,
  ValidationIssue,
} from "./types";

const VALUE_KINDS = new Set([
  "DIRECT", "TRANSFORM", "AGGREGATE", "ANALYTIC", "VIA_VARIABLE", "VIA_CTE", "VIA_PIPELINE",
]);
const CONTROL_KINDS = new Set(["INDIRECT", "INDIRECT_FILTER", "FILTER"]);
const DYNAMIC_KINDS = new Set(["UNRESOLVED", "DYNAMIC", "DYNAMIC_SQL", "EXECUTE_IMMEDIATE"]);
const NODE_TYPES = new Set([
  "table", "view", "column", "package", "procedure", "function", "parameter", "trigger", "dynamic_statement",
]);

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function finiteNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function categoryFor(kind: string): EdgeCategory {
  const folded = kind.trim().toUpperCase();
  if (VALUE_KINDS.has(folded) || folded === "DIRECT") return "value";
  if (CONTROL_KINDS.has(folded) || folded.startsWith("INDIRECT")) return "control";
  if (folded === "CALL") return "call";
  if (DYNAMIC_KINDS.has(folded) || folded.includes("DYNAMIC")) return "dynamic";
  return "other";
}

function normalizeRef(value: unknown): SourceRef | undefined {
  if (!isObject(value)) return undefined;
  const table = text(value.table);
  if (!table) return undefined;
  const result: SourceRef = { table };
  const column = text(value.column);
  const dblink = text(value.dblink);
  if (column) result.column = column;
  if (dblink) result.dblink = dblink;
  return result;
}

function tableSpelling(ref: SourceRef): string {
  return ref.dblink && !ref.table.includes("@") ? `${ref.table}@${ref.dblink}` : ref.table;
}

function idPart(value: string): string {
  return value.trim().toLowerCase();
}

export function refNodeId(ref: SourceRef): string {
  const table = tableSpelling(ref);
  return ref.column
    ? `column.${idPart(table)}.${idPart(ref.column)}`
    : `table.${idPart(table)}`;
}

/** Map an engine FQN (`SCHEMA.TABLE.COL`, `TABLE.*`, `T@DBLINK.COL`) to a viewer node id. */
export function fqnToNodeId(fqn: string): string | null {
  const trimmed = fqn.trim();
  if (!trimmed || trimmed === "(unresolved)") return null;
  const lastDot = trimmed.lastIndexOf(".");
  if (lastDot <= 0) return null;
  const table = trimmed.slice(0, lastDot);
  const column = trimmed.slice(lastDot + 1);
  if (!table) return null;
  if (column === "*") return `table.${idPart(table)}`;
  return refNodeId({ table, column });
}

function datasetIdForRef(ref: SourceRef): string {
  return `table.${idPart(tableSpelling(ref))}`;
}

function nodeFromRef(ref: SourceRef): LineageNode {
  const dataset = tableSpelling(ref);
  return {
    id: refNodeId(ref),
    type: ref.column ? "column" : "table",
    displayName: ref.column ? `${dataset}.${ref.column}`.toUpperCase() : dataset.toUpperCase(),
    datasetId: datasetIdForRef(ref),
    ref,
  };
}

function datasetNodeFromRef(ref: SourceRef): LineageNode {
  const dataset = tableSpelling(ref);
  const datasetRef: SourceRef = ref.dblink ? { table: ref.table, dblink: ref.dblink } : { table: ref.table };
  return {
    id: datasetIdForRef(ref),
    type: "table",
    displayName: dataset.toUpperCase(),
    datasetId: datasetIdForRef(ref),
    ref: datasetRef,
  };
}

function putRefNodes(nodes: Map<string, LineageNode>, ref: SourceRef): LineageNode {
  const datasetNode = datasetNodeFromRef(ref);
  nodes.set(datasetNode.id, datasetNode);
  const endpointNode = nodeFromRef(ref);
  nodes.set(endpointNode.id, endpointNode);
  return endpointNode;
}

function normalizeLocation(value: unknown): SourceLocation | undefined {
  if (!isObject(value)) return undefined;
  const location: SourceLocation = {};
  for (const key of ["file", "package", "procedure", "function"] as const) {
    const parsed = text(value[key]);
    if (parsed) location[key] = parsed;
  }
  const line = finiteNumber(value.line);
  if (line !== undefined) location.line = line;
  if (Array.isArray(value.names)) {
    const names = value.names.map(text).filter((item): item is string => Boolean(item));
    if (names.length) location.names = names;
  }
  return Object.keys(location).length ? location : undefined;
}

function locationSpan(location: SourceLocation | undefined): string | undefined {
  if (!location) return undefined;
  const at = location.file
    ? `${location.file}${location.line === undefined ? "" : `:${location.line}`}`
    : location.line === undefined ? "" : String(location.line);
  const routine = [location.package, location.function ?? location.procedure].filter(Boolean).join(".");
  return [at, routine].filter(Boolean).join(" ") || undefined;
}

function normalizeDiagnostic(value: unknown): LineageDiagnostic | undefined {
  if (!isObject(value)) return undefined;
  const location = normalizeLocation(value.location ?? value.span);
  const diagnostic: LineageDiagnostic = {
    severity: text(value.severity) ?? "",
    code: text(value.code) ?? "",
    message: text(value.message) ?? "",
  };
  if (location) diagnostic.location = location;
  const spanText = text(value.spanText) ?? locationSpan(location);
  if (spanText) diagnostic.spanText = spanText;
  return diagnostic;
}

function programNodes(location: SourceLocation | undefined): LineageNode[] {
  if (!location?.package) return [];
  const pkg = location.package;
  const result: LineageNode[] = [{ id: `package.${idPart(pkg)}`, type: "package", displayName: pkg.toUpperCase() }];
  const routine = location.function ?? location.procedure;
  if (routine) {
    const type: NodeType = location.function ? "function" : "procedure";
    result.push({ id: `${type}.${idPart(pkg)}.${idPart(routine)}`, type, displayName: `${pkg}.${routine}`.toUpperCase() });
  }
  return result;
}

function dynamicNode(location: SourceLocation | undefined, expression: string): LineageNode {
  const routine = location?.function ?? location?.procedure;
  const suffix = location?.package || routine
    ? [location?.package, routine, location?.line].filter((item) => item !== undefined && item !== "").map(String).join(".")
    : location?.file
      ? `${location.file.replace(/\\/g, "/").split("/").pop()}.${location.line ?? ""}`
      : "unknown";
  return {
    id: `dynamic_statement.${idPart(suffix)}`,
    type: "dynamic_statement",
    displayName: expression || [location?.package, routine].filter(Boolean).join(".") || location?.file || "DYNAMIC SQL",
    synthetic: true,
  };
}

function stableEdgeId(edge: Omit<LineageEdge, "id">, ordinal: number): string {
  const fingerprint = [edge.kind, edge.sourceId, edge.targetId, edge.expression, String(ordinal)].join("|");
  let hash = 2166136261;
  for (let index = 0; index < fingerprint.length; index += 1) {
    hash ^= fingerprint.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `edge.${String(ordinal).padStart(6, "0")}.${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function fromEngine(data: JsonObject, metadata: LineageMetadata): ParseResult {
  if (!Array.isArray(data.edges)) return failure("edges", "invalid_type", "edges must be an array");
  const warnings: ValidationIssue[] = [];
  const nodes = new Map<string, LineageNode>();
  const edges: LineageEdge[] = [];

  data.edges.forEach((value, edgeIndex) => {
    if (!isObject(value)) {
      warnings.push(issue(`edges[${edgeIndex}]`, "invalid_edge", "edge was skipped because it is not an object"));
      return;
    }
    const targetRef = normalizeRef(value.target);
    if (!targetRef) {
      warnings.push(issue(`edges[${edgeIndex}].target`, "invalid_ref", "edge was skipped because target.table is required"));
      return;
    }
    const kind = text(value.kind) ?? "DIRECT";
    const expression = text(value.transform) ?? "";
    const evidence = normalizeLocation(value.location);
    const targetNode = putRefNodes(nodes, targetRef);
    for (const node of programNodes(evidence)) nodes.set(node.id, node);

    const sources = Array.isArray(value.sources) ? value.sources : [];
    const normalizedSources = sources.map(normalizeRef).filter((item): item is SourceRef => Boolean(item));
    if (sources.length !== normalizedSources.length) {
      warnings.push(issue(`edges[${edgeIndex}].sources`, "invalid_ref", "one or more sources without table were skipped"));
    }
    if (!normalizedSources.length && categoryFor(kind) === "dynamic") {
      const sourceNode = dynamicNode(evidence, expression);
      nodes.set(sourceNode.id, sourceNode);
      addEdge(edges, { sourceId: sourceNode.id, targetId: targetNode.id, kind, category: categoryFor(kind), expression, hops: finiteNumber(value.hops), evidence, targetRef });
      return;
    }
    for (const sourceRef of normalizedSources) {
      const sourceNode = putRefNodes(nodes, sourceRef);
      addEdge(edges, { sourceId: sourceNode.id, targetId: targetNode.id, kind, category: categoryFor(kind), expression, hops: finiteNumber(value.hops), evidence, sourceRef, targetRef });
    }
  });

  return success(metadata, nodes, edges, data.diagnostics, warnings);
}

function inferLegacyRef(node: JsonObject): SourceRef | undefined {
  const explicit = normalizeRef(node.ref);
  if (explicit) return explicit;
  const type = text(node.type);
  const name = text(node.name);
  if (!name || (type !== "table" && type !== "column")) return undefined;
  if (type === "table") return { table: name };
  const lastDot = name.lastIndexOf(".");
  return lastDot > 0 ? { table: name.slice(0, lastDot), column: name.slice(lastDot + 1) } : undefined;
}

function fromLegacy(data: JsonObject, metadata: LineageMetadata): ParseResult {
  if (!Array.isArray(data.objects)) return failure("objects", "invalid_type", "objects must be an array");
  if (!Array.isArray(data.relationships)) return failure("relationships", "invalid_type", "relationships must be an array");
  const warnings: ValidationIssue[] = [];
  const nodes = new Map<string, LineageNode>();
  data.objects.forEach((value, index) => {
    if (!isObject(value)) {
      warnings.push(issue(`objects[${index}]`, "invalid_node", "object was skipped because it is not an object"));
      return;
    }
    const id = text(value.id);
    if (!id) {
      warnings.push(issue(`objects[${index}].id`, "required", "object was skipped because id is required"));
      return;
    }
    const rawType = text(value.type) ?? "unknown";
    const type = (NODE_TYPES.has(rawType) ? rawType : "unknown") as NodeType;
    const ref = inferLegacyRef(value);
    const node: LineageNode = { id, type, displayName: text(value.name) ?? id };
    if (ref) {
      node.ref = ref;
      node.datasetId = type === "table" || type === "view" ? id : datasetIdForRef(ref);
    }
    nodes.set(id, node);
  });

  const containers = [...nodes.values()].filter((node) => node.type === "table" || node.type === "view");
  for (const node of nodes.values()) {
    if (node.type !== "column") continue;
    const owner = containers
      .filter((candidate) => node.displayName.toUpperCase().startsWith(`${candidate.displayName.toUpperCase()}.`))
      .sort((a, b) => b.displayName.length - a.displayName.length)[0];
    if (owner) node.datasetId = owner.id;
  }

  const edges: LineageEdge[] = [];
  data.relationships.forEach((value, index) => {
    if (!isObject(value)) {
      warnings.push(issue(`relationships[${index}]`, "invalid_edge", "relationship was skipped because it is not an object"));
      return;
    }
    const sourceId = text(value.source);
    const targetId = text(value.target);
    if (!sourceId || !targetId) {
      warnings.push(issue(`relationships[${index}]`, "required", "relationship was skipped because source and target are required"));
      return;
    }
    for (const endpoint of [sourceId, targetId]) {
      if (!nodes.has(endpoint)) nodes.set(endpoint, { id: endpoint, type: "unknown", displayName: endpoint, synthetic: true });
    }
    const kind = text(value.kind) ?? text(value.type) ?? "direct";
    const sourceRef = nodes.get(sourceId)?.ref;
    const targetRef = nodes.get(targetId)?.ref;
    addEdge(edges, {
      sourceId, targetId, kind, category: categoryFor(kind), expression: text(value.expression) ?? text(value.transform) ?? "",
      hops: finiteNumber(value.hops), evidence: normalizeLocation(value.location ?? value.evidence), sourceRef, targetRef,
    });
  });
  return success(metadata, nodes, edges, data.diagnostics, warnings);
}

function addEdge(edges: LineageEdge[], edge: Omit<LineageEdge, "id">): void {
  const cleaned = Object.fromEntries(Object.entries(edge).filter(([, value]) => value !== undefined)) as unknown as Omit<LineageEdge, "id">;
  edges.push({ id: stableEdgeId(cleaned, edges.length), ...cleaned });
}

function success(metadata: LineageMetadata, nodes: Map<string, LineageNode>, edges: LineageEdge[], rawDiagnostics: unknown, warnings: ValidationIssue[]): ParseResult {
  const diagnostics = Array.isArray(rawDiagnostics)
    ? rawDiagnostics.map(normalizeDiagnostic).filter((item): item is LineageDiagnostic => Boolean(item))
    : [];
  if (rawDiagnostics !== undefined && !Array.isArray(rawDiagnostics)) warnings.push(issue("diagnostics", "invalid_type", "diagnostics was ignored because it is not an array"));
  return {
    ok: true,
    graph: {
      metadata,
      nodes: [...nodes.values()].sort((a, b) => a.id.localeCompare(b.id)),
      edges: edges.sort((a, b) => a.id.localeCompare(b.id)),
      diagnostics,
    },
    warnings,
  };
}

function issue(path: string, code: string, message: string): ValidationIssue {
  return { path, code, message };
}

function failure(path: string, code: string, message: string): ParseResult {
  return { ok: false, errors: [issue(path, code, message)] };
}

/** Parse untrusted uploaded JSON without exposing its values in validation errors. */
export function parseLineage(input: unknown, metadata: Partial<LineageMetadata> = {}): ParseResult {
  if (!isObject(input)) return failure("$", "invalid_type", "lineage input must be an object");
  const saved = isObject(input.metadata) ? input.metadata : {};
  const provenance = { demo: saved.demo === true, fictional: saved.fictional === true };
  if ("edges" in input) return fromEngine(input, { ...provenance, ...metadata, sourceFormat: "engine" });
  if ("objects" in input || "relationships" in input) return fromLegacy(input, { ...provenance, ...metadata, sourceFormat: "legacy-viewer" });
  return failure("$", "unsupported_format", "expected an engine graph or legacy viewer graph");
}
