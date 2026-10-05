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

describe("se bitmask", () => {
  it("serializes non-default masks and omits 7", () => {
    expect(serializeUrl({ se: 7 })).toBe("#");
    expect(serializeUrl({ se: 5 })).toBe("#se=5");
  });
  it("parses and clamps", () => {
    expect(parseUrl("#se=5")).toEqual({ se: 5 });
    expect(parseUrl("#se=abc&se=-3&se=12").se).toBe(7);
    expect(parseUrl("#se=2")).toEqual({ se: 2 });
  });
  it("round-trips", () => {
    expect(parseUrl(serializeUrl({ se: 3 }))).toEqual({ se: 3 });
  });
});
