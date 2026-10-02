import Graph from "graphology";

export interface TopicRow { id: string; label: string; y: number; color: string }
export interface NodeRow {
  name: string; topic: string; x: number; y: number; r: number; color: string;
  declCount: number; closureSize: number; isDeprecated: boolean;
  title: string | null; docstring: string | null;
}
export interface DataDoc {
  schemaVersion: number;
  meta: { version: string; generatedAt: string; scope: string; stats: Record<string, number> };
  topics: TopicRow[];
  nodes: NodeRow[];
  edges: [number, number][];
}

export async function loadData(url = "data.json"): Promise<DataDoc> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`loadData: fetch ${url} -> ${res.status}`);
  const doc = (await res.json()) as DataDoc;
  if (doc.schemaVersion !== 1)
    throw new Error(`loadData: unsupported schemaVersion ${doc.schemaVersion}`);
  return doc;
}

export function buildGraph(doc: DataDoc): Graph {
  const g = new Graph({ type: "directed", multi: false });
  for (const n of doc.nodes) {
    g.addNode(n.name, {
      x: n.x,
      y: -n.y, // negate so low band values (Probability=20) render on top
      size: n.r * 2,
      color: n.color,
      label: n.name.split(".").slice(-2).join("."),
      title: n.title ?? n.name,
      declCount: n.declCount,
      closureSize: n.closureSize,
      topic: n.topic,
      r: n.r,
    });
  }
  for (const [a, b] of doc.edges) {
    const s = doc.nodes[a]!.name, t = doc.nodes[b]!.name;
    if (!g.hasEdge(s, t)) g.addEdge(s, t, { color: "#26304a", size: 0.5 });
  }
  return g;
}
