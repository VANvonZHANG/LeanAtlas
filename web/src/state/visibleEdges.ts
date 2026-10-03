import { atom, computed } from "nanostores";
import type Graph from "graphology";
import { rankEdges, topKKeys } from "../graph/edgeSalience";
import { edgeDensityStore } from "./stores";

export interface VisibleEdges {
  keys: Set<string>;
  enabled: boolean;
}

// Module-level salience ranking, computed once at load (initEdgeRanking).
// Slider changes only re-derive the top-k key set from this cache — they never
// re-rank the graph (rankEdges is O(E log E) over the whole graph).
let ranked: ReturnType<typeof rankEdges> = [];

export function initEdgeRanking(g: Graph): void {
  ranked = rankEdges(g);
}

// density (0..1) -> top round(density * E) edges by salience; disabled at 0,
// meaning "no density edges" (hover/pin highlights are unaffected).
export const visibleEdgesStore = computed(edgeDensityStore, (density): VisibleEdges => ({
  keys: topKKeys(ranked, Math.round(density * ranked.length)),
  enabled: density > 0,
}));

// Camera LOD gate: GraphView's camera listener flips this flag when the camera
// zooms in deep (ratio < 0.15 — sigma's ratio shrinks below 1 when zooming in,
// grows above 1 when zooming out), hiding the global density channel so close-up
// inspection relies on the hover/pin highlights. atom.set dedupes via Object.is,
// so continuous camera updates only notify on flips.
export const lodEdgesHiddenStore = atom(false);

// What the edgeReducer reads: the LOD gate overrides the density channel
// entirely. Kept permanently subscribed by RefreshOnStoreChange, so the lazy
// computed stays live/cached and reducer .get() calls are cheap snapshot reads.
// NB: nanostores 1.5.4 computed() takes (stores, fn) — deps must be an array
// (the multi-arg computed(a, b, fn) form does not exist and silently passes the
// second store as the callback).
export const effectiveEdgesStore = computed(
  [visibleEdgesStore, lodEdgesHiddenStore],
  (visible, hidden): VisibleEdges =>
    hidden ? { keys: new Set<string>(), enabled: false } : visible,
);
