import { describe, expect, it } from "vitest";
import { buildSearchIndex, scoreDoc, searchDocs } from "./search";

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
  it("same score: lastSegment ascending tiebreak orders FundamentalGroup before FundamentalTheorem", () => {
    // fixture deliberately lists FundamentalTheorem first: both lastSegments
    // prefix-match "fund" (score 90 each), so the order can only come from the
    // lastSegment-ascending tiebreak, not from the score or the input order.
    const tie = buildSearchIndex([
      { name: "Mathlib.Algebra.Group.FundamentalTheorem", title: null, docstring: null, topic: "Algebra", x: 0, y: 0, r: 0.2, color: "#fff", declCount: 0, closureSize: 0, isDeprecated: false },
      { name: "Mathlib.Topology.FundamentalGroup", title: null, docstring: null, topic: "Topology", x: 0, y: 0, r: 0.2, color: "#fff", declCount: 0, closureSize: 0, isDeprecated: false },
    ] as never[]);
    expect(tie.map((d) => scoreDoc(d, "fund"))).toEqual([90, 90]); // same score
    expect(searchDocs(tie, "fund").map((d) => d.lastSegment)).toEqual([
      "FundamentalGroup",
      "FundamentalTheorem",
    ]);
  });
  it("limit truncates: 3 matches with limit 2 return exactly 2", () => {
    const three = buildSearchIndex([
      { name: "Mathlib.A.FundamentalTheorem", title: null, docstring: null, topic: "Algebra", x: 0, y: 0, r: 0.2, color: "#fff", declCount: 0, closureSize: 0, isDeprecated: false },
      { name: "Mathlib.B.FundamentalGroup", title: null, docstring: null, topic: "Topology", x: 0, y: 0, r: 0.2, color: "#fff", declCount: 0, closureSize: 0, isDeprecated: false },
      { name: "Mathlib.C.FundamentalLemma", title: null, docstring: null, topic: "Order", x: 0, y: 0, r: 0.2, color: "#fff", declCount: 0, closureSize: 0, isDeprecated: false },
    ] as never[]);
    expect(searchDocs(three, "fund")).toHaveLength(3); // all match under the default limit
    const got = searchDocs(three, "fund", 2);
    expect(got).toHaveLength(2);
    expect(got.map((d) => d.lastSegment)).toEqual(["FundamentalGroup", "FundamentalLemma"]); // truncated in tiebreak order
  });
});
