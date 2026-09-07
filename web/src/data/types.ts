export type NodeType =
  | "table"
  | "view"
  | "column"
  | "package"
  | "procedure"
  | "function"
  | "parameter"
  | "trigger"
  | "dynamic_statement"
  | "unknown";

export type EdgeCategory = "value" | "control" | "call" | "dynamic" | "other";

export interface SourceRef {
  table: string;
  column?: string;
  dblink?: string;
}

export interface SourceLocation {
  file?: string;
  line?: number;
  package?: string;
  procedure?: string;
  function?: string;
  names?: string[];
}

export interface LineageNode {
  id: string;
  type: NodeType;
  displayName: string;
  datasetId?: string;
  ref?: SourceRef;
  synthetic?: boolean;
}

export interface LineageEdge {
  id: string;
  sourceId: string;
  targetId: string;
  /** Original engine kind or legacy relationship type. */
  kind: string;
  category: EdgeCategory;
  expression: string;
  hops?: number;
  evidence?: SourceLocation;
  sourceRef?: SourceRef;
  targetRef?: SourceRef;
}

export interface LineageDiagnostic {
  severity: string;
  code: string;
  message: string;
  location?: SourceLocation;
  spanText?: string;
}

export interface LineageMetadata {
  label?: string;
  sourceFormat: "engine" | "legacy-viewer";
  demo?: boolean;
  fictional?: boolean;
}

export interface NormalizedLineageGraph {
  metadata: LineageMetadata;
  nodes: LineageNode[];
  edges: LineageEdge[];
  diagnostics: LineageDiagnostic[];
}

export interface ValidationIssue {
  path: string;
  code: string;
  message: string;
}

export type ParseResult =
  | { ok: true; graph: NormalizedLineageGraph; warnings: ValidationIssue[] }
  | { ok: false; errors: ValidationIssue[] };

export interface TraversalBounds {
  maxDepth?: number;
  maxNodes?: number;
  maxEdges?: number;
}

export interface TraversalResult {
  nodeIds: string[];
  edgeIds: string[];
  depthByNode: ReadonlyMap<string, number>;
  truncated: boolean;
}

export interface PathBounds {
  maxDepth?: number;
  maxPaths?: number;
  maxVisited?: number;
}

export interface LineagePath {
  nodeIds: string[];
  edgeIds: string[];
}

export interface PathResult {
  paths: LineagePath[];
  truncated: boolean;
}

export interface DatasetAggregate {
  id: string;
  displayName: string;
  nodeIds: string[];
  columnIds: string[];
  incomingEdgeCount: number;
  outgoingEdgeCount: number;
  diagnosticCount: number;
}
