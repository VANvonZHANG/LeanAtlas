import { describe, expect, it } from "vitest";
import { mergeHits } from "./mixedSearch";
import type { SearchDoc } from "./search";

const MODS: SearchDoc[] = [
  { name: "Mathlib.Order.Basic", lastSegment: "Basic", title: null, docFirstLine: null },
];
const DECLS = [
  { name: "le_iff_eq_or_lt", kind: "theorem", module: "Mathlib.Order.Basic" },
  { name: "Nat.add_succ", kind: "def", module: "Mathlib.Data.Nat.Basic" },
];

describe("mergeHits", () => {
  it("places modules first, declarations below, no cross-ranking", () => {
    expect(mergeHits(MODS, DECLS)).toEqual([
      { type: "module", name: "Mathlib.Order.Basic" },
      { type: "decl", name: "le_iff_eq_or_lt", kind: "theorem", module: "Mathlib.Order.Basic" },
      { type: "decl", name: "Nat.add_succ", kind: "def", module: "Mathlib.Data.Nat.Basic" },
    ]);
  });

  it("tolerates empty halves", () => {
    expect(mergeHits([], DECLS)).toHaveLength(2);
    expect(mergeHits(MODS, [])).toEqual([{ type: "module", name: "Mathlib.Order.Basic" }]);
  });
});
