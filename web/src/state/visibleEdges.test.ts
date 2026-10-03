import Graph from "graphology";
import { beforeEach, describe, expect, it } from "vitest";
import { edgeDensityStore } from "./stores";
import {
  effectiveEdgesStore,
  initEdgeRanking,
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

  it("LOD gate overrides the density channel entirely", () => {
    edgeDensityStore.set(1);
    lodEdgesHiddenStore.set(true);
    expect(effectiveEdgesStore.get()).toEqual({ keys: new Set(), enabled: false });
    lodEdgesHiddenStore.set(false);
    expect(effectiveEdgesStore.get().enabled).toBe(true);
    expect(effectiveEdgesStore.get().keys).toEqual(new Set(["X→Y", "X→Z", "Y→Z"]));
  });
});
