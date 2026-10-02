import Graph from "graphology";
import { describe, expect, it } from "vitest";
import { closureOf, neighborsOf } from "./bfs";

function g() {
  const g = new Graph({ type: "directed", multi: false });
  for (const n of ["A", "B", "C", "D"]) g.addNode(n);
  // addEdgesFrom does not exist in graphology 0.26; adapted to per-edge addEdge
  for (const [a, b] of [["A", "B"], ["A", "C"], ["B", "D"], ["C", "D"]] as const)
    g.addEdge(a, b); // dep -> importer
  return g;
}

describe("bfs", () => {
  it("neighborsOf splits directions", () => {
    expect(neighborsOf(g(), "A")).toEqual({ deps: [], dependents: ["B", "C"] });
    expect(neighborsOf(g(), "D")).toEqual({ deps: ["B", "C"], dependents: [] });
  });
  it("closureOf is transitive and excludes self", () => {
    const { deps, dependents } = closureOf(g(), "A");
    expect([...dependents].sort()).toEqual(["B", "C", "D"]);
    expect(deps.size).toBe(0);
    const d = closureOf(g(), "D");
    expect([...d.deps].sort()).toEqual(["A", "B", "C"]);
  });
});
