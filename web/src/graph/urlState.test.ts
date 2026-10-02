import { describe, expect, it } from "vitest";
import { parseUrl, serializeUrl } from "./urlState";

describe("urlState", () => {
  it("round-trips full state with rounding", () => {
    const s = { node: "Mathlib.A", topic: "Algebra", edges: 30, z: 1.23456, x: 12.345, y: -6.789 };
    const again = parseUrl(serializeUrl(s));
    expect(again).toEqual({ node: "Mathlib.A", topic: "Algebra", edges: 30, z: 1.235, x: 12.35, y: -6.79 });
  });
  it("omits undefined fields; empty -> bare hash", () => {
    expect(serializeUrl({})).toBe("#");
    expect(parseUrl("")).toEqual({});
    expect(parseUrl("#topic=Order&edges=120")).toEqual({ topic: "Order", edges: 100 });
  });
  it("ignores garbage numbers", () => {
    expect(parseUrl("#edges=abc&z=NaN&node=X")).toEqual({ node: "X" });
  });
});
