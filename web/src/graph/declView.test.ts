import { beforeEach, describe, expect, it } from "vitest";
import type { DeclBlock } from "./declPack";
import { hoverStore, topicFilterStore, selectionStore, viewStore } from "../state/stores";
import { backToOverview, buildDeclGraph, drillTo, kindColor } from "./declView";

const BLOCK: DeclBlock = {
  schemaVersion: 1,
  module: "M.A",
  decls: [
    { name: "M.A.thm", k: "theorem", x: 0, y: 0, s: 1.5 },
    { name: "M.A.f", k: "def", x: 1, y: 0, s: 2.5 },
    { name: "M.A.odd", k: "macro", x: 2, y: 0, s: 1.5 },
  ],
  e: [[1, 0], [1, 0], [1, 1]], // duplicate pair + self-loop: both dropped
};

describe("buildDeclGraph", () => {
  it("sets kind colors, short labels, and InfoPanel stand-in attrs", () => {
    const g = buildDeclGraph(BLOCK);
    const a = g.getNodeAttributes("M.A.thm");
    expect(a.color).toBe("#7fd1b9");
    expect(a.label).toBe("thm");
    expect(a.title).toBe("M.A.thm");
    expect(a.topic).toBe("theorem"); // InfoPanel's topic line shows the kind
    expect(a.declCount).toBe(0); // thm is a dependency, not a user
    expect(g.getNodeAttributes("M.A.f").declCount).toBe(1); // f depends on thm
  });

  it("adds dependency edges with the import relation, dropping self-loops and duplicates", () => {
    const g = buildDeclGraph(BLOCK);
    expect(g.size).toBe(1); // graphology 0.26 edge count is the `size` property
    expect(g.getEdgeAttributes("M.A.f", "M.A.thm").rel).toBe("import");
  });

  it("falls back to a default color for unknown kinds", () => {
    expect(buildDeclGraph(BLOCK).getNodeAttributes("M.A.odd").color).toBe(kindColor("macro"));
    expect(kindColor("macro")).toBe("#9aa4bf");
  });
});

describe("view transitions", () => {
  beforeEach(() => {
    viewStore.set({ mode: "overview" });
    selectionStore.set(null);
    topicFilterStore.set(null);
    hoverStore.set(null);
  });

  it("drillTo clears overview interactions and switches the view", () => {
    selectionStore.set({ node: "Mathlib.X", neighbors: [], closure: new Set(["Mathlib.X"]) });
    topicFilterStore.set("Algebra");
    hoverStore.set({ node: "Mathlib.X", neighbors: [] });
    drillTo("Mathlib.X");
    expect(viewStore.get()).toEqual({ mode: "decls", module: "Mathlib.X" });
    expect(selectionStore.get()).toBeNull();
    expect(topicFilterStore.get()).toBeNull();
    expect(hoverStore.get()).toBeNull();
  });

  it("backToOverview returns to overview and clears the selection", () => {
    drillTo("Mathlib.X");
    selectionStore.set({ node: "M.A.f", neighbors: [], closure: new Set() });
    hoverStore.set({ node: "M.A.f", neighbors: [] });
    backToOverview();
    expect(viewStore.get()).toEqual({ mode: "overview" });
    expect(selectionStore.get()).toBeNull();
    expect(hoverStore.get()).toBeNull();
  });
});
