import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowDownToLine,
  ArrowLeftRight,
  Braces,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Columns3,
  Database,
  Download,
  FileCode2,
  GitBranch,
  Info,
  ListFilter,
  LocateFixed,
  Menu,
  PanelBottomClose,
  PanelBottomOpen,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Search,
  Share2,
  Sparkles,
  Table2,
  Upload,
  X,
} from "lucide-react";
import { GraphCanvas } from "./GraphCanvas";
import { PathFinder } from "./PathFinder";
import { aggregateDatasets, DEMO_LINEAGE, DEMO_PAYLOAD, fqnToNodeId, parseLineage } from "./data";
import type { LineageDiagnostic, LineageEdge, LineageNode, NormalizedLineageGraph, ValidationIssue } from "./data";
import { graphsMatch, invokeLiveTool, parseFocusEvent, parseLiveOrigin, sha256Prefixed, subscribeLiveFocus, type AgentFocus, type LiveStatus } from "./live";
import "./styles.css";

type ViewMode = "datasets" | "columns";
type Direction = "all" | "upstream" | "downstream";
type Kind = "VALUE" | "FILTER" | "all";
type BottomTab = "preview" | "evidence" | "path" | "diagnostics" | "json";
type InspectorTab = "about" | "columns";
const MAX_IMPORT_BYTES = 25 * 1024 * 1024;

const navItems = [
  { label: "Lineage", icon: GitBranch },
  { label: "Datasets", icon: Database },
  { label: "Columns", icon: Columns3 },
  { label: "Diagnostics", icon: AlertTriangle },
];

function IconButton({ label, children, active = false, onClick, disabled = false }: { label: string; children: React.ReactNode; active?: boolean; onClick?: () => void; disabled?: boolean }) {
  return <button className={`icon-button${active ? " active" : ""}`} type="button" title={label} aria-label={label} aria-pressed={active || undefined} onClick={onClick} disabled={disabled}>{children}</button>;
}

function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[]; onChange: (value: T) => void; label: string }) {
  return <div className="segmented" role="group" aria-label={label}>{options.map(option => <button key={option.value} className={value === option.value ? "active" : ""} aria-pressed={value === option.value} type="button" onClick={() => onChange(option.value)}>{option.label}</button>)}</div>;
}

function shortName(node?: LineageNode) {
  if (!node) return "Nothing selected";
  return node.ref?.column ?? node.ref?.table ?? node.displayName.split(".").at(-1) ?? node.displayName;
}

function locationText(edge?: LineageEdge) {
  if (!edge?.evidence) return "No source location reported";
  const { file, line, package: pkg, procedure, function: fn } = edge.evidence;
  return [file && `${file}${line ? `:${line}` : ""}`, [pkg, fn ?? procedure].filter(Boolean).join(".")].filter(Boolean).join(" · ") || "No source location reported";
}

function App() {
  const [graph, setGraph] = useState<NormalizedLineageGraph>(DEMO_LINEAGE);
  const [originalPayload, setOriginalPayload] = useState<unknown>(DEMO_PAYLOAD);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<ViewMode>("datasets");
  const [direction, setDirection] = useState<Direction>("all");
  const [scopeId, setScopeId] = useState<string | null>(null);
  const [kind, setKind] = useState<Kind>("VALUE");
  const [depth, setDepth] = useState(3);
  const [query, setQuery] = useState("");
  const [rightOpen, setRightOpen] = useState(true);
  const [bottomOpen, setBottomOpen] = useState(false);
  const [bottomTab, setBottomTab] = useState<BottomTab>("preview");
  const [activeNav, setActiveNav] = useState("Lineage");
  const [rightTab, setRightTab] = useState<"details" | "search">("details");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("about");
  const [columnQuery, setColumnQuery] = useState("");
  const [railOpen, setRailOpen] = useState(true);
  const [helpOpen, setHelpOpen] = useState(false);
  const [inspectorWidth, setInspectorWidth] = useState(350);
  const [bottomHeight, setBottomHeight] = useState(220);
  const [notice, setNotice] = useState<{ tone: "error" | "info"; title: string; issues?: ValidationIssue[] } | null>(null);
  const [liveStatus, setLiveStatus] = useState<LiveStatus>("off");
  const [canvasSha, setCanvasSha] = useState<string | null>(null);
  const [agentFocus, setAgentFocus] = useState<AgentFocus | null>(null);
  const [followAgent, setFollowAgent] = useState(false);
  const [liveQuery, setLiveQuery] = useState("OUT_ALLOC.ORD_QTY");
  const fileRef = useRef<HTMLInputElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const liveOrigin = useMemo(() => parseLiveOrigin(window.location.search), []);

  const nodeById = useMemo(() => new Map(graph.nodes.map(node => [node.id, node])), [graph]);
  const datasets = useMemo(() => aggregateDatasets(graph), [graph]);
  const datasetById = useMemo(() => new Map(datasets.map(dataset => [dataset.id, nodeById.get(dataset.id) ?? { id: dataset.id, type: "table" as const, displayName: dataset.displayName, datasetId: dataset.id }])), [datasets, nodeById]);
  const datasetCount = datasets.length;
  const selectedNode = useMemo(() => {
    const direct = selectedId ? nodeById.get(selectedId) : undefined;
    return direct ?? (selectedId ? datasetById.get(selectedId) : undefined);
  }, [selectedId, nodeById, datasetById]);
  const selectedDatasetId = selectedNode?.datasetId ?? (selectedNode?.type === "table" || selectedNode?.type === "view" ? selectedNode.id : undefined);
  const selectedEdges = useMemo(() => {
    if (!selectedId) return [];
    const belongs = (id: string) => id === selectedId || Boolean((selectedNode?.type === "table" || selectedNode?.type === "view") && selectedDatasetId && nodeById.get(id)?.datasetId === selectedDatasetId);
    return graph.edges.filter(edge => belongs(edge.sourceId) || belongs(edge.targetId));
  }, [graph.edges, selectedId, selectedDatasetId, selectedNode?.type, nodeById]);
  const selectedFlow = useMemo(() => {
    if (!selectedNode || !selectedDatasetId) return { upstream: [] as LineageNode[], downstream: [] as LineageNode[] };
    const upstream = new Map<string, LineageNode>();
    const downstream = new Map<string, LineageNode>();
    const datasetFor = (id: string) => {
      const endpoint = nodeById.get(id);
      const datasetId = endpoint?.datasetId ?? (endpoint?.type === "table" || endpoint?.type === "view" ? endpoint.id : undefined);
      return datasetId ? datasetById.get(datasetId) : undefined;
    };
    const isSelectedSource = (edge: LineageEdge) => selectedNode.type === "column" ? edge.sourceId === selectedNode.id : datasetFor(edge.sourceId)?.id === selectedDatasetId;
    const isSelectedTarget = (edge: LineageEdge) => selectedNode.type === "column" ? edge.targetId === selectedNode.id : datasetFor(edge.targetId)?.id === selectedDatasetId;
    const eligibleEdges = kind === "all" ? graph.edges : graph.edges.filter(edge => edge.category === (kind === "VALUE" ? "value" : "control"));
    for (const edge of eligibleEdges) {
      const sourceDataset = datasetFor(edge.sourceId);
      const targetDataset = datasetFor(edge.targetId);
      if (isSelectedTarget(edge) && sourceDataset && sourceDataset.id !== selectedDatasetId) upstream.set(sourceDataset.id, sourceDataset);
      if (isSelectedSource(edge) && targetDataset && targetDataset.id !== selectedDatasetId) downstream.set(targetDataset.id, targetDataset);
    }
    const byName = (a: LineageNode, b: LineageNode) => a.displayName.localeCompare(b.displayName);
    return { upstream: [...upstream.values()].sort(byName), downstream: [...downstream.values()].sort(byName) };
  }, [datasetById, graph.edges, kind, nodeById, selectedDatasetId, selectedNode]);
  const columns = useMemo(() => graph.nodes.filter(node => node.type === "column" && (!selectedDatasetId || node.datasetId === selectedDatasetId) && node.displayName.toLowerCase().includes(columnQuery.toLowerCase())), [graph.nodes, selectedDatasetId, columnQuery]);
  const searchResults = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return [];
    return graph.nodes.filter(node => `${node.displayName} ${node.type}`.toLowerCase().includes(needle)).slice(0, 40);
  }, [graph.nodes, query]);
  const graphMismatch = Boolean(agentFocus?.graph && canvasSha && !graphsMatch(canvasSha, agentFocus.graph));
  const canPaintAgent = Boolean(agentFocus && canvasSha && agentFocus.graph && graphsMatch(canvasSha, agentFocus.graph));
  const agentLayer = useMemo(() => {
    const empty = { columnIds: new Set<string>(), edgeKeys: new Set<string>(), unmatched: 0 };
    if (!canPaintAgent || !agentFocus) return empty;
    const columnIds = new Set<string>();
    let unmatched = 0;
    for (const fqn of agentFocus.columns) {
      const id = fqnToNodeId(fqn);
      if (!id || (!nodeById.has(id) && !datasetById.has(id))) { unmatched += 1; continue; }
      columnIds.add(id);
    }
    const edgeKeys = new Set<string>();
    for (const edge of agentFocus.edges) {
      const source = fqnToNodeId(edge.source);
      const target = fqnToNodeId(edge.target);
      if (source && target) edgeKeys.add(`${source}|${target}`);
    }
    return { columnIds, edgeKeys, unmatched };
  }, [agentFocus, canPaintAgent, datasetById, nodeById]);

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (event.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(target.tagName)) { event.preventDefault(); searchRef.current?.focus(); }
      if (event.key === "Escape") { setQuery(""); setNotice(null); setHelpOpen(false); }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  useEffect(() => {
    if (!helpOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>('.help-dialog');
    const controls = dialog?.querySelectorAll<HTMLElement>('button, input, select, [tabindex="0"]');
    controls?.[0]?.focus();
    const trap = (event: KeyboardEvent) => {
      if (event.key !== 'Tab' || !controls?.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', trap);
    return () => { document.removeEventListener('keydown', trap); previous?.focus(); };
  }, [helpOpen]);

  useEffect(() => {
    if (!liveOrigin) return;
    let cancelled = false;
    setLiveStatus("connecting");
    setNotice({ tone: "info", title: `Connecting to live lineage at ${liveOrigin}` });
    void (async () => {
      try {
        const response = await fetch(`${liveOrigin}/engine.json`);
        if (!response.ok) throw new Error(`engine.json ${response.status}`);
        const buffer = await response.arrayBuffer();
        const sha = await sha256Prefixed(buffer);
        const raw = JSON.parse(new TextDecoder().decode(buffer)) as unknown;
        const parsed = parseLineage(raw, { label: "live engine.json" });
        if (cancelled) return;
        if (!parsed.ok) {
          setLiveStatus("error");
          setNotice({ tone: "error", title: "Live engine.json is not a supported lineage graph", issues: parsed.errors });
          return;
        }
        setGraph(parsed.graph);
        setOriginalPayload(raw);
        setCanvasSha(sha);
        setSelectedId(null);
        resetExploration();
        setMode("columns");
        setActiveNav("Columns");
        const focusResponse = await fetch(`${liveOrigin}/focus`);
        if (focusResponse.ok) {
          const focus = parseFocusEvent(await focusResponse.json());
          if (focus && (focus.columns.length || focus.edges.length || focus.tool)) setAgentFocus(focus);
        }
        setLiveStatus("live");
        setNotice({ tone: "info", title: `Live graph loaded from ${liveOrigin}` });
      } catch {
        if (!cancelled) {
          setLiveStatus("error");
          setNotice({ tone: "error", title: `Could not load live engine.json from ${liveOrigin}` });
        }
      }
    })();
    const stop = subscribeLiveFocus(liveOrigin, (focus) => {
      setAgentFocus(focus);
      setLiveStatus("live");
    }, (status, detail) => {
      setLiveStatus(status);
      if (status === "error" && detail) setNotice({ tone: "info", title: detail });
    });
    return () => { cancelled = true; stop(); };
  }, [liveOrigin]);

  useEffect(() => {
    if (!followAgent || !agentFocus?.seed || graphMismatch) return;
    const id = fqnToNodeId(agentFocus.seed);
    if (id && (nodeById.has(id) || datasetById.has(id))) setSelectedId(id);
  }, [agentFocus, datasetById, followAgent, graphMismatch, nodeById]);

  async function handleImport(file?: File) {
    if (!file) return;
    if (file.size > MAX_IMPORT_BYTES) {
      setNotice({ tone: "error", title: "This file is larger than the 25 MB import limit" });
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    setNotice({ tone: "info", title: `Reading ${file.name}…` });
    try {
      const text = await file.text();
      const raw = JSON.parse(text) as unknown;
      const parsed = parseLineage(raw, { label: file.name });
      if (!parsed.ok) { setNotice({ tone: "error", title: "This file is not a supported lineage graph", issues: parsed.errors }); return; }
      setGraph(parsed.graph);
      setOriginalPayload(raw);
      setCanvasSha(await sha256Prefixed(new TextEncoder().encode(text)));
      setSelectedId(null);
      resetExploration();
      setNotice(parsed.warnings.length ? { tone: "info", title: `Imported ${file.name} with ${parsed.warnings.length} warning${parsed.warnings.length === 1 ? "" : "s"}`, issues: parsed.warnings } : { tone: "info", title: `Imported ${file.name}` });
    } catch {
      setNotice({ tone: "error", title: "The selected file is not valid JSON" });
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  function exportGraph() {
    const blob = new Blob([JSON.stringify(originalPayload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${(graph.metadata.label ?? "lineage").replace(/[^a-z0-9_-]+/gi, "-").toLowerCase()}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function loadDemo() {
    setGraph(DEMO_LINEAGE);
    setOriginalPayload(DEMO_PAYLOAD);
    setCanvasSha("local:demo");
    setSelectedId(null);
    resetExploration();
    setNotice({ tone: "info", title: "Loaded the fictional sample workspace" });
  }

  function resetExploration() {
    setQuery(""); setColumnQuery(""); setDirection("all"); setScopeId(null); setDepth(3); setKind("VALUE"); setMode("datasets"); setRightTab("details"); setInspectorTab("about"); setActiveNav("Lineage");
  }

  function navigate(label: string) {
    setActiveNav(label);
    if (label === "Lineage") { setMode("datasets"); setRightTab("details"); setBottomTab("preview"); }
    if (label === "Datasets") { setMode("datasets"); setRightOpen(true); setRightTab("search"); searchRef.current?.focus(); }
    if (label === "Columns") { setMode("columns"); setRightOpen(true); setRightTab("search"); searchRef.current?.focus(); }
    if (label === "Diagnostics") { setBottomOpen(true); setBottomTab("diagnostics"); }
  }

  function beginResize(axis: "x" | "y", event: React.PointerEvent) {
    event.preventDefault();
    const start = axis === "x" ? event.clientX : event.clientY;
    const initial = axis === "x" ? inspectorWidth : bottomHeight;
    const move = (next: PointerEvent) => axis === "x" ? setInspectorWidth(Math.max(280, Math.min(560, initial + start - next.clientX))) : setBottomHeight(Math.max(140, Math.min(420, initial + start - next.clientY)));
    const stop = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", stop); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", stop);
  }

  function resizeKey(axis: "x" | "y", event: React.KeyboardEvent) {
    const delta = event.key === "ArrowLeft" || event.key === "ArrowUp" ? 16 : event.key === "ArrowRight" || event.key === "ArrowDown" ? -16 : 0;
    if (!delta) return;
    event.preventDefault();
    axis === "x" ? setInspectorWidth(value => Math.max(280, Math.min(560, value + delta))) : setBottomHeight(value => Math.max(140, Math.min(420, value + delta)));
  }

  const selectNode = useCallback((id: string | null) => {
    setSelectedId(id);
    if (!id) return;
    const node = nodeById.get(id);
    setColumnQuery("");
    setRightTab("details");
    setInspectorTab(node?.type === "column" ? "columns" : "about");
  }, [nodeById]);

  const inspectNode = useCallback((id: string) => {
    selectNode(id);
    setRightOpen(true);
  }, [selectNode]);

  const exploreNode = useCallback((id: string, nextDirection: Direction) => {
    setDirection(nextDirection);
    setScopeId(nextDirection === "all" ? null : id);
    setQuery("");
  }, []);

  function applyDirection(nextDirection: Direction) {
    const anchor = selectedId ?? scopeId;
    if (nextDirection !== "all" && !anchor) {
      setNotice({ tone: "info", title: "Select a dataset or column to set the exploration scope" });
      return;
    }
    exploreNode(anchor ?? "", nextDirection);
  }

  function selectFromList(id: string) {
    selectNode(id);
    setRightOpen(true);
  }

  function traceSelectedColumn() {
    if (selectedNode?.type !== "column") return;
    setMode("columns");
    setActiveNav("Columns");
    setRightOpen(true);
    setRightTab("details");
    setInspectorTab("columns");
  }

  async function submitLiveQuery(event: React.FormEvent) {
    event.preventDefault();
    if (!liveOrigin) return;
    const column = liveQuery.trim();
    if (!column) return;
    try {
      await invokeLiveTool(liveOrigin, { tool: "query_lineage", column });
    } catch (error) {
      setNotice({ tone: "error", title: error instanceof Error ? error.message : "Live query failed" });
    }
  }

  function openBottomTab(tab: BottomTab) {
    setBottomTab(tab);
    setBottomOpen(true);
    if (tab === "path") setBottomHeight(value => Math.max(value, 320));
  }

  return <div className={`app-shell${railOpen ? " rail-open" : ""}`}>
    <aside className="global-rail" aria-label="Primary navigation">
      <div className="brand-mark" aria-label="Lineage home"><Share2 size={18} /></div>
      <nav>{navItems.map(({ label, icon: Icon }) => <button key={label} type="button" className={activeNav === label ? "active" : ""} aria-current={activeNav === label ? "page" : undefined} title={label} aria-label={label} onClick={() => navigate(label)}><Icon size={18} /></button>)}</nav>
      <div className="rail-spacer" />
      <IconButton label="Help" onClick={() => setHelpOpen(true)}><CircleHelp size={18} /></IconButton>
      <div className="user-avatar" title="Local workspace">LW</div>
    </aside>

    <main className="workspace">
      <header className="topbar">
        <div className="title-group"><button className="menu-button" aria-label={railOpen ? "Hide navigation" : "Show navigation"} aria-expanded={railOpen} type="button" onClick={() => setRailOpen(value => !value)}><Menu size={17} /></button><div><strong>Lineage</strong><span>{graph.metadata.label ?? "Workspace"}</span></div>{graph.metadata.fictional && <span className="demo-badge"><Sparkles size={12} /> Fictional sample</span>}</div>
        <div className="top-actions">
          <input ref={fileRef} hidden type="file" accept="application/json,.json" onChange={event => void handleImport(event.target.files?.[0])} />
          <button className="button ghost" type="button" onClick={loadDemo}><RefreshCw size={14} /> Sample</button>
          <button className="button ghost" type="button" onClick={() => fileRef.current?.click()}><Upload size={14} /> Import JSON</button>
          <button className="button primary" type="button" onClick={exportGraph}><Download size={14} /> Export</button>
        </div>
      </header>

      <section className="controlbar" aria-label="Lineage controls">
        <div className="search-wrap"><Search size={15} /><input ref={searchRef} value={query} onChange={event => { setQuery(event.target.value); setRightOpen(true); setRightTab("search"); }} placeholder="Find a dataset or column" aria-label="Find a dataset or column" />{query ? <button type="button" onClick={() => setQuery("")} aria-label="Clear search"><X size={13} /></button> : <kbd>/</kbd>}</div>
        <span className="toolbar-divider" />
        <div className="control-group"><label>View</label><Segmented value={mode} label="Graph view" options={[{ value: "datasets", label: "Datasets" }, { value: "columns", label: "Columns" }]} onChange={value => { setMode(value); setActiveNav(value === "columns" ? "Columns" : "Lineage"); }} /></div>
        <div className="control-group"><label>Flow</label><Segmented value={direction} label="Flow direction" options={[{ value: "upstream", label: "Up" }, { value: "all", label: "All" }, { value: "downstream", label: "Down" }]} onChange={applyDirection} /></div>
        <label className="select-control"><span>Depth</span><select value={depth} onChange={event => setDepth(Number(event.target.value))}>{[1,2,3,4,5,8].map(value => <option key={value} value={value}>{value} hop{value === 1 ? "" : "s"}</option>)}</select><ChevronDown size={13} /></label>
        <label className="select-control"><span>Edges</span><select value={kind} onChange={event => setKind(event.target.value as Kind)}><option value="VALUE">Value</option><option value="FILTER">Filter</option><option value="all">All</option></select><ChevronDown size={13} /></label>
        <span className="toolbar-spacer" />
        <div className="legend" aria-label="Edge legend"><span><i className="value" />Value</span><span><i className="filter" />Filter</span><span><i className="dynamic" />Dynamic</span><span><i className="selected" />Selected</span><span><i className="agent" />Agent</span></div>
      </section>

      {notice && <div className={`notice ${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}><div><strong>{notice.title}</strong>{notice.issues?.slice(0, 3).map(issue => <span key={`${issue.path}-${issue.code}`}>{issue.path}: {issue.message}</span>)}</div><button type="button" onClick={() => setNotice(null)} aria-label="Dismiss message"><X size={14} /></button></div>}

      <div className={`work-area${rightOpen ? " with-inspector" : ""}${bottomOpen ? " with-bottom" : ""}`} style={{ "--inspector-width": `${inspectorWidth}px`, "--bottom-height": `${bottomHeight}px` } as React.CSSProperties}>
        <section className="canvas-panel" aria-label="Lineage graph">
          <GraphCanvas graph={graph} selectedId={selectedId} onSelect={selectNode} onInspect={inspectNode} onExplore={exploreNode} scopeId={scopeId} mode={mode} direction={direction} depth={depth} kind={kind} query={query} agentColumnIds={agentLayer.columnIds} agentEdgeKeys={agentLayer.edgeKeys} />
            {liveOrigin && <div className={`live-banner${graphMismatch ? " is-mismatch" : ""}`} data-testid="live-banner" data-mismatch={graphMismatch || undefined} role="status">
            <span className={`live-dot ${liveStatus}`} aria-hidden="true" />
            <strong>Agent</strong>
            {graphMismatch
              ? <span>Graph mismatch — highlights paused. Reload from the live server or import the same engine.json.</span>
              : agentFocus?.seed
                ? <span title={agentFocus.seed}>{agentFocus.tool} · {agentFocus.seed}{agentLayer.unmatched ? ` · ${agentLayer.unmatched} unmatched` : ""}{agentFocus.omitted_columns ? ` · ${agentFocus.omitted_columns} omitted` : ""}</span>
                : <span>{liveStatus === "connecting" ? "Connecting…" : liveStatus === "error" ? "Disconnected" : "Waiting for a query"}</span>}
            <label className="live-follow"><input type="checkbox" checked={followAgent} onChange={event => setFollowAgent(event.target.checked)} /> Follow</label>
            <button type="button" onClick={() => setAgentFocus(null)}>Clear</button>
            <form onSubmit={event => void submitLiveQuery(event)}>
              <input type="text" value={liveQuery} onChange={event => setLiveQuery(event.target.value)} aria-label="Live query column" placeholder="OUT_ALLOC.ORD_QTY" />
              <button type="submit">Query</button>
            </form>
          </div>}
          {scopeId && direction !== "all" && <div className="scope-banner" role="status"><GitBranch size={13} /><span title={nodeById.get(scopeId)?.displayName ?? scopeId}>{direction === "upstream" ? "Upstream" : "Downstream"} of <strong>{nodeById.get(scopeId)?.displayName ?? scopeId}</strong></span><button type="button" onClick={() => exploreNode(scopeId, "all")}>Show all</button></div>}
          <div className="canvas-status"><span>{datasetCount.toLocaleString()} datasets</span><span>{graph.edges.length.toLocaleString()} edges</span><span>{graph.diagnostics.length} diagnostics</span></div>
        </section>

        {rightOpen && <div className="resize-handle vertical" role="separator" aria-label="Resize details panel" aria-valuemin={280} aria-valuemax={560} aria-valuenow={inspectorWidth} aria-orientation="vertical" tabIndex={0} onPointerDown={event => beginResize("x", event)} onKeyDown={event => resizeKey("x", event)} />}
        <aside className={`inspector${rightOpen ? " open" : ""}`} aria-label="Details panel">
          <div className="panel-tabs"><button type="button" aria-pressed={rightTab === "details"} className={rightTab === "details" ? "active" : ""} onClick={() => setRightTab("details")}><Info size={14} /> Details</button><button type="button" aria-pressed={rightTab === "search"} className={rightTab === "search" ? "active" : ""} onClick={() => setRightTab("search")}><Search size={14} /> Results {query && <em>{searchResults.length}</em>}</button><IconButton label="Collapse details" onClick={() => setRightOpen(false)}><PanelRightClose size={15} /></IconButton></div>
          {rightTab === "search" ? <div className="result-list">{query ? searchResults.length ? <>{searchResults.map(node => <button key={node.id} type="button" className={node.id === selectedId ? "active" : ""} onClick={() => selectFromList(node.id)}><span className={`object-icon ${node.type}`}><Database size={14} /></span><span><strong>{shortName(node)}</strong><small>{node.displayName}</small></span><em>{node.type}</em></button>)}{searchResults.length === 40 && <p className="result-cap">Showing the first 40 matches. Refine your search to narrow the graph.</p>}</> : <EmptyState icon={<Search size={20} />} title="No matches" text="Try a dataset, column, or routine name." /> : <EmptyState icon={<Search size={20} />} title="Search the graph" text="Press / to move to search." />}</div> : <InspectorDetails node={selectedNode} dataset={selectedDatasetId ? datasetById.get(selectedDatasetId) : undefined} columns={columns} columnQuery={columnQuery} onColumnQuery={setColumnQuery} onSelect={selectFromList} edgeCount={selectedEdges.length} tab={inspectorTab} onTab={setInspectorTab} flow={selectedFlow} onTraceColumn={traceSelectedColumn} columnModeActive={mode === "columns"} />}
        </aside>
        {!rightOpen && <button className="reopen-panel right" type="button" onClick={() => setRightOpen(true)} title="Open details"><PanelRightOpen size={16} /></button>}

        {bottomOpen && <div className="resize-handle horizontal" role="separator" aria-label="Resize evidence panel" aria-valuemin={140} aria-valuemax={420} aria-valuenow={bottomHeight} aria-orientation="horizontal" tabIndex={0} onPointerDown={event => beginResize("y", event)} onKeyDown={event => resizeKey("y", event)} />}
        <section className={`bottom-panel${bottomOpen ? " open" : ""}`} aria-label="Evidence panel">
          <div className="bottom-tabs">{([['preview',Table2,'Preview'],['evidence',FileCode2,'Evidence'],['path',GitBranch,'Path'],['diagnostics',AlertTriangle,'Diagnostics'],['json',Braces,'JSON']] as const).map(([tab,Icon,label]) => <button key={tab} type="button" aria-pressed={bottomOpen && bottomTab === tab} className={bottomOpen && bottomTab === tab ? "active" : ""} onClick={() => openBottomTab(tab)}><Icon size={14} /> {label}{tab === 'evidence' && <em>{selectedEdges.length}</em>}{tab === 'diagnostics' && <em>{graph.diagnostics.length}</em>}</button>)}<span /><IconButton label={bottomOpen ? "Collapse bottom panel" : "Expand bottom panel"} onClick={() => setBottomOpen(value => !value)}>{bottomOpen ? <PanelBottomClose size={15} /> : <PanelBottomOpen size={15} />}</IconButton></div>
          {bottomOpen && (bottomTab === "path" ? <PathFinder graph={graph} onSelect={selectFromList} /> : <BottomContent tab={bottomTab} node={selectedNode} edges={selectedEdges} diagnostics={graph.diagnostics} nodeById={nodeById} graph={graph} onOpenEvidence={() => openBottomTab("evidence")} />)}
        </section>
      </div>
      {helpOpen && <div className="dialog-backdrop" role="presentation" onMouseDown={() => setHelpOpen(false)}><section className="help-dialog" role="dialog" aria-modal="true" aria-labelledby="help-title" onMouseDown={event => event.stopPropagation()}><header><div><CircleHelp size={18} /><h2 id="help-title">Lineage workspace help</h2></div><IconButton label="Close help" onClick={() => setHelpOpen(false)}><X size={15} /></IconButton></header><p>This local viewer explores upstream and downstream relationships from engine or legacy viewer JSON. It does not run analysis or connect to a database.</p><p>With <code>?live=http://127.0.0.1:PORT</code> it also subscribes to a loopback UI channel from <code>plsqllineage.serve --ui</code>. Agent walks paint a magenta layer; your click selection stays orange. Follow syncs the inspector to the seed column. A graph hash mismatch pauses painting.</p><dl><div><dt><kbd>/</kbd></dt><dd>Focus graph search</dd></div><div><dt><kbd>Esc</kbd></dt><dd>Clear search or dismiss a message</dd></div><div><dt><kbd>←</kbd> <kbd>→</kbd></dt><dd>Resize the focused side separator</dd></div><div><dt><kbd>↑</kbd> <kbd>↓</kbd></dt><dd>Resize the focused bottom separator</dd></div></dl><p>Datasets keeps one compact card per dataset. Columns expands those cards to show connected column rows. Selecting a column highlights its connected path in orange; Trace column switches to the Columns view without changing the lineage scope.</p><p>Clicking a node selects it without changing the visible graph. Right-click a dataset or column for details, lineage scope, centering, and copying. Use Up or Down to explicitly set a scope; All restores the graph.</p><p>VALUE shows data transformations. FILTER shows predicate influence. All includes calls, unresolved edges, and other relationship kinds.</p></section></div>}
    </main>
  </div>;
}

function InspectorDetails({ node, dataset, columns, columnQuery, onColumnQuery, onSelect, edgeCount, tab, onTab, flow, onTraceColumn, columnModeActive }: { node?: LineageNode; dataset?: LineageNode; columns: LineageNode[]; columnQuery: string; onColumnQuery: (value: string) => void; onSelect: (id: string) => void; edgeCount: number; tab: InspectorTab; onTab: (tab: InspectorTab) => void; flow: { upstream: LineageNode[]; downstream: LineageNode[] }; onTraceColumn: () => void; columnModeActive: boolean }) {
  if (!node) return <EmptyState icon={<LocateFixed size={21} />} title="Select a node" text="Choose a dataset or column to inspect its lineage." />;
  return <div className="inspector-content">
    <div className="object-heading"><span className={`object-icon large ${node.type}`}><Database size={17} /></span><div><span>{node.type}</span><h2>{shortName(node)}</h2><p>{node.displayName}</p></div></div>
    <div className="inspector-subtabs" role="tablist" aria-label="Object details">
      <button type="button" role="tab" aria-selected={tab === "about"} className={tab === "about" ? "active" : ""} onClick={() => onTab("about")}>About</button>
      <button type="button" role="tab" aria-selected={tab === "columns"} className={tab === "columns" ? "active" : ""} onClick={() => onTab("columns")}>Columns <em>{columns.length}</em></button>
    </div>
    {tab === "about" ? <>
      <dl className="about-grid"><div><dt>Object type</dt><dd>{node.type}</dd></div><div><dt>Connected edges</dt><dd>{edgeCount}</dd></div><div><dt>Dataset</dt><dd>{node.ref?.table ?? node.datasetId ?? "—"}</dd></div><div><dt>Remote link</dt><dd>{node.ref?.dblink ?? "—"}</dd></div></dl>
      <div className="flow-summary">
        <div className="section-title"><strong>Selected flow</strong><span>direct neighbors · current edge filter</span></div>
        <FlowGroup label="Upstream inputs" nodes={flow.upstream} onSelect={onSelect} empty="No matching upstream dataset edge" />
        <FlowGroup label="Downstream consumers" nodes={flow.downstream} onSelect={onSelect} empty="No matching downstream dataset edge" />
      </div>
    </> : <>
      <div className="selection-breadcrumb" aria-label="Selected column">
        {dataset ? <button type="button" onClick={() => onSelect(dataset.id)} title={dataset.displayName}>{shortName(dataset)}</button> : <span>{node.ref?.table ?? "Dataset"}</span>}
        {node.type === "column" && <><ChevronRight size={12} /><strong title={node.displayName}>{node.ref?.column ?? shortName(node)}</strong></>}
      </div>
      {node.type === "column" && <div className="trace-column-action"><button className="trace-column" type="button" onClick={onTraceColumn} disabled={columnModeActive}><GitBranch size={13} /> {columnModeActive ? "Column view active" : "Trace column"}</button><small>{columnModeActive ? "The canvas is showing column-level rows." : "See column-to-column connections across the graph."}</small></div>}
      <div className="section-title"><strong>Columns</strong><span>{columns.length}</span></div>
      <div className="small-search"><ListFilter size={14} /><input value={columnQuery} onChange={event => onColumnQuery(event.target.value)} placeholder="Filter columns" aria-label="Filter columns" /></div>
      <div className="column-list">{columns.length ? <>{columns.slice(0, 200).map(column => <button type="button" key={column.id} className={column.id === node.id ? "active" : ""} onClick={() => onSelect(column.id)}><span className="column-glyph">#</span><span>{column.ref?.column ?? shortName(column)}</span><ChevronRight size={13} /></button>)}{columns.length > 200 && <p className="result-cap">Showing 200 of {columns.length} columns. Use the filter to narrow this list.</p>}</> : <p className="muted-copy">No columns are available for this object.</p>}</div>
    </>}
  </div>;
}

function FlowGroup({ label, nodes, onSelect, empty }: { label: string; nodes: LineageNode[]; onSelect: (id: string) => void; empty: string }) {
  return <div className="flow-group"><span>{label}</span>{nodes.length ? <div>{nodes.map(node => <button type="button" key={node.id} onClick={() => onSelect(node.id)} title={node.displayName}>{shortName(node)}</button>)}</div> : <small>{empty}</small>}</div>;
}

function BottomContent({ tab, node, edges, diagnostics, nodeById, graph, onOpenEvidence }: { tab: BottomTab; node?: LineageNode; edges: LineageEdge[]; diagnostics: LineageDiagnostic[]; nodeById: Map<string, LineageNode>; graph: NormalizedLineageGraph; onOpenEvidence: () => void }) {
  if (tab === "diagnostics") return diagnostics.length ? <div className="diagnostic-list">{diagnostics.slice(0, 500).map((item, index) => <div key={`${item.code}-${index}`}><span className={`severity ${item.severity.toLowerCase()}`}>{item.severity || "INFO"}</span><code>{item.code || "UNSPECIFIED"}</code><strong>{item.message || "No diagnostic message"}</strong><small>{item.spanText ?? item.location?.file ?? "No location"}</small></div>)}{diagnostics.length > 500 && <p className="result-cap">Showing 500 of {diagnostics.length} diagnostics.</p>}</div> : <EmptyState compact icon={<AlertTriangle size={18} />} title="No diagnostics" text="The loaded graph did not report any diagnostics." />;
  if (tab === "json") {
    const json = JSON.stringify(node ? { node, edges: edges.slice(0, 500), truncated: edges.length > 500, totalEdges: edges.length } : graph.metadata, null, 2);
    return <pre className="json-preview">{json.length > 100_000 ? `${json.slice(0, 100_000)}\n\n… Preview capped at 100,000 characters. Use Export for the complete payload.` : json}</pre>;
  }
  if (!node) return <EmptyState compact icon={<LocateFixed size={18} />} title="Select a node" text="Evidence and transformations appear here." />;
  if (tab === "evidence") return edges.length ? <div className="evidence-list">{edges.slice(0, 200).map(edge => <article key={edge.id}><div><span className={`edge-kind ${edge.category}`}>{edge.kind}</span><code>{locationText(edge)}</code></div><p>{edge.expression || "No transform expression reported"}</p></article>)}{edges.length > 200 && <p className="result-cap">Showing 200 of {edges.length} evidence records.</p>}</div> : <EmptyState compact icon={<FileCode2 size={18} />} title="No edge evidence" text="This node has no connected lineage evidence." />;
  return edges.length ? <div className="preview-table" role="table"><div className="table-row table-head" role="row"><span>Flow</span><span>Source</span><span>Target</span><span>Kind</span><span>Transform</span><span>Location</span></div>{edges.slice(0, 500).map(edge => { const source = nodeById.get(edge.sourceId)?.displayName ?? edge.sourceId; const target = nodeById.get(edge.targetId)?.displayName ?? edge.targetId; return <button type="button" className="table-row" role="row" key={edge.id} onClick={onOpenEvidence} title={`Open evidence for ${source} → ${target}`}><span>{edge.targetId === node.id || nodeById.get(edge.targetId)?.datasetId === node.id ? <ArrowDownToLine size={14} /> : <ArrowLeftRight size={14} />}</span><strong title={source}>{source}</strong><strong title={target}>{target}</strong><span className={`edge-kind ${edge.category}`}>{edge.kind}</span><code title={edge.expression}>{edge.expression || "—"}</code><small title={locationText(edge)}>{locationText(edge)}</small></button>; })}{edges.length > 500 && <p className="result-cap">Showing 500 of {edges.length} connected edges.</p>}</div> : <EmptyState compact icon={<Table2 size={18} />} title="No connected rows" text="Change direction, depth, or select another node." />;
}

function EmptyState({ icon, title, text, compact = false }: { icon: React.ReactNode; title: string; text: string; compact?: boolean }) {
  return <div className={`empty-state${compact ? " compact" : ""}`}><span>{icon}</span><strong>{title}</strong><p>{text}</p></div>;
}

export default App;
