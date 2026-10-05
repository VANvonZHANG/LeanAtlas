import Graph from "graphology";
import { describe, expect, it } from "vitest";
import { planRefresh } from "./refreshPlan";

// dep -> importer direction (irrelevant to dirty sets, kept for realism):
// H is a hub imported by A and B; A imports X too.
function fixture(): Graph {
  const g = new Graph({ type: "directed", multi: false });
  for (const n of ["H", "A", "B", "X"]) g.addNode(n);
  g.addEdge("H", "A");
  g.addEdge("H", "B");
  g.addEdge("A", "X");
  return g;
}

// graphology generates opaque edge keys (geid_*), so assertions map them
// back to sorted endpoint pairs.
function edgePairs(g: Graph, keys: string[]): string[] {
  return keys.map((e) => g.extremities(e).sort().join("-")).sort();
}

const HOVER_H = { node: "H", neighbors: ["A", "B"] };
const HOVER_A = { node: "A", neighbors: ["H", "X"] };

describe("planRefresh(hover)", () => {
  it("enter: dirty = node + neighbors + incident edges", () => {
    const g = fixture();
    const plan = planRefresh("hover", g, null, HOVER_H);
    expect(plan).toEqual({
      kind: "partial",
      nodes: ["A", "B", "H"],
      edges: expect.any(Array),
    });
    expect(edgePairs(g, (plan as { edges: string[] }).edges)).toEqual(["A-H", "B-H"]);
  });

  it("leave: same sets (restore path)", () => {
    const g = fixture();
    const plan = planRefresh("hover", g, HOVER_H, null);
    expect((plan as { nodes: string[] }).nodes).toEqual(["A", "B", "H"]);
    expect(edgePairs(g, (plan as { edges: string[] }).edges)).toEqual(["A-H", "B-H"]);
  });

  it("sweep A -> H: union of both sides, deduped and sorted", () => {
    const g = fixture();
    const plan = planRefresh("hover", g, HOVER_A, HOVER_H);
    // from side {A,H,X} ∪ to side {H,A,B} = all four nodes once
    expect((plan as { nodes: string[] }).nodes).toEqual(["A", "B", "H", "X"]);
    expect(edgePairs(g, (plan as { edges: string[] }).edges)).toEqual(["A-H", "A-X", "B-H"]);
  });

  it("same value re-fire: idempotent single side", () => {
    const g = fixture();
    const plan = planRefresh("hover", g, HOVER_A, HOVER_A);
    expect((plan as { nodes: string[] }).nodes).toEqual(["A", "H", "X"]);
    expect(edgePairs(g, (plan as { edges: string[] }).edges)).toEqual(["A-H", "A-X"]);
  });

  it("nanostores immediate-callback oldValue (undefined) is treated as no side", () => {
    const g = fixture();
    expect(planRefresh("hover", g, undefined, null)).toEqual({
      kind: "partial",
      nodes: [],
      edges: [],
    });
    const enter = planRefresh("hover", g, undefined, HOVER_H);
    expect((enter as { nodes: string[] }).nodes).toEqual(["A", "B", "H"]);
    expect(edgePairs(g, (enter as { edges: string[] }).edges)).toEqual(["A-H", "B-H"]);
  });
});

describe("planRefresh(non-hover kinds)", () => {
  const g = fixture();
  it("selection -> full regardless of values", () => {
    expect(planRefresh("selection", g, undefined, undefined)).toEqual({ kind: "full" });
    expect(planRefresh("selection", g, null, { node: "H" })).toEqual({ kind: "full" });
  });
  it("topicFilter -> full", () => {
    expect(planRefresh("topicFilter", g, null, "Algebra")).toEqual({ kind: "full" });
  });
  it("edges -> full", () => {
    expect(planRefresh("edges", g, { enabled: false }, { enabled: true })).toEqual({ kind: "full" });
  });
});

describe("planRefresh(structure/edgeStyle)", () => {
  const g = fixture();
  it("structure toggle change -> full", () => {
    expect(planRefresh("structure", g, undefined, undefined)).toEqual({ kind: "full" });
  });
  it("edgeStyle change -> full", () => {
    expect(planRefresh("edgeStyle", g, undefined, undefined)).toEqual({ kind: "full" });
  });
});
