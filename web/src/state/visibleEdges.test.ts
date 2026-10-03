import Graph from "graphology";
import { beforeEach, describe, expect, it } from "vitest";
import { edgeDensityStore } from "./stores";
import {
  effectiveEdgesStore,
  initEdgeRanking,
  LOD_EDGES_MAX_RATIO,
  lodEdgesHiddenForRatio,
  lodEdgesHiddenStore,
  visibleEdgesStore,
} from "./visibleEdges";

describe("visibleEdges stores", () => {
  beforeEach(() => {
    // 3 edges; salience ranking (edgeSalience.test.ts): X→Y, X→Z, Y→Z
    const g = new Graph({ type: "directed", multi: false });
    for (const [n, r] of [["X", 3], ["Y", 2], ["Z", 2]] as const) g.addNode(n, { r });
    g.addEdge("X", "Y");
    g.addEdge("X", "Z");
    g.addEdge("Y", "Z");
    initEdgeRanking(g);
    edgeDensityStore.set(0);
    lodEdgesHiddenStore.set(false);
  });

  it("density maps to top round(density*E) salient keys, disabled at 0", () => {
    expect(visibleEdgesStore.get()).toEqual({ keys: new Set(), enabled: false });
    edgeDensityStore.set(0.5); // round(0.5 * 3) = 2
    expect(visibleEdgesStore.get()).toEqual({
      keys: new Set(["X→Y", "X→Z"]),
      enabled: true,
    });
    edgeDensityStore.set(1);
    expect(visibleEdgesStore.get().keys).toEqual(new Set(["X→Y", "X→Z", "Y→Z"]));
  });

  it("LOD gate hides density edges when zoomed OUT (ratio > LOD_EDGES_MAX_RATIO)", () => {
    edgeDensityStore.set(1);
    // zoomed-out overview (sigma ratio > 2): density edges become overdraw
    // noise -> gate hides the whole density channel, override and all
    lodEdgesHiddenStore.set(lodEdgesHiddenForRatio(2.5));
    expect(lodEdgesHiddenForRatio(2.5)).toBe(true);
    expect(effectiveEdgesStore.get()).toEqual({ keys: new Set(), enabled: false });
    // boundary: exactly LOD_EDGES_MAX_RATIO stays visible — hidden is strictly
    // greater only (> not >=)
    expect(lodEdgesHiddenForRatio(LOD_EDGES_MAX_RATIO)).toBe(false);
    // zoomed in (ratio < 2, e.g. the default 1): density channel intact
    expect(lodEdgesHiddenForRatio(1)).toBe(false);
    lodEdgesHiddenStore.set(lodEdgesHiddenForRatio(1));
    expect(effectiveEdgesStore.get().enabled).toBe(true);
    expect(effectiveEdgesStore.get().keys).toEqual(new Set(["X→Y", "X→Z", "Y→Z"]));
  });
});
