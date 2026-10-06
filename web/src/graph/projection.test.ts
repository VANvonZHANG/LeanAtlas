import { describe, expect, it } from "vitest";
import { projectAnchors, topicScale } from "./projection";

const identity = (p: { x: number; y: number }) => ({ x: p.x, y: p.y });
const VP = { width: 1000, height: 600 };

describe("projectAnchors", () => {
  it("passes projected coordinates through in order", () => {
    const anchors = [
      { id: "a", label: "A", x: 10, y: 20 },
      { id: "b", label: "B", x: 30, y: 40 },
    ];
    const out = projectAnchors(anchors, VP, (p) => ({ x: p.x * 2, y: p.y * 2 }));
    expect(out).toEqual([
      { id: "a", x: 20, y: 40, visible: true },
      { id: "b", x: 60, y: 80, visible: true },
    ]);
  });

  it("visibility margins are strict inequalities (legacy semantics)", () => {
    const at = (x: number, y: number) => [{ id: "t", label: "T", x, y }];
    // x boundary: -80 invisible, just inside visible; width+80 invisible, just inside visible
    expect(projectAnchors(at(-80, 300), VP, identity)[0]!.visible).toBe(false);
    expect(projectAnchors(at(-79.99, 300), VP, identity)[0]!.visible).toBe(true);
    expect(projectAnchors(at(1080, 300), VP, identity)[0]!.visible).toBe(false);
    expect(projectAnchors(at(1079.99, 300), VP, identity)[0]!.visible).toBe(true);
    // y boundary: -24 / height+24
    expect(projectAnchors(at(500, -24), VP, identity)[0]!.visible).toBe(false);
    expect(projectAnchors(at(500, -23.99), VP, identity)[0]!.visible).toBe(true);
    expect(projectAnchors(at(500, 624), VP, identity)[0]!.visible).toBe(false);
    expect(projectAnchors(at(500, 623.99), VP, identity)[0]!.visible).toBe(true);
  });

  it("empty anchors yield empty output", () => {
    expect(projectAnchors([], VP, identity)).toEqual([]);
  });
});

describe("topicScale", () => {
  it("identity at ratio 1, inverse of zoom direction (smaller ratio = zoomed in)", () => {
    expect(topicScale(1)).toBe(1);
    expect(topicScale(0.5)).toBe(2);
    expect(topicScale(2)).toBeCloseTo(0.5);
  });
  it("clamps to [0.5, 4] at extreme ratios", () => {
    expect(topicScale(0.25)).toBe(4);
    expect(topicScale(0.02)).toBe(4);   // minCameraRatio floor
    expect(topicScale(60)).toBe(0.5);   // maxCameraRatio ceiling
    expect(topicScale(600)).toBe(0.5);
  });
  it("returns 1 when not following zoom (legacy screen-anchored behavior)", () => {
    expect(topicScale(0.02, { followZoom: false })).toBe(1);
    expect(topicScale(600, { followZoom: false })).toBe(1);
  });
  it("defensive: non-finite or non-positive ratios read as no scaling", () => {
    expect(topicScale(Number.NaN)).toBe(1);
    expect(topicScale(0)).toBe(1);
    expect(topicScale(-3)).toBe(1);
  });
  it("honors custom clamps", () => {
    expect(topicScale(0.1, { min: 0.2, max: 5 })).toBe(5);
    expect(topicScale(100, { min: 0.2, max: 5 })).toBeCloseTo(0.2);
  });
});
