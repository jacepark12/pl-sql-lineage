import type {
  DatasetAggregate,
  LineageEdge,
  LineagePath,
  NormalizedLineageGraph,
  PathBounds,
  PathResult,
  TraversalBounds,
  TraversalResult,
} from "./types";

export interface GraphIndex {
  nodeById: ReadonlyMap<string, NormalizedLineageGraph["nodes"][number]>;
  edgeById: ReadonlyMap<string, LineageEdge>;
  incomingByNode: ReadonlyMap<string, readonly LineageEdge[]>;
  outgoingByNode: ReadonlyMap<string, readonly LineageEdge[]>;
}

const DEFAULT_MAX_DEPTH = 12;
const DEFAULT_MAX_NODES = 2_000;
const DEFAULT_MAX_EDGES = 5_000;

export function createGraphIndex(graph: NormalizedLineageGraph): GraphIndex {
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const edgeById = new Map(graph.edges.map((edge) => [edge.id, edge]));
  const incomingByNode = new Map<string, LineageEdge[]>();
  const outgoingByNode = new Map<string, LineageEdge[]>();
  for (const edge of graph.edges) {
    append(outgoingByNode, edge.sourceId, edge);
    append(incomingByNode, edge.targetId, edge);
  }
  for (const edges of [...incomingByNode.values(), ...outgoingByNode.values()]) {
    edges.sort((a, b) => a.id.localeCompare(b.id));
  }
  return { nodeById, edgeById, incomingByNode, outgoingByNode };
}

function append(map: Map<string, LineageEdge[]>, key: string, edge: LineageEdge): void {
  const values = map.get(key);
  if (values) values.push(edge);
  else map.set(key, [edge]);
}

export function traverseLineage(
  index: GraphIndex,
  startId: string,
  direction: "upstream" | "downstream",
  bounds: TraversalBounds = {},
): TraversalResult {
  const maxDepth = nonNegativeInt(bounds.maxDepth, DEFAULT_MAX_DEPTH);
  const maxNodes = positiveInt(bounds.maxNodes, DEFAULT_MAX_NODES);
  const maxEdges = positiveInt(bounds.maxEdges, DEFAULT_MAX_EDGES);
  if (!index.nodeById.has(startId)) return { nodeIds: [], edgeIds: [], depthByNode: new Map(), truncated: false };

  const depthByNode = new Map<string, number>([[startId, 0]]);
  const edgeIds: string[] = [];
  const seenEdges = new Set<string>();
  const queue = [startId];
  let cursor = 0;
  let truncated = false;

  while (cursor < queue.length) {
    const nodeId = queue[cursor++];
    const depth = depthByNode.get(nodeId) ?? 0;
    const adjacent = direction === "upstream" ? index.incomingByNode.get(nodeId) : index.outgoingByNode.get(nodeId);
    if (!adjacent?.length) continue;
    if (depth >= maxDepth) {
      truncated = true;
      continue;
    }
    for (const edge of adjacent) {
      if (seenEdges.has(edge.id)) continue;
      if (edgeIds.length >= maxEdges) {
        truncated = true;
        break;
      }
      const nextId = direction === "upstream" ? edge.sourceId : edge.targetId;
      if (!depthByNode.has(nextId)) {
        if (depthByNode.size >= maxNodes) {
          truncated = true;
          continue;
        }
        depthByNode.set(nextId, depth + 1);
        queue.push(nextId);
      }
      seenEdges.add(edge.id);
      edgeIds.push(edge.id);
    }
  }
  return { nodeIds: [...depthByNode.keys()], edgeIds, depthByNode, truncated };
}

export function findColumnPaths(
  index: GraphIndex,
  sourceId: string,
  targetId: string,
  bounds: PathBounds = {},
): PathResult {
  const source = index.nodeById.get(sourceId);
  const target = index.nodeById.get(targetId);
  if (source?.type !== "column" || target?.type !== "column") return { paths: [], truncated: false };
  const maxDepth = nonNegativeInt(bounds.maxDepth, DEFAULT_MAX_DEPTH);
  const maxPaths = positiveInt(bounds.maxPaths, 20);
  const maxVisited = positiveInt(bounds.maxVisited, 10_000);
  const paths: LineagePath[] = [];
  const stack: Array<{ nodeId: string; nodeIds: string[]; edgeIds: string[] }> = [
    { nodeId: sourceId, nodeIds: [sourceId], edgeIds: [] },
  ];
  let visited = 0;
  let truncated = false;

  while (stack.length) {
    const state = stack.pop()!;
    visited += 1;
    if (visited > maxVisited) {
      truncated = true;
      break;
    }
    if (state.nodeId === targetId) {
      paths.push({ nodeIds: state.nodeIds, edgeIds: state.edgeIds });
      if (paths.length >= maxPaths) {
        truncated = stack.length > 0;
        break;
      }
      continue;
    }
    const outgoing = index.outgoingByNode.get(state.nodeId) ?? [];
    if (state.edgeIds.length >= maxDepth) {
      if (outgoing.length) truncated = true;
      continue;
    }
    // Reverse push preserves stable ascending edge order for DFS output.
    for (let indexPosition = outgoing.length - 1; indexPosition >= 0; indexPosition -= 1) {
      const edge = outgoing[indexPosition];
      if (state.nodeIds.includes(edge.targetId)) continue;
      stack.push({
        nodeId: edge.targetId,
        nodeIds: [...state.nodeIds, edge.targetId],
        edgeIds: [...state.edgeIds, edge.id],
      });
    }
  }
  return { paths, truncated };
}

export function aggregateDatasets(graph: NormalizedLineageGraph, index = createGraphIndex(graph)): DatasetAggregate[] {
  const aggregates = new Map<string, DatasetAggregate>();
  for (const node of graph.nodes) {
    const datasetId = node.datasetId ?? (node.type === "table" || node.type === "view" ? node.id : undefined);
    if (!datasetId) continue;
    let aggregate = aggregates.get(datasetId);
    if (!aggregate) {
      const datasetNode = index.nodeById.get(datasetId);
      aggregate = {
        id: datasetId,
        displayName: datasetNode?.displayName ?? node.ref?.table?.toUpperCase() ?? datasetId,
        nodeIds: [], columnIds: [], incomingEdgeCount: 0, outgoingEdgeCount: 0, diagnosticCount: 0,
      };
      aggregates.set(datasetId, aggregate);
    }
    aggregate.nodeIds.push(node.id);
    if (node.type === "column") aggregate.columnIds.push(node.id);
  }
  for (const edge of graph.edges) {
    const sourceDataset = index.nodeById.get(edge.sourceId)?.datasetId;
    const targetDataset = index.nodeById.get(edge.targetId)?.datasetId;
    if (sourceDataset !== targetDataset) {
      const source = sourceDataset ? aggregates.get(sourceDataset) : undefined;
      const target = targetDataset ? aggregates.get(targetDataset) : undefined;
      if (source) source.outgoingEdgeCount += 1;
      if (target) target.incomingEdgeCount += 1;
    }
  }
  for (const aggregate of aggregates.values()) {
    aggregate.nodeIds.sort();
    aggregate.columnIds.sort();
  }
  return [...aggregates.values()].sort((a, b) => a.id.localeCompare(b.id));
}

function positiveInt(value: number | undefined, fallback: number): number {
  return value !== undefined && Number.isInteger(value) && value > 0 ? value : fallback;
}

function nonNegativeInt(value: number | undefined, fallback: number): number {
  return value !== undefined && Number.isInteger(value) && value >= 0 ? value : fallback;
}
