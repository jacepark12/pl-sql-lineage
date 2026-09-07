import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type MouseEvent } from "react";
import dagre from "@dagrejs/dagre";
import { LayoutGrid, Table2 } from "lucide-react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  applyNodeChanges,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./graph.css";
import { aggregateDatasets, createGraphIndex, traverseLineage } from "./data";
import type { EdgeCategory, LineageNode, NormalizedLineageGraph } from "./data";

export interface GraphCanvasProps {
  graph: NormalizedLineageGraph;
  selectedId: string | null;
  scopeId: string | null;
  onSelect: (id: string | null) => void;
  onInspect: (id: string) => void;
  onExplore: (id: string, direction: "upstream" | "downstream" | "all") => void;
  mode: "datasets" | "columns";
  direction: "all" | "upstream" | "downstream";
  depth: number;
  kind: "VALUE" | "FILTER" | "all";
  query: string;
}

interface DatasetCardData extends Record<string, unknown> {
  id: string;
  label: string;
  type: string;
  schema: string;
  columns: LineageNode[];
  hiddenColumnCount: number;
  expanded: boolean;
  selectedId: string | null;
  matchedIds: ReadonlySet<string>;
  onSelect: (id: string) => void;
  onContextMenu: (id: string, event: MouseEvent | KeyboardEvent) => void;
}

const MAX_VISIBLE_NODES = 160;
const MAX_VISIBLE_EDGES = 500;
const CARD_WIDTH = 236;
const COMPACT_HEIGHT = 76;
const ROW_HEIGHT = 28;
const MAX_COLUMNS_PER_CARD = 16;

function DatasetCard({ data }: NodeProps<Node<DatasetCardData>>) {
  const selected = data.selectedId === data.id;
  const matched = data.matchedIds.has(data.id);
  const select = () => data.onSelect(data.id);
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ContextMenu" || (event.key === "F10" && event.shiftKey)) {
      event.preventDefault(); data.onContextMenu(data.id, event); return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select();
    }
  };
  return (
    <div
      className={`dataset-card dataset-card--${data.type} ${selected ? "is-selected" : ""} ${matched ? "is-match" : ""}`}
      tabIndex={0}
      role="button"
      aria-label={`${data.label}, ${data.columns.length} columns`}
      onClick={select}
      onKeyDown={onKeyDown}
      onContextMenu={(event) => { event.preventDefault(); data.onContextMenu(data.id, event); }}
    >
      <Handle type="target" position={Position.Left} className="dataset-handle" />
      <div className="dataset-card__header">
        <span className="dataset-card__icon" aria-hidden="true"><Table2 size={15} /></span>
        <span className="dataset-card__title" title={data.label}>{data.label}</span>
        <span className="dataset-card__count">{data.columns.length}</span>
      </div>
      <div className="dataset-card__meta"><span>{data.schema}</span><span>{data.type} · {data.columns.length} columns</span></div>
      {data.expanded && (
        <div className="dataset-card__columns">
          {data.columns.map((column) => {
            const columnSelected = data.selectedId === column.id;
            const columnMatched = data.matchedIds.has(column.id);
            return (
              <button
                type="button"
                key={column.id}
                className={`dataset-column ${columnSelected ? "is-selected" : ""} ${columnMatched ? "is-match" : ""}`}
                onClick={(event) => { event.stopPropagation(); data.onSelect(column.id); }}
                onContextMenu={(event) => { event.preventDefault(); event.stopPropagation(); data.onContextMenu(column.id, event); }}
                onKeyDown={(event) => { event.stopPropagation(); if (event.key === "ContextMenu" || (event.key === "F10" && event.shiftKey)) { event.preventDefault(); data.onContextMenu(column.id, event); } }}
                title={column.displayName}
                aria-label={column.displayName}
              >
                <Handle id={column.id} type="target" position={Position.Left} className="column-handle" />
                <span>{column.ref?.column ?? column.displayName.split(".").at(-1) ?? column.displayName}</span>
                <Handle id={column.id} type="source" position={Position.Right} className="column-handle" />
              </button>
            );
          })}
          {data.hiddenColumnCount > 0 && <div className="dataset-column-overflow">+{data.hiddenColumnCount} more columns</div>}
        </div>
      )}
      <Handle type="source" position={Position.Right} className="dataset-handle" />
    </div>
  );
}

const nodeTypes = { datasetCard: DatasetCard };

function categoryFor(kind: GraphCanvasProps["kind"]): EdgeCategory | null {
  if (kind === "VALUE") return "value";
  if (kind === "FILTER") return "control";
  return null;
}

export function GraphCanvas({ graph, selectedId, scopeId, onSelect, onInspect, onExplore, mode, direction, depth, kind, query }: GraphCanvasProps) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuTriggerRef = useRef<HTMLElement | null>(null);
  const [flow, setFlow] = useState<ReactFlowInstance<Node<DatasetCardData>, Edge> | null>(null);
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const openMenu = useCallback((id: string, event: MouseEvent | KeyboardEvent) => {
    event.preventDefault();
    event.stopPropagation();
    menuTriggerRef.current = event.currentTarget as HTMLElement;
    onSelect(id);
    const bounds = canvasRef.current?.getBoundingClientRect();
    const mouse = "clientX" in event;
    const trigger = event.currentTarget.getBoundingClientRect();
    const x = (mouse ? event.clientX : trigger.left + 16) - (bounds?.left ?? 0);
    const y = (mouse ? event.clientY : trigger.bottom) - (bounds?.top ?? 0);
    setMenu({ id, x: Math.max(8, Math.min(x, (bounds?.width ?? 300) - 210)), y: Math.max(8, Math.min(y, (bounds?.height ?? 300) - 244)) });
  }, [onSelect]);
  const model = useMemo(
    () => buildCanvasModel(graph, { selectedId, scopeId, mode, direction, depth, kind, query, onSelect, onInspect, onExplore, onContextMenu: openMenu }),
    [graph, selectedId, scopeId, mode, direction, depth, kind, query, onSelect, onInspect, onExplore, openMenu],
  );
  const [nodes, setNodes] = useState(model.nodes);
  useEffect(() => {
    setNodes((current) => {
      const currentById = new Map(current.map((node) => [node.id, node]));
      const sameTopology = current.length === model.nodes.length && model.nodes.every((node) => {
        const previous = currentById.get(node.id);
        return previous && previous.width === node.width && previous.height === node.height;
      });
      if (!sameTopology) return model.nodes;
      return model.nodes.map((node) => ({ ...node, position: currentById.get(node.id)!.position }));
    });
  }, [model.nodes]);
  const onNodesChange = (changes: NodeChange<Node<DatasetCardData>>[]) => {
    setNodes((current) => applyNodeChanges(changes, current));
  };
  useEffect(() => {
    if (!menu) return;
    const dismiss = (event: globalThis.MouseEvent) => { if (!menuRef.current?.contains(event.target as globalThis.Node)) setMenu(null); };
    window.addEventListener("mousedown", dismiss);
    return () => window.removeEventListener("mousedown", dismiss);
  }, [menu]);
  useEffect(() => { if (menu) requestAnimationFrame(() => (menuRef.current?.querySelector("button") as HTMLButtonElement | null)?.focus()); }, [menu]);

  const copy = async (value: string, label: string) => {
    try { await navigator.clipboard.writeText(value); setCopyStatus(`${label} copied`); }
    catch { setCopyStatus(`Could not copy ${label.toLowerCase()}`); }
    setMenu(null); window.setTimeout(() => setCopyStatus(null), 1800);
  };
  const centerMenuNode = () => {
    if (!menu || !flow) return;
    const node = nodes.find((candidate) => candidate.id === (model.datasetByNode.get(menu.id) ?? menu.id));
    if (node) void flow.setCenter(node.position.x + CARD_WIDTH / 2, node.position.y + (node.height ?? COMPACT_HEIGHT) / 2, { zoom: 1.15, duration: 300 });
    setMenu(null);
  };
  const menuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = [...(menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])];
    const current = items.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "Escape" || event.key === "Tab") {
      event.preventDefault(); event.stopPropagation(); setMenu(null);
      menuTriggerRef.current?.focus({ preventScroll: true }); return;
    }
    let next = current;
    if (event.key === "ArrowDown") next = (current + 1) % items.length;
    else if (event.key === "ArrowUp") next = (current - 1 + items.length) % items.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = items.length - 1;
    else return;
    event.preventDefault(); items[next]?.focus();
  };

  if (!graph.nodes.length) {
    return <div className="graph-empty"><div className="graph-empty__icon">⌁</div><strong>No lineage loaded</strong><span>Import an engine JSON file to explore its datasets.</span></div>;
  }

  return (
    <div className="graph-canvas" data-testid="graph-canvas" ref={canvasRef}>
      {model.truncated && (
        <div className="graph-truncation" role="status">
          Showing {model.nodes.length} datasets and {model.edges.length} connections. Refine the search or selection to see more.
        </div>
      )}
      <button type="button" className="graph-layout-reset" onClick={() => setNodes(model.nodes)} title="Restore automatic layout" aria-label="Restore automatic layout"><LayoutGrid size={14} /></button>
      <ReactFlow
        key={model.topologyKey}
        nodes={nodes}
        edges={model.edges}
        nodeTypes={nodeTypes}
        onInit={setFlow}
        onNodesChange={onNodesChange}
        onPaneClick={() => onSelect(null)}
        fitView
        fitViewOptions={{ padding: 0.18, maxZoom: 1.15 }}
        minZoom={0.18}
        maxZoom={1.8}
        nodesConnectable={false}
        deleteKeyCode={null}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#cbd3dc" />
        <MiniMap position="bottom-left" pannable zoomable nodeStrokeWidth={2} nodeColor="#d7dee7" maskColor="rgba(241,244,247,.72)" />
        <Controls position="bottom-left" showInteractive={false} />
      </ReactFlow>
      {menu && <div className="graph-context-menu" ref={menuRef} role="menu" aria-label="Node actions" style={{ left: menu.x, top: menu.y }} onKeyDown={menuKeyDown}>
        <button role="menuitem" onClick={() => { onInspect(menu.id); setMenu(null); }}>View details</button>
        <div className="graph-context-separator" />
        <button role="menuitem" onClick={() => { onExplore(menu.id, "upstream"); setMenu(null); }}>Show upstream only</button>
        <button role="menuitem" onClick={() => { onExplore(menu.id, "downstream"); setMenu(null); }}>Show downstream only</button>
        <button role="menuitem" onClick={() => { onExplore(menu.id, "all"); setMenu(null); }}>Show all resources</button>
        <div className="graph-context-separator" />
        <button role="menuitem" onClick={centerMenuNode}>Center node</button>
        <button role="menuitem" onClick={() => void copy(model.nameById.get(menu.id) ?? menu.id, "Name")}>Copy name</button>
        <button role="menuitem" onClick={() => void copy(menu.id, "ID")}>Copy ID</button>
      </div>}
      {copyStatus && <div className="graph-copy-status" role="status">{copyStatus}</div>}
    </div>
  );
}

export interface BuildOptions extends Pick<GraphCanvasProps, "selectedId" | "scopeId" | "mode" | "direction" | "depth" | "kind" | "query"> {
  onSelect?: GraphCanvasProps["onSelect"];
  onInspect?: GraphCanvasProps["onInspect"];
  onExplore?: GraphCanvasProps["onExplore"];
  onContextMenu?: DatasetCardData["onContextMenu"];
}

export function buildCanvasModel(graph: NormalizedLineageGraph, options: BuildOptions) {
  const index = createGraphIndex(graph);
  const category = categoryFor(options.kind);
  const eligibleEdges = graph.edges.filter((edge) => !category || edge.category === category);
  const traversalIndex = category ? createGraphIndex({ ...graph, edges: eligibleEdges }) : index;
  const eligibleEdgeIds = new Set(eligibleEdges.map((edge) => edge.id));
  const aggregates = aggregateDatasets(graph, index);
  const datasetByNode = new Map<string, string>();
  const aggregateById = new Map(aggregates.map((aggregate) => [aggregate.id, aggregate]));
  for (const aggregate of aggregates) for (const id of aggregate.nodeIds) datasetByNode.set(id, aggregate.id);
  let visibleNodeIds: Set<string> | null = null;
  let visibleEdgeIds: Set<string> | null = null;
  const highlightedEdgeIds = new Set<string>();
  let visibleDatasetOrder: ReadonlyMap<string, number> | null = null;
  let traversalTruncated = false;

  if (options.scopeId && (index.nodeById.has(options.scopeId) || aggregateById.has(options.scopeId)) && options.direction !== "all") {
    const selectedDatasetAggregate = aggregateById.get(options.scopeId);
    if (selectedDatasetAggregate) {
      const traversal = traverseDatasets(eligibleEdges, datasetByNode, options.scopeId, options.direction, options.depth);
      visibleNodeIds = new Set();
      traversal.datasetIds.forEach((datasetId) => aggregateById.get(datasetId)?.nodeIds.forEach((id) => visibleNodeIds!.add(id)));
      visibleEdgeIds = traversal.edgeIds;
      visibleDatasetOrder = new Map([...traversal.datasetIds].map((id, position) => [id, position]));
      traversalTruncated = traversal.truncated;
    } else {
      const traversal = traverseLineage(traversalIndex, options.scopeId, options.direction, {
        maxDepth: options.depth,
        maxNodes: MAX_VISIBLE_NODES * 8,
        maxEdges: MAX_VISIBLE_EDGES * 8,
      });
      visibleNodeIds = new Set(traversal.nodeIds);
      visibleEdgeIds = new Set(traversal.edgeIds.filter((id) => eligibleEdgeIds.has(id)));
    }
  }

  if (options.selectedId && index.nodeById.get(options.selectedId)?.type === "column") {
    for (const walkDirection of ["upstream", "downstream"] as const) {
      const traversal = traverseLineage(traversalIndex, options.selectedId, walkDirection, {
        maxDepth: options.depth,
        maxNodes: MAX_VISIBLE_NODES * 8,
        maxEdges: MAX_VISIBLE_EDGES * 8,
      });
      traversal.edgeIds.forEach((id) => highlightedEdgeIds.add(id));
    }
  }

  const q = options.query.trim().toLocaleLowerCase();
  const matchedIds = new Set<string>();
  if (q) {
    for (const node of graph.nodes) {
      const haystack = `${node.displayName} ${node.ref?.table ?? ""} ${node.ref?.column ?? ""}`.toLocaleLowerCase();
      if (haystack.includes(q)) matchedIds.add(node.id);
    }
  }

  const selectedDataset = options.selectedId ? datasetByNode.get(options.selectedId) ?? options.selectedId : null;
  let datasets = aggregates.filter((dataset) => {
    if (visibleNodeIds && !dataset.nodeIds.some((id) => visibleNodeIds!.has(id))) return false;
    if (q && !dataset.nodeIds.some((id) => matchedIds.has(id)) && !dataset.displayName.toLocaleLowerCase().includes(q)) return false;
    return true;
  });
  datasets.sort((a, b) => {
    if (visibleDatasetOrder) return (visibleDatasetOrder.get(a.id) ?? Number.MAX_SAFE_INTEGER) - (visibleDatasetOrder.get(b.id) ?? Number.MAX_SAFE_INTEGER);
    return a.id.localeCompare(b.id);
  });
  const datasetTruncated = datasets.length > MAX_VISIBLE_NODES;
  datasets = datasets.slice(0, MAX_VISIBLE_NODES).sort((a, b) => a.id.localeCompare(b.id));
  const datasetIds = new Set(datasets.map((dataset) => dataset.id));
  const shownColumnIds = new Set(datasets.flatMap((dataset) => dataset.columnIds.slice(0, MAX_COLUMNS_PER_CARD)));

  const groupedEdges = new Map<string, { source: string; target: string; ids: string[]; selected: boolean; category: EdgeCategory; sourceHandle?: string; targetHandle?: string }>();
  for (const edge of eligibleEdges) {
    if (visibleEdgeIds && !visibleEdgeIds.has(edge.id)) continue;
    const source = datasetByNode.get(edge.sourceId);
    const target = datasetByNode.get(edge.targetId);
    if (!source || !target || !datasetIds.has(source) || !datasetIds.has(target)) continue;
    const key = options.mode === "columns" ? `${source}|${target}|${edge.sourceId}|${edge.targetId}|${edge.category}` : `${source}|${target}|${edge.category}`;
    const selected = highlightedEdgeIds.has(edge.id) || (!!options.selectedId && (options.selectedId === source || options.selectedId === target));
    const current = groupedEdges.get(key);
    if (current) { current.ids.push(edge.id); current.selected ||= selected; }
    else groupedEdges.set(key, {
      source, target, ids: [edge.id], selected, category: edge.category,
      sourceHandle: options.mode === "columns" && shownColumnIds.has(edge.sourceId) ? edge.sourceId : undefined,
      targetHandle: options.mode === "columns" && shownColumnIds.has(edge.targetId) ? edge.targetId : undefined,
    });
  }
  const rawGroups = [...groupedEdges.values()].sort((a, b) => `${a.source}|${a.target}|${a.ids[0]}`.localeCompare(`${b.source}|${b.target}|${b.ids[0]}`));
  const edgeTruncated = rawGroups.length > MAX_VISIBLE_EDGES;
  const groups = rawGroups.slice(0, MAX_VISIBLE_EDGES);
  const connectedDatasets = new Set(groups.flatMap((edge) => [edge.source, edge.target]));

  const rfNodes: Node<DatasetCardData>[] = datasets.map((dataset) => {
    const datasetNode = index.nodeById.get(dataset.id);
    const allColumns = dataset.columnIds.map((id) => index.nodeById.get(id)).filter((node): node is LineageNode => !!node);
    const columns = allColumns.slice(0, MAX_COLUMNS_PER_CARD);
    const expanded = options.mode === "columns";
    const tableName = datasetNode?.ref?.table ?? allColumns[0]?.ref?.table ?? "";
    const schema = tableName.split(".").slice(0, -1).join(".") || "DATASET";
    return {
      id: dataset.id,
      type: "datasetCard",
      position: { x: 0, y: 0 },
      data: { id: dataset.id, label: dataset.displayName, type: datasetNode?.type ?? "table", schema, columns, hiddenColumnCount: allColumns.length - columns.length, expanded, selectedId: options.selectedId, matchedIds, onSelect: (id) => options.onSelect?.(id), onContextMenu: options.onContextMenu ?? (() => undefined) },
      style: { "--dataset-accent": schemaColor(schema) } as CSSProperties,
      width: CARD_WIDTH,
      height: expanded ? COMPACT_HEIGHT + columns.length * ROW_HEIGHT + (allColumns.length > columns.length ? ROW_HEIGHT : 0) : COMPACT_HEIGHT,
    };
  });
  const rfEdges: Edge[] = groups.map((group) => ({
    id: group.ids.join("::"), source: group.source, target: group.target,
    sourceHandle: group.sourceHandle, targetHandle: group.targetHandle,
    type: "smoothstep", animated: group.selected,
    className: group.selected ? "lineage-edge is-selected" : "lineage-edge",
    markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: group.selected ? "#1769e0" : group.category === "control" ? "#9a6bd7" : group.category === "dynamic" ? "#c78a26" : "#8b98a7" },
    style: { stroke: group.selected ? "#1769e0" : group.category === "control" ? "#9a6bd7" : group.category === "dynamic" ? "#c78a26" : "#8b98a7", strokeWidth: group.selected ? 2.4 : 1.35, strokeDasharray: group.category === "control" ? "5 4" : undefined },
  }));
  const topologyKey = `${options.mode}:${rfNodes.map((node) => `${node.id}:${node.height}`).join(",")}:${rfEdges.map((edge) => edge.id).join(",")}`;
  const nameById = new Map(graph.nodes.map((node) => [node.id, node.displayName]));
  aggregates.forEach((dataset) => { if (!nameById.has(dataset.id)) nameById.set(dataset.id, dataset.displayName); });
  return { nodes: layout(rfNodes, rfEdges), edges: rfEdges, truncated: traversalTruncated || datasetTruncated || edgeTruncated, topologyKey, datasetByNode, nameById };
}

function schemaColor(schema: string): string {
  let hash = 0;
  for (let position = 0; position < schema.length; position += 1) hash = (hash * 31 + schema.charCodeAt(position)) | 0;
  return `hsl(${Math.abs(hash) % 360} 42% 45%)`;
}

function traverseDatasets(
  edges: NormalizedLineageGraph["edges"],
  datasetByNode: ReadonlyMap<string, string>,
  startId: string,
  direction: "upstream" | "downstream",
  maxDepth: number,
): { datasetIds: Set<string>; edgeIds: Set<string>; truncated: boolean } {
  const adjacent = new Map<string, Array<{ next: string; edgeId: string }>>();
  for (const edge of edges) {
    const source = datasetByNode.get(edge.sourceId);
    const target = datasetByNode.get(edge.targetId);
    if (!source || !target || source === target) continue;
    const from = direction === "upstream" ? target : source;
    const next = direction === "upstream" ? source : target;
    const entries = adjacent.get(from);
    if (entries) entries.push({ next, edgeId: edge.id });
    else adjacent.set(from, [{ next, edgeId: edge.id }]);
  }
  const datasetIds = new Set([startId]);
  const edgeIds = new Set<string>();
  const queue: Array<{ id: string; depth: number }> = [{ id: startId, depth: 0 }];
  let truncated = false;
  for (let cursor = 0; cursor < queue.length; cursor += 1) {
    const current = queue[cursor];
    if (current.depth >= Math.max(0, maxDepth)) continue;
    for (const relation of adjacent.get(current.id) ?? []) {
      if (edgeIds.size >= MAX_VISIBLE_EDGES) { truncated = true; break; }
      edgeIds.add(relation.edgeId);
      if (!datasetIds.has(relation.next)) {
        if (datasetIds.size >= MAX_VISIBLE_NODES) { truncated = true; continue; }
        datasetIds.add(relation.next);
        queue.push({ id: relation.next, depth: current.depth + 1 });
      }
    }
  }
  return { datasetIds, edgeIds, truncated };
}

function layout(nodes: Node<DatasetCardData>[], edges: Edge[]): Node<DatasetCardData>[] {
  const layoutGraph = new dagre.graphlib.Graph({ multigraph: true });
  layoutGraph.setGraph({ rankdir: "LR", ranksep: 110, nodesep: 42, marginx: 32, marginy: 32, acyclicer: "greedy", ranker: "network-simplex" });
  layoutGraph.setDefaultEdgeLabel(() => ({}));
  for (const node of nodes) layoutGraph.setNode(node.id, { width: node.width ?? CARD_WIDTH, height: node.height ?? COMPACT_HEIGHT });
  edges.forEach((edge, position) => layoutGraph.setEdge(edge.source, edge.target, {}, `${edge.id}-${position}`));
  dagre.layout(layoutGraph);
  return nodes.map((node) => {
    const point = layoutGraph.node(node.id);
    const width = node.width ?? CARD_WIDTH;
    const height = node.height ?? COMPACT_HEIGHT;
    return { ...node, position: { x: point.x - width / 2, y: point.y - height / 2 } };
  });
}
