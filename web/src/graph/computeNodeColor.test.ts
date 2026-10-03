import { describe, expect, it } from "vitest";
import { computeNodeColor } from "./computeNodeColor";

const attrs = { color: "#ffff00", topic: "Algebra" };
const sel = {
  node: "HUB",
  neighbors: ["N1"],
  closure: new Set(["N2", "N3"]),
};

describe("computeNodeColor", () => {
  it("defaults to original color", () => {
    expect(computeNodeColor("X", attrs, { selection: null, topicFilter: null, hover: null })).toBe("#ffff00");
  });
  it("selection: direct neighbors original, closure 45% alpha, others dark unless topicFilter", () => {
    const st = { selection: sel, topicFilter: null, hover: null };
    expect(computeNodeColor("HUB", attrs, st)).toBe("#ffff00");
    expect(computeNodeColor("N1", attrs, st)).toBe("#ffff00");
    expect(computeNodeColor("N2", attrs, st)).toBe("rgba(255,255,0,0.45)");
    expect(computeNodeColor("X", attrs, st)).toBe("#151a26");
  });
  it("selection + topicFilter: filter governs non-selection nodes", () => {
    const st = { selection: sel, topicFilter: "Topology", hover: null };
    expect(computeNodeColor("N2", attrs, st)).toBe("rgba(255,255,0,0.45)"); // closure wins over filter
    expect(computeNodeColor("X", attrs, st)).toBe("rgba(255,255,0,0.15)"); // not in filtered topic
    const inTopic = { color: "#00ffff", topic: "Topology" };
    expect(computeNodeColor("Y", inTopic, st)).toBe("#00ffff");
  });
  it("topicFilter alone: in-topic original, out 15% alpha", () => {
    const st = { selection: null, topicFilter: "Algebra", hover: null };
    expect(computeNodeColor("X", attrs, st)).toBe("#ffff00");
    expect(computeNodeColor("X", { color: "#00ffff", topic: "Analysis" }, st)).toBe("rgba(0,255,255,0.15)");
  });
  it("hover restores dimmed nodes when no selection", () => {
    const st = { selection: null, topicFilter: "Algebra", hover: "X" };
    const out = { color: "#00ffff", topic: "Analysis" };
    expect(computeNodeColor("X", out, st)).toBe("#00ffff"); // hovered itself restored
    expect(computeNodeColor("Y", out, st)).toBe("rgba(0,255,255,0.15)");
  });
});
