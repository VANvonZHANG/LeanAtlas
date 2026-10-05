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

describe("bfs on multi-relation graph", () => {
  function mg() {
    const g = new Graph({ type: "directed", multi: true });
    for (const n of ["A", "B", "C"]) g.addNode(n);
    g.addEdge("A", "B", { rel: "import" });       // dep -> importer
    g.addEdge("A", "B", { rel: "extends" });      // same pair, structure relation
    g.addEdge("C", "B", { rel: "instantiates" }); // structure endpoint only
    return g;
  }
  it("neighborsOf counts import endpoints only (structure edges are not deps)", () => {
    expect(neighborsOf(mg(), "B")).toEqual({ deps: ["A"], dependents: [] });
  });
  it("closureOf never traverses structure edges", () => {
    const { deps, dependents } = closureOf(mg(), "A");
    expect([...dependents].sort()).toEqual(["B"]);
    expect(dependents.has("C")).toBe(false);
    const b = closureOf(mg(), "B");
    expect([...b.deps].sort()).toEqual(["A"]); // C is reachable only via the instantiates edge
    expect(deps.size).toBe(0);
  });
});
