import type Graph from "graphology";

export interface SalientEdge { a: string; b: string; score: number }

export function rankEdges(g: Graph): SalientEdge[] {
  const out: SalientEdge[] = [];
  g.forEachEdge((_e, attrs, a, b) => {
    // density channel pool: imports only; structure edges never rank
    if ((attrs.rel ?? "import") !== "import") return;
    const ra = g.getNodeAttribute(a, "r") as number;
    const rb = g.getNodeAttribute(b, "r") as number;
    out.push({ a, b, score: ra * rb });
  });
  out.sort((e1, e2) => e2.score - e1.score || e1.a.localeCompare(e2.a) || e1.b.localeCompare(e2.b));
  return out;
}

export function edgeKey(a: string, b: string): string {
  return `${a}→${b}`;
}

export function topKKeys(edges: SalientEdge[], k: number): Set<string> {
  const s = new Set<string>();
  for (const e of edges.slice(0, Math.max(0, k))) s.add(edgeKey(e.a, e.b));
  return s;
}
