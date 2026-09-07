import { useEffect, useMemo, useState } from "react";
import { createGraphIndex, findColumnPaths } from "./data";
import type { LineageEdge, LineageNode, NormalizedLineageGraph } from "./data";
import "./path-finder.css";

export interface PathFinderProps {
  graph: NormalizedLineageGraph;
  onSelect: (id: string) => void;
}

type KindFilter = "VALUE" | "FILTER" | "all";
type Endpoint = "source" | "target";

const MAX_CANDIDATES = 40;
const PATH_BOUNDS = { maxDepth: 12, maxPaths: 20, maxVisited: 10_000 } as const;

function refLabel(node: LineageNode): string {
  if (!node.ref) return node.displayName;
  const table = node.ref.dblink && !node.ref.table.includes("@")
    ? `${node.ref.table}@${node.ref.dblink}`
    : node.ref.table;
  return node.ref.column ? `${table}.${node.ref.column}` : table;
}

function evidenceLabel(edge: LineageEdge): string | null {
  const evidence = edge.evidence;
  if (!evidence) return null;
  const location = evidence.file
    ? `${evidence.file}${evidence.line === undefined ? "" : `:${evidence.line}`}`
    : evidence.line === undefined ? "" : `line ${evidence.line}`;
  const routine = [evidence.package, evidence.function ?? evidence.procedure].filter(Boolean).join(".");
  return [location, routine].filter(Boolean).join(" · ") || null;
}

function matchesKind(edge: LineageEdge, filter: KindFilter): boolean {
  if (filter === "VALUE") return edge.category === "value";
  if (filter === "FILTER") return edge.category === "control";
  return true;
}

export function PathFinder({ graph, onSelect }: PathFinderProps) {
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [targetId, setTargetId] = useState<string | null>(null);
  const [sourceQuery, setSourceQuery] = useState("");
  const [targetQuery, setTargetQuery] = useState("");
  const [kind, setKind] = useState<KindFilter>("VALUE");

  const columns = useMemo(
    () => graph.nodes.filter((node) => node.type === "column").sort((a, b) => refLabel(a).localeCompare(refLabel(b))),
    [graph],
  );
  const columnById = useMemo(() => new Map(columns.map((node) => [node.id, node])), [columns]);

  useEffect(() => {
    if (sourceId && !columnById.has(sourceId)) setSourceId(null);
    if (targetId && !columnById.has(targetId)) setTargetId(null);
  }, [columnById, sourceId, targetId]);

  const filteredGraph = useMemo(
    () => ({ ...graph, edges: graph.edges.filter((edge) => matchesKind(edge, kind)) }),
    [graph, kind],
  );
  const index = useMemo(() => createGraphIndex(filteredGraph), [filteredGraph]);
  const result = useMemo(
    () => sourceId && targetId ? findColumnPaths(index, sourceId, targetId, PATH_BOUNDS) : null,
    [index, sourceId, targetId],
  );

  const choose = (endpoint: Endpoint, node: LineageNode) => {
    if (endpoint === "source") {
      setSourceId(node.id);
      setSourceQuery("");
    } else {
      setTargetId(node.id);
      setTargetQuery("");
    }
    onSelect(node.id);
  };

  const renderPicker = (endpoint: Endpoint) => {
    const selectedId = endpoint === "source" ? sourceId : targetId;
    const query = endpoint === "source" ? sourceQuery : targetQuery;
    const setQuery = endpoint === "source" ? setSourceQuery : setTargetQuery;
    const selected = selectedId ? columnById.get(selectedId) : undefined;
    const folded = query.trim().toLocaleLowerCase();
    const matches = columns
      .filter((node) => !folded || `${refLabel(node)} ${node.id}`.toLocaleLowerCase().includes(folded))
      .slice(0, MAX_CANDIDATES);
    const label = endpoint === "source" ? "Source column" : "Target column";
    return (
      <div className="path-picker" data-testid={`${endpoint}-column-picker`}>
        <label htmlFor={`path-${endpoint}-search`}>{label}</label>
        {selected && (
          <div className="path-picker__selected">
            <button type="button" onClick={() => onSelect(selected.id)} title={selected.id}>{refLabel(selected)}</button>
            <button
              type="button"
              className="path-picker__clear"
              aria-label={`Clear ${label.toLowerCase()}`}
              onClick={() => endpoint === "source" ? setSourceId(null) : setTargetId(null)}
            >×</button>
          </div>
        )}
        <input
          id={`path-${endpoint}-search`}
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={selected ? "Choose a different column" : "Search table or column"}
          autoComplete="off"
          aria-controls={`path-${endpoint}-options`}
        />
        {query.trim() && (
          <div id={`path-${endpoint}-options`} className="path-picker__options" role="listbox" aria-label={`${label} matches`}>
            {matches.map((node) => (
              <button key={node.id} type="button" role="option" aria-selected={node.id === selectedId} onClick={() => choose(endpoint, node)}>
                <span>{refLabel(node)}</span><small>{node.id}</small>
              </button>
            ))}
            {!matches.length && <p>No matching columns.</p>}
            {matches.length === MAX_CANDIDATES && <p>Showing the first {MAX_CANDIDATES} matches. Refine the search.</p>}
          </div>
        )}
      </div>
    );
  };

  return (
    <section className="path-finder" aria-labelledby="path-finder-title" data-testid="path-finder">
      <div className="path-finder__heading">
        <div><h2 id="path-finder-title">Column path</h2><p>Trace directed lineage from a source column to a target column.</p></div>
        <label className="path-kind" htmlFor="path-kind-filter">
          Relationship
          <select id="path-kind-filter" value={kind} onChange={(event) => setKind(event.target.value as KindFilter)}>
            <option value="VALUE">Value</option>
            <option value="FILTER">Filter</option>
            <option value="all">All</option>
          </select>
        </label>
      </div>
      <div className="path-finder__pickers">{renderPicker("source")}<span className="path-finder__arrow" aria-hidden="true">→</span>{renderPicker("target")}</div>

      {!sourceId || !targetId ? (
        <div className="path-finder__empty">Choose both columns to find a directed path.</div>
      ) : result && result.paths.length ? (
        <div className="path-results" aria-live="polite">
          <div className="path-results__summary">
            <strong>{result.paths.length} path{result.paths.length === 1 ? "" : "s"}</strong>
            {result.truncated && <span>Results reached the search limit; additional paths may exist.</span>}
          </div>
          {result.paths.map((path, pathIndex) => (
            <details key={path.edgeIds.join("|")} open={pathIndex === 0} data-testid="lineage-path">
              <summary>Path {pathIndex + 1} · {path.edgeIds.length} hop{path.edgeIds.length === 1 ? "" : "s"}</summary>
              <ol>
                {path.edgeIds.map((edgeId, edgeIndex) => {
                  const edge = index.edgeById.get(edgeId)!;
                  const source = index.nodeById.get(edge.sourceId)!;
                  const target = index.nodeById.get(edge.targetId)!;
                  const evidence = evidenceLabel(edge);
                  return (
                    <li key={edge.id}>
                      <div className="path-step__route">
                        <button type="button" onClick={() => onSelect(source.id)}>{refLabel(source)}</button>
                        <span aria-label="flows to">→</span>
                        <button type="button" onClick={() => onSelect(target.id)}>{refLabel(target)}</button>
                      </div>
                      <div className="path-step__meta"><span>{edge.kind}</span><code>{edge.expression || "No expression recorded"}</code></div>
                      {evidence && <div className="path-step__evidence">Evidence: {evidence}</div>}
                      {edgeIndex < path.edgeIds.length - 1 && <span className="path-step__continuation" aria-hidden="true" />}
                    </li>
                  );
                })}
              </ol>
            </details>
          ))}
        </div>
      ) : (
        <div className="path-finder__empty" role="status" data-testid="no-path-result">
          {result?.truncated
            ? "No path was found within the search limits. A longer path may still exist."
            : `No directed ${kind === "all" ? "" : kind.toLocaleLowerCase() + " "}path connects these columns.`}
        </div>
      )}
    </section>
  );
}
