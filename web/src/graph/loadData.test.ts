import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { buildGraph, loadData } from "./loadData";

const doc = {
  schemaVersion: 1,
  meta: { version: "t", generatedAt: "t", scope: "mathlib", stats: {} },
  topics: [{ id: "Algebra", label: "Algebra", y: 100, color: "#ffff00" }],
  nodes: [
    { name: "Mathlib.A", topic: "Algebra", x: 0, y: 100, r: 1, color: "#ffff00",
      declCount: 1, closureSize: 0, isDeprecated: false, title: null, docstring: null },
    { name: "Mathlib.B", topic: "Algebra", x: 1.5, y: 100, r: 2, color: "#ffff00",
      declCount: 2, closureSize: 1, isDeprecated: false, title: "B", docstring: "d" },
    { name: "Mathlib.C", topic: "Algebra", x: 3, y: 100, r: 1.5, color: "#ffff00",
      declCount: 3, closureSize: 2, isDeprecated: false, title: "C", docstring: null },
  ],
  edges: [[0, 1]],
  structureEdges: { extends: [], instantiates: [], fields: [] },
} as const;

describe("loadData", () => {
  it("rejects unsupported schemaVersion", async () => {
    const bad = { ...doc, schemaVersion: 1 };
    globalThis.fetch = (async () =>
      new Response(JSON.stringify(bad))) as typeof fetch;
    await expect(loadData()).rejects.toThrow(/schemaVersion/);
  });
  it("returns doc for v2", async () => {
    const v2 = { ...doc, schemaVersion: 2, structureEdges: { extends: [], instantiates: [], fields: [] } } as never;
    globalThis.fetch = (async () =>
      new Response(JSON.stringify(v2))) as typeof fetch;
    const got = await loadData();
    expect(got.nodes).toHaveLength(3);
  });
  // guard: real data.json is gitignored (built by `leanatlas layout`); skip when absent
  const maybeRealData = existsSync(resolve(__dirname, "../../public/data.json")) ? it : it.skip;
  maybeRealData("loads real v2 public/data.json and builds the graph from it", async () => {
    const raw = readFileSync(resolve(__dirname, "../../public/data.json"), "utf8");
    globalThis.fetch = (async () => new Response(raw)) as typeof fetch;
    const got = await loadData();
    expect(got.nodes.length).toBeGreaterThan(8000);
    const g = buildGraph(got);
    expect(g.order).toBeGreaterThan(8000);
    expect(g.size).toBeGreaterThan(0);
  });
});

describe("buildGraph", () => {
  it("preset coords (y negated) and edge attrs", () => {
    const g = buildGraph(doc as never);
    expect(g.getNodeAttribute("Mathlib.A", "x")).toBe(0);
    expect(g.getNodeAttribute("Mathlib.B", "y")).toBe(-100);
    expect(g.getNodeAttribute("Mathlib.B", "size")).toBe(4);
    // multi graph: pair-form attribute lookup is ambiguous, use the edge key
    expect(g.getEdgeAttribute(g.edges()[0], "color")).toBe("#26304a");
  });
});

const doc2 = {
  ...doc, schemaVersion: 2,
  structureEdges: { extends: [[0, 1]], instantiates: [[1, 2]], fields: [] },
} as never;

describe("v2 structure edges", () => {
  it("rejects v1 data", async () => {
    const v1 = { ...doc, structureEdges: { extends: [], instantiates: [], fields: [] } } as never;
    globalThis.fetch = (async () => new Response(JSON.stringify(v1))) as typeof fetch;
    await expect(loadData()).rejects.toThrow(/schemaVersion/);
  });
  it("loads v2 and attaches rel attrs with parallel edges", () => {
    const g = buildGraph(doc2 as never);
    const rels = g.edges().map((e) => g.getEdgeAttribute(e, "rel"));
    expect(rels.filter((r) => r === "import").length).toBe(1);
    expect(rels.filter((r) => r === "extends").length).toBe(1);
    expect(rels.filter((r) => r === "instantiates").length).toBe(1);
  });
  it("parallel edges coexist: extends + import between same pair", () => {
    const both = { ...doc, schemaVersion: 2,
      structureEdges: { extends: [[0, 1]], instantiates: [], fields: [] } } as never;
    const g = buildGraph(both as never);
    expect(g.edges().length).toBe(2); // import 0->1 plus extends 0->1
  });
});
