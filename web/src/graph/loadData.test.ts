import { readFileSync } from "node:fs";
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
  ],
  edges: [[0, 1]],
} as const;

describe("loadData", () => {
  it("rejects unsupported schemaVersion", async () => {
    const bad = { ...doc, schemaVersion: 2 };
    globalThis.fetch = (async () =>
      new Response(JSON.stringify(bad))) as typeof fetch;
    await expect(loadData()).rejects.toThrow(/schemaVersion/);
  });
  it("returns doc for v1", async () => {
    globalThis.fetch = (async () =>
      new Response(JSON.stringify(doc))) as typeof fetch;
    const got = await loadData();
    expect(got.nodes).toHaveLength(2);
  });
  it("real public/data.json loads and passes version check", async () => {
    const raw = readFileSync(resolve(__dirname, "../../public/data.json"), "utf8");
    globalThis.fetch = (async () => new Response(raw)) as typeof fetch;
    const got = await loadData();
    expect(got.schemaVersion).toBe(1);
    expect(got.nodes.length).toBeGreaterThan(8000);
  });
});

describe("buildGraph", () => {
  it("preset coords (y negated) and edge attrs", () => {
    const g = buildGraph(doc as never);
    expect(g.getNodeAttribute("Mathlib.A", "x")).toBe(0);
    expect(g.getNodeAttribute("Mathlib.B", "y")).toBe(-100);
    expect(g.getNodeAttribute("Mathlib.B", "size")).toBe(4);
    expect(g.getEdgeAttribute("Mathlib.A", "Mathlib.B", "color")).toBe("#26304a");
  });
});
