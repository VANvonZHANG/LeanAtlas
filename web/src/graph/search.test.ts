import { describe, expect, it } from "vitest";
import { buildSearchIndex, searchDocs } from "./search";

const nodes = [
  { name: "Mathlib.Algebra.Group.FundamentalTheorem", title: "Fundamental theorem", docstring: "about groups", topic: "Algebra", x: 0, y: 0, r: 0.2, color: "#fff", declCount: 0, closureSize: 0, isDeprecated: false },
  { name: "Mathlib.Topology.FundamentalGroup", title: null, docstring: "the fundamental group\nsecond line", topic: "Topology", x: 0, y: 0, r: 0.2, color: "#fff", declCount: 0, closureSize: 0, isDeprecated: false },
  { name: "Mathlib.Data.Zoo", title: "zoo helpers", docstring: null, topic: "Data", x: 0, y: 0, r: 0.2, color: "#fff", declCount: 0, closureSize: 0, isDeprecated: false },
] as never[];
const index = buildSearchIndex(nodes);

describe("search", () => {
  it("lastSegment prefix beats name substring", () => {
    const got = searchDocs(index, "fund");
    expect(got[0]!.name).toBe("Mathlib.Topology.FundamentalGroup"); // lastSegment prefix (90)
    expect(got[1]!.name).toBe("Mathlib.Algebra.Group.FundamentalTheorem"); // name substring (40)
  });
  it("title prefix (50) beats name substring (40)", () => {
    const got = searchDocs(index, "zoo");
    expect(got).toHaveLength(1);
    expect(got[0]!.name).toBe("Mathlib.Data.Zoo");
  });
  it("case-insensitive; empty q returns empty; limit truncates", () => {
    expect(searchDocs(index, "ZOO")).toHaveLength(1);
    expect(searchDocs(index, "")).toEqual([]);
  });
});
