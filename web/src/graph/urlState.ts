export interface UrlState {
  node?: string; topic?: string; edges?: number; z?: number; x?: number; y?: number;
}

export function serializeUrl(s: UrlState): string {
  const parts: string[] = [];
  if (s.node) parts.push(`node=${encodeURIComponent(s.node)}`);
  if (s.topic) parts.push(`topic=${encodeURIComponent(s.topic)}`);
  if (s.edges !== undefined) parts.push(`edges=${Math.round(s.edges)}`);
  if (s.z !== undefined) parts.push(`z=${s.z.toFixed(3)}`);
  if (s.x !== undefined) parts.push(`x=${s.x.toFixed(2)}`);
  if (s.y !== undefined) parts.push(`y=${s.y.toFixed(2)}`);
  return `#${parts.join("&")}`;
}

export function parseUrl(hash: string): UrlState {
  const out: UrlState = {};
  const body = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!body) return out;
  for (const kv of body.split("&")) {
    const [k, v] = kv.split("=");
    if (k === undefined || v === undefined) continue;
    const val = decodeURIComponent(v);
    if (k === "node" || k === "topic") out[k] = val;
    else if (k === "edges") {
      const n = Number(val);
      if (Number.isFinite(n)) out.edges = Math.min(100, Math.max(0, Math.round(n)));
    } else if (k === "z" || k === "x" || k === "y") {
      const n = Number(val);
      if (Number.isFinite(n)) out[k] = n;
    }
  }
  return out;
}
