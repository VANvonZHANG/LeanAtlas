import type Graph from "graphology";

// Relation-aware neighbor walk: only import edges participate. On the
// multi-relation graph, hasEdge/neighbors see all edge kinds, so edges are
// inspected per-relation instead. Edge direction: dep -> importer.
function importNeighbors(g: Graph, node: string): { deps: string[]; dependents: string[] } {
  const deps: string[] = [], dependents: string[] = [];
  for (const e of g.edges(node)) {
    if ((g.getEdgeAttribute(e, "rel") ?? "import") !== "import") continue;
    const [source, target] = g.extremities(e);
    if (target === node) deps.push(source);
    else dependents.push(target);
  }
  return { deps: deps.sort(), dependents: dependents.sort() };
}

export function neighborsOf(g: Graph, node: string) {
  return importNeighbors(g, node);
}

export function closureOf(g: Graph, node: string): { deps: Set<string>; dependents: Set<string> } {
  const walk = (expand: (n: string) => string[]): Set<string> => {
    const seen = new Set<string>();
    const queue = [...expand(node)];
    while (queue.length) {
      const v = queue.pop()!;
      if (seen.has(v) || v === node) continue;
      seen.add(v);
      queue.push(...expand(v));
    }
    return seen;
  };
  return {
    deps: walk((n) => neighborsOf(g, n).deps),
    dependents: walk((n) => neighborsOf(g, n).dependents),
  };
}
