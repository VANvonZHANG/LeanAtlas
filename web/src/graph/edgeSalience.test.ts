import Graph from "graphology";
import { describe, expect, it } from "vitest";
import { rankEdges, topKKeys } from "./edgeSalience";

describe("edgeSalience", () => {
  it("ranks by r(a)*r(b) desc, name-asc tiebreak, stable", () => {
    const g = new Graph({ type: "directed", multi: false });
    for (const [n, r] of [["X", 3], ["Y", 2], ["Z", 2]] as const) g.addNode(n, { r });
    g.addEdge("X", "Y"); // 6
    g.addEdge("Y", "Z"); // 4
    g.addEdge("X", "Z"); // 6, tie with X->Y? no: 3*2=6 both; tiebreak a asc then b asc: X→Y before X→Z
    const ranked = rankEdges(g);
    expect(ranked.map((e) => `${e.a}→${e.b}`)).toEqual(["X→Y", "X→Z", "Y→Z"]);
  });
  it("topKKeys returns key set", () => {
    const edges = [
      { a: "X", b: "Y", score: 6 },
      { a: "X", b: "Z", score: 6 },
      { a: "Y", b: "Z", score: 4 },
    ];
    expect(topKKeys(edges, 2)).toEqual(new Set(["X→Y", "X→Z"]));
    expect(topKKeys(edges, 0)).toEqual(new Set());
  });
});

describe("edgeSalience on multi-relation graph", () => {
  it("rankEdges pools imports only", () => {
    const g = new Graph({ type: "directed", multi: true });
    for (const [n, r] of [["X", 3], ["Y", 2]] as const) g.addNode(n, { r });
    g.addEdge("X", "Y", { rel: "import" });
    g.addEdge("X", "Y", { rel: "extends" }); // same pair, structure: excluded from pool
    const ranked = rankEdges(g);
    expect(ranked).toHaveLength(1);
    expect(`${ranked[0]!.a}→${ranked[0]!.b}`).toBe("X→Y");
  });
});
