import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type MouseEvent } from "react";
import dagre from "@dagrejs/dagre";
import { LayoutGrid, Map as MapIcon } from "lucide-react";
import {
  BaseEdge,
  ControlButton,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  applyNodeChanges,
  getStraightPath,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeChange,
  type NodeProps,
  type ReactFlowInstance,
  useInternalNode,
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
  fill: string;
  columns: LineageNode[];
  hiddenColumns: LineageNode[];
  hiddenColumnCount: number;
  overflowColumnCount: number;
  overflowExpanded: boolean;
  expanded: boolean;
  selectedId: string | null;
  selectedDatasetId: string | null;
  related: boolean;
  matchedIds: ReadonlySet<string>;
  onSelect: (id: string) => void;
  onContextMenu: (id: string, event: MouseEvent | KeyboardEvent) => void;
  onToggleColumns: (id: string) => void;
}

const MAX_VISIBLE_NODES = 160;
const MAX_VISIBLE_EDGES = 500;
const CARD_WIDTH = 230;
const COMPACT_HEIGHT = 48;
const ROW_HEIGHT = 26;
const MAX_COLUMNS_PER_CARD = 8;
const FIT_VIEW_OPTIONS = { padding: { top: "96px", right: "28px", bottom: "28px", left: "68px" }, maxZoom: 1.15 } as const;

function DatasetCard({ data }: NodeProps<Node<DatasetCardData>>) {
  const selected = data.selectedDatasetId === data.id;
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
      className={`dataset-card ${selected ? "is-selected" : ""} ${matched ? "is-match" : ""} ${data.related ? "is-related" : "is-muted"}`}
      tabIndex={0}
      role="button"
      aria-label={data.expanded ? `${data.label}, ${data.columns.length + data.hiddenColumnCount} connected columns` : data.label}
      onClick={select}
      onKeyDown={onKeyDown}
      onContextMenu={(event) => { event.preventDefault(); data.onContextMenu(data.id, event); }}
    >
      <Handle type="target" position={Position.Left} className="dataset-handle" />
      <div className="dataset-card__header">
        <span className="dataset-card__title" title={data.label}>{data.label}</span>
      </div>
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
                <Handle id={`${column.id}::self`} type="target" position={Position.Right} className="column-handle column-handle--self" />
              </button>
            );
          })}
          {data.hiddenColumnCount > 0 && (
            <div className="dataset-column-overflow">
              <button type="button" onClick={(event) => { event.stopPropagation(); data.onToggleColumns(data.id); }}>
                Show {data.hiddenColumnCount} more column{data.hiddenColumnCount === 1 ? "" : "s"}
              </button>
              {data.hiddenColumns.map((column) => (
                <span className="dataset-column-overflow__handles" key={column.id} aria-hidden="true">
                  <Handle id={column.id} type="target" position={Position.Left} className="column-handle column-handle--overflow" />
                  <Handle id={column.id} type="source" position={Position.Right} className="column-handle column-handle--overflow" />
                  <Handle id={`${column.id}::self`} type="target" position={Position.Right} className="column-handle column-handle--overflow column-handle--self" />
                </span>
              ))}
            </div>
          )}
          {data.overflowExpanded && data.overflowColumnCount > 0 && (
            <div className="dataset-column-overflow">
              <button type="button" onClick={(event) => { event.stopPropagation(); data.onToggleColumns(data.id); }}>Show fewer columns</button>
            </div>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} className="dataset-handle" />
    </div>
  );
}

const nodeTypes = { datasetCard: DatasetCard };

function FloatingEdge({ id, source, target, sourceX, sourceY, targetX, targetY, markerEnd, style }: EdgeProps) {
  const sourceNode = useInternalNode(source);
  const targetNode = useInternalNode(target);
  let start = { x: sourceX, y: sourceY };
  let end = { x: targetX, y: targetY };
  if (sourceNode && targetNode) {
    const sourceWidth = sourceNode.measured.width ?? CARD_WIDTH;
    const sourceHeight = sourceNode.measured.height ?? COMPACT_HEIGHT;
    const targetWidth = targetNode.measured.width ?? CARD_WIDTH;
    const targetHeight = targetNode.measured.height ?? COMPACT_HEIGHT;
    const sourceCenter = { x: sourceNode.internals.positionAbsolute.x + sourceWidth / 2, y: sourceNode.internals.positionAbsolute.y + sourceHeight / 2 };
    const targetCenter = { x: targetNode.internals.positionAbsolute.x + targetWidth / 2, y: targetNode.internals.positionAbsolute.y + targetHeight / 2 };
    [start, end] = facingBoundaries(sourceCenter, targetCenter, sourceWidth, sourceHeight, targetWidth, targetHeight);
    const distance = Math.hypot(end.x - start.x, end.y - start.y);
    if (distance > 4) {
      end = { x: end.x - ((end.x - start.x) / distance) * 4, y: end.y - ((end.y - start.y) / distance) * 4 };
    }
  }
  const [path] = getStraightPath({ sourceX: start.x, sourceY: start.y, targetX: end.x, targetY: end.y });
  return <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} interactionWidth={12} />;
}

function facingBoundaries(
  source: { x: number; y: number },
  target: { x: number; y: number },
  sourceWidth: number,
  sourceHeight: number,
  targetWidth: number,
  targetHeight: number,
) {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const clamp = (value: number, limit: number) => Math.max(-limit + 4, Math.min(value, limit - 4));
  if (Math.abs(dx) >= (sourceWidth + targetWidth) / 2) {
    const sign = Math.sign(dx) || 1;
    return [
      { x: source.x + sign * sourceWidth / 2, y: source.y + clamp(dy * (sourceWidth / 2) / Math.abs(dx), sourceHeight / 2) },
      { x: target.x - sign * targetWidth / 2, y: target.y - clamp(dy * (targetWidth / 2) / Math.abs(dx), targetHeight / 2) },
    ] as const;
  }
  const sign = Math.sign(dy) || 1;
  const distance = Math.abs(dy) || 1;
  return [
    { x: source.x + clamp(dx * (sourceHeight / 2) / distance, sourceWidth / 2), y: source.y + sign * sourceHeight / 2 },
    { x: target.x - clamp(dx * (targetHeight / 2) / distance, targetWidth / 2), y: target.y - sign * targetHeight / 2 },
  ] as const;
}

function IntraDatasetEdge({ id, sourceX, sourceY, targetX, targetY, markerEnd, style, data }: EdgeProps) {
  const lane = typeof data?.lane === "number" ? data.lane : 0;
  const loopX = Math.max(sourceX, targetX) + 20 + lane * 7;
  const path = `M ${sourceX},${sourceY} C ${loopX},${sourceY} ${loopX},${targetY} ${targetX},${targetY}`;
  return <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} interactionWidth={12} />;
}

const edgeTypes = { floating: FloatingEdge, intraDataset: IntraDatasetEdge };

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
  const [showMiniMap, setShowMiniMap] = useState(false);
  const [expandedDatasetIds, setExpandedDatasetIds] = useState<ReadonlySet<string>>(() => new Set());
  const toggleDatasetColumns = useCallback((id: string) => {
    setExpandedDatasetIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
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
    () => buildCanvasModel(graph, { selectedId, scopeId, mode, direction, depth, kind, query, expandedDatasetIds, onSelect, onInspect, onExplore, onContextMenu: openMenu, onToggleColumns: toggleDatasetColumns }),
    [graph, selectedId, scopeId, mode, direction, depth, kind, query, expandedDatasetIds, onSelect, onInspect, onExplore, openMenu, toggleDatasetColumns],
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
      {mode === "columns" && <div className="graph-mode-hint">Column lineage · highlighted value flow</div>}
      <div className="graph-schema-legend" aria-label="Schema color legend">
        <strong>Schema</strong>
        {model.schemas.map((schema) => <span key={schema.name}><i style={{ background: schema.fill, borderColor: schema.border }} />{schema.name}</span>)}
      </div>
      <ReactFlow
        key={model.topologyKey}
        nodes={nodes}
        edges={model.edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onInit={setFlow}
        onNodesChange={onNodesChange}
        onPaneClick={() => onSelect(null)}
        fitView
        fitViewOptions={FIT_VIEW_OPTIONS}
        minZoom={0.18}
        maxZoom={1.8}
        nodesConnectable={false}
        deleteKeyCode={null}
        proOptions={{ hideAttribution: true }}
      >
        {showMiniMap && <MiniMap position="bottom-left" pannable zoomable nodeStrokeWidth={1} nodeColor={(node) => String(node.data.fill ?? "#d9e8f5")} maskColor="rgba(235,236,240,.78)" />}
        <Controls position="bottom-left" orientation="vertical" showInteractive={false} fitViewOptions={FIT_VIEW_OPTIONS}>
          <ControlButton onClick={() => setNodes(model.nodes)} title="Restore automatic layout" aria-label="Restore automatic layout"><LayoutGrid size={14} /></ControlButton>
          <ControlButton onClick={() => setShowMiniMap((visible) => !visible)} title={showMiniMap ? "Hide minimap" : "Show minimap"} aria-label={showMiniMap ? "Hide minimap" : "Show minimap"} className={showMiniMap ? "is-active" : ""}><MapIcon size={14} /></ControlButton>
        </Controls>
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
  onToggleColumns?: DatasetCardData["onToggleColumns"];
  expandedDatasetIds?: ReadonlySet<string>;
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
    });
  }
  const rawGroups = [...groupedEdges.values()].sort((a, b) => `${a.source}|${a.target}|${a.ids[0]}`.localeCompare(`${b.source}|${b.target}|${b.ids[0]}`));
  const edgeTruncated = rawGroups.length > MAX_VISIBLE_EDGES;
  const groups = rawGroups.slice(0, MAX_VISIBLE_EDGES);
  const renderedEdgeIds = new Set(groups.map((group) => group.ids[0]));
  const connectedColumnIds = new Map<string, Set<string>>();
  const rememberColumn = (datasetId: string, nodeId: string) => {
    if (index.nodeById.get(nodeId)?.type !== "column") return;
    const ids = connectedColumnIds.get(datasetId);
    if (ids) ids.add(nodeId);
    else connectedColumnIds.set(datasetId, new Set([nodeId]));
  };
  const renderedEdgeById = new Map(eligibleEdges.filter((edge) => renderedEdgeIds.has(edge.id)).map((edge) => [edge.id, edge]));
  for (const edge of renderedEdgeById.values()) {
    const source = datasetByNode.get(edge.sourceId);
    const target = datasetByNode.get(edge.targetId);
    if (source) rememberColumn(source, edge.sourceId);
    if (target) rememberColumn(target, edge.targetId);
  }
  const connectedColumnsByDataset = new Map(datasets.map((dataset) => {
    const connected = connectedColumnIds.get(dataset.id) ?? new Set<string>();
    return [dataset.id, dataset.columnIds.filter((id) => connected.has(id))] as const;
  }));
  const shownColumnIds = new Set([...connectedColumnsByDataset.values()].flat());
  if (options.mode === "columns") {
    for (const group of groups) {
      const representative = renderedEdgeById.get(group.ids[0]);
      group.sourceHandle = representative && shownColumnIds.has(representative.sourceId) ? representative.sourceId : undefined;
      group.targetHandle = representative && shownColumnIds.has(representative.targetId) ? representative.targetId : undefined;
      if (group.source === group.target && group.targetHandle) group.targetHandle = `${group.targetHandle}::self`;
    }
  }
  const selectedRelationDatasets = new Set(groups.filter((edge) => edge.selected).flatMap((edge) => [edge.source, edge.target]));
  const hasSelection = !!options.selectedId;
  const schemaByDataset = new Map(aggregates.map((dataset) => {
    const datasetNode = index.nodeById.get(dataset.id);
    const firstColumn = dataset.columnIds.length ? index.nodeById.get(dataset.columnIds[0]) : undefined;
    const tableName = datasetNode?.ref?.table ?? firstColumn?.ref?.table ?? "";
    return [dataset.id, tableName.split(".").slice(0, -1).join(".") || "No schema"] as const;
  }));
  const schemaStyles = new Map([...new Set(schemaByDataset.values())].sort().map((schema, position) => [schema, SCHEMA_PALETTE[position % SCHEMA_PALETTE.length]] as const));

  const rfNodes: Node<DatasetCardData>[] = datasets.map((dataset) => {
    const datasetNode = index.nodeById.get(dataset.id);
    const allColumns = dataset.columnIds.map((id) => index.nodeById.get(id)).filter((node): node is LineageNode => !!node);
    const connectedIds = new Set(connectedColumnsByDataset.get(dataset.id) ?? []);
    const connectedColumns = allColumns.filter((column) => connectedIds.has(column.id));
    const overflowColumns = connectedColumns.slice(MAX_COLUMNS_PER_CARD);
    const overflowExpanded = options.expandedDatasetIds?.has(dataset.id) ?? false;
    const columns = overflowExpanded ? connectedColumns : connectedColumns.slice(0, MAX_COLUMNS_PER_CARD);
    const hiddenColumns = overflowExpanded ? [] : overflowColumns;
    const expanded = options.mode === "columns";
    const schema = schemaByDataset.get(dataset.id) ?? "No schema";
    const schemaStyle = schemaStyles.get(schema) ?? SCHEMA_PALETTE[0];
    return {
      id: dataset.id,
      type: "datasetCard",
      position: { x: 0, y: 0 },
      data: { id: dataset.id, label: dataset.displayName, type: datasetNode?.type ?? "table", schema, fill: schemaStyle.fill, columns, hiddenColumns, hiddenColumnCount: hiddenColumns.length, overflowColumnCount: overflowColumns.length, overflowExpanded, expanded, selectedId: options.selectedId, selectedDatasetId: selectedDataset, related: !hasSelection || selectedDataset === dataset.id || selectedRelationDatasets.has(dataset.id), matchedIds, onSelect: (id) => options.onSelect?.(id), onContextMenu: options.onContextMenu ?? (() => undefined), onToggleColumns: options.onToggleColumns ?? (() => undefined) },
      style: { "--dataset-fill": schemaStyle.fill, "--dataset-border": schemaStyle.border } as CSSProperties,
      width: CARD_WIDTH,
      height: expanded ? COMPACT_HEIGHT + columns.length * ROW_HEIGHT + (overflowColumns.length ? ROW_HEIGHT : 0) : COMPACT_HEIGHT,
    };
  });
  const intraLaneByDataset = new Map<string, number>();
  const rfEdges: Edge[] = groups.map((group) => {
    const intraDataset = group.source === group.target && options.mode === "columns";
    const lane = intraDataset ? intraLaneByDataset.get(group.source) ?? 0 : 0;
    if (intraDataset) intraLaneByDataset.set(group.source, lane + 1);
    return {
      id: group.ids.join("::"), source: group.source, target: group.target,
      sourceHandle: group.sourceHandle, targetHandle: group.targetHandle,
      type: intraDataset ? "intraDataset" : group.source === group.target ? "smoothstep" : options.mode === "datasets" ? "floating" : "straight",
      data: intraDataset ? { lane } : undefined,
      animated: false,
      className: `lineage-edge lineage-edge--${group.category}${group.selected ? " is-selected" : ""}${intraDataset ? " lineage-edge--intra" : ""}`,
      markerEnd: { type: MarkerType.ArrowClosed, width: 11, height: 11, color: group.selected ? "#bf7329" : "#78838e" },
      style: { stroke: group.selected ? "#bf7329" : "#78838e", strokeWidth: group.selected ? 2.2 : 1.15, strokeDasharray: group.category === "control" ? "4 3" : group.category === "dynamic" ? "2 3" : undefined },
    };
  });
  const topologyKey = `${options.mode}:${rfNodes.map((node) => `${node.id}:${node.width}x${node.height}`).join(",")}:${rfEdges.map((edge) => `${edge.id}:${edge.source}>${edge.target}`).join(",")}`;
  const nameById = new Map(graph.nodes.map((node) => [node.id, node.displayName]));
  aggregates.forEach((dataset) => { if (!nameById.has(dataset.id)) nameById.set(dataset.id, dataset.displayName); });
  const schemas = [...new Map(rfNodes.map((node) => [node.data.schema, { name: node.data.schema, ...(schemaStyles.get(node.data.schema) ?? SCHEMA_PALETTE[0]) }])).values()]
    .sort((a, b) => a.name.localeCompare(b.name));
  return { nodes: layout(rfNodes, rfEdges, topologyKey), edges: rfEdges, schemas, truncated: traversalTruncated || datasetTruncated || edgeTruncated, topologyKey, datasetByNode, nameById };
}

const SCHEMA_PALETTE = [
  { fill: "#d9e8f5", border: "#96abc0" },
  { fill: "#dfead8", border: "#9eaf96" },
  { fill: "#eee0f2", border: "#b4a0ba" },
  { fill: "#f3e4d2", border: "#bca68b" },
  { fill: "#d8ece9", border: "#94b1ad" },
  { fill: "#eee5c9", border: "#b5aa83" },
  { fill: "#e1e3f2", border: "#a1a5bd" },
  { fill: "#eadedd", border: "#b39c9a" },
  { fill: "#d6e9df", border: "#92ad9d" },
  { fill: "#e5dbef", border: "#aa9ab8" },
  { fill: "#f0dfdf", border: "#b59b9c" },
  { fill: "#d8e6ed", border: "#94a8b3" },
  { fill: "#ece2d5", border: "#b4a28e" },
  { fill: "#dce9cf", border: "#9eaf8d" },
  { fill: "#e6def0", border: "#aaa0b7" },
  { fill: "#f1e4c9", border: "#b6a886" },
] as const;

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

const layoutCache = new Map<string, Map<string, { x: number; y: number }>>();

function layout(nodes: Node<DatasetCardData>[], edges: Edge[], cacheKey: string): Node<DatasetCardData>[] {
  const cached = layoutCache.get(cacheKey);
  if (cached && nodes.every((node) => cached.has(node.id))) {
    return nodes.map((node) => ({ ...node, position: cached.get(node.id)! }));
  }
  const layoutGraph = new dagre.graphlib.Graph({ multigraph: true });
  layoutGraph.setGraph({ rankdir: "LR", ranksep: 110, nodesep: 42, marginx: 32, marginy: 32, acyclicer: "greedy", ranker: "network-simplex" });
  layoutGraph.setDefaultEdgeLabel(() => ({}));
  for (const node of nodes) layoutGraph.setNode(node.id, { width: node.width ?? CARD_WIDTH, height: node.height ?? COMPACT_HEIGHT });
  edges.forEach((edge, position) => layoutGraph.setEdge(edge.source, edge.target, {}, `${edge.id}-${position}`));
  dagre.layout(layoutGraph);
  const positioned = nodes.map((node) => {
    const point = layoutGraph.node(node.id);
    const width = node.width ?? CARD_WIDTH;
    const height = node.height ?? COMPACT_HEIGHT;
    return { ...node, position: { x: point.x - width / 2, y: point.y - height / 2 } };
  });
  layoutCache.set(cacheKey, new Map(positioned.map((node) => [node.id, node.position])));
  if (layoutCache.size > 12) layoutCache.delete(layoutCache.keys().next().value!);
  return positioned;
}
