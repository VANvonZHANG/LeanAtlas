import type Graph from "graphology";

export function neighborsOf(g: Graph, node: string): { deps: string[]; dependents: string[] } {
  const deps: string[] = [], dependents: string[] = [];
  for (const d of g.neighbors(node)) {
    // edge direction: dep -> importer; node imports d iff edge d -> node exists
    if (g.hasEdge(d, node)) deps.push(d);
    else dependents.push(d);
  }
  return { deps: deps.sort(), dependents: dependents.sort() };
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
