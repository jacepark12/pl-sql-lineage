/** Localhost live-focus client: `?live=http://127.0.0.1:8765`. */

export type AgentFocusEdge = {
  kind: string;
  source: string;
  target: string;
};

export type AgentFocus = {
  v: number;
  ts?: string;
  tool: string | null;
  seed: string | null;
  columns: string[];
  edges: AgentFocusEdge[];
  graph: string | null;
  seq?: number;
  truncated?: boolean;
  omitted_columns?: number;
  omitted_edges?: number;
  note?: string | null;
};

export type LiveStatus = "off" | "connecting" | "live" | "error";

export function parseLiveOrigin(search: string): string | null {
  const query = search.startsWith("?") ? search.slice(1) : search;
  const raw = new URLSearchParams(query).get("live");
  if (!raw) return null;
  try {
    const url = new URL(raw);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (url.hostname !== "127.0.0.1" && url.hostname !== "localhost") return null;
    return url.origin;
  } catch {
    return null;
  }
}

export async function sha256Prefixed(data: ArrayBuffer): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", data);
  const hex = [...new Uint8Array(hash)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `sha256:${hex}`;
}

export function parseFocusEvent(raw: unknown): AgentFocus | null {
  if (!raw || typeof raw !== "object") return null;
  const value = raw as Record<string, unknown>;
  const columns = Array.isArray(value.columns)
    ? value.columns.filter((item): item is string => typeof item === "string")
    : [];
  const edges = Array.isArray(value.edges)
    ? value.edges.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const edge = item as Record<string, unknown>;
      if (typeof edge.source !== "string" || typeof edge.target !== "string") return [];
      return [{ kind: typeof edge.kind === "string" ? edge.kind : "DIRECT", source: edge.source, target: edge.target }];
    })
    : [];
  return {
    v: typeof value.v === "number" ? value.v : 1,
    ts: typeof value.ts === "string" ? value.ts : undefined,
    tool: typeof value.tool === "string" ? value.tool : null,
    seed: typeof value.seed === "string" ? value.seed : null,
    columns,
    edges,
    graph: typeof value.graph === "string" ? value.graph : null,
    seq: typeof value.seq === "number" ? value.seq : undefined,
    truncated: Boolean(value.truncated),
    omitted_columns: typeof value.omitted_columns === "number" ? value.omitted_columns : 0,
    omitted_edges: typeof value.omitted_edges === "number" ? value.omitted_edges : 0,
    note: typeof value.note === "string" ? value.note : null,
  };
}

export function graphsMatch(liveSha: string | null, focusSha: string | null): boolean {
  if (!liveSha || !focusSha) return false;
  return liveSha === focusSha;
}

export async function invokeLiveTool(origin: string, payload: Record<string, unknown>): Promise<string> {
  const response = await fetch(`${origin}/invoke`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(text.trim() || `invoke failed (${response.status})`);
  return text;
}

export function subscribeLiveFocus(
  origin: string,
  onFocus: (focus: AgentFocus) => void,
  onStatus: (status: Exclude<LiveStatus, "off">, detail?: string) => void,
): () => void {
  const source = new EventSource(`${origin}/events`);
  const handle = (event: MessageEvent<string>) => {
    try {
      const parsed = parseFocusEvent(JSON.parse(event.data) as unknown);
      if (parsed && (parsed.columns.length || parsed.edges.length || parsed.tool)) onFocus(parsed);
    } catch {
      /* ignore malformed frames */
    }
  };
  source.addEventListener("focus", handle as EventListener);
  source.onopen = () => onStatus("live");
  source.onerror = () => onStatus("error", "Live events disconnected. Retrying…");
  return () => {
    source.removeEventListener("focus", handle as EventListener);
    source.close();
  };
}
