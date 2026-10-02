import type { NodeRow } from "./loadData";

export interface SearchDoc {
  name: string; lastSegment: string; title: string | null; docFirstLine: string | null;
}

export function buildSearchIndex(nodes: NodeRow[]): SearchDoc[] {
  return nodes.map((n) => ({
    name: n.name,
    lastSegment: n.name.split(".").pop() ?? n.name,
    title: n.title,
    docFirstLine: n.docstring ? (n.docstring.split("\n")[0] ?? null) : null,
  }));
}

export function scoreDoc(d: SearchDoc, qLower: string): number {
  const name = d.name.toLowerCase();
  const last = d.lastSegment.toLowerCase();
  const title = (d.title ?? "").toLowerCase();
  const doc = (d.docFirstLine ?? "").toLowerCase();
  let s = 0;
  if (last.startsWith(qLower)) s = 90;
  else if (name.startsWith(qLower)) s = 70;
  else if (title.startsWith(qLower)) s = 50;
  else if (name.includes(qLower)) s = 40;
  else if (title.includes(qLower)) s = 25;
  else if (doc.includes(qLower)) s = 10;
  return s;
}

export function searchDocs(index: SearchDoc[], q: string, limit = 10): SearchDoc[] {
  const ql = q.trim().toLowerCase();
  if (!ql) return [];
  return index
    .map((d) => ({ d, score: scoreDoc(d, ql) }))
    .filter((x) => x.score > 0)
    // Tie-break: lastSegment ascending, then name ascending. (lastSegment first:
    // docs whose last segments prefix-match a query are shown in lastSegment order,
    // e.g. "fund" -> FundamentalGroup before FundamentalTheorem.)
    .sort(
      (a, b) =>
        b.score - a.score ||
        a.d.lastSegment.localeCompare(b.d.lastSegment) ||
        a.d.name.localeCompare(b.d.name),
    )
    .slice(0, limit)
    .map((x) => x.d);
}
