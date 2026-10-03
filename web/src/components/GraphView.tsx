// @react-sigma/core ships its container CSS as a separate export (the ESM bundle
// does not inject it); without it .react-sigma has zero height.
import "@react-sigma/core/lib/style.css";
import { SigmaContainer, useSigma } from "@react-sigma/core";
// sigma v3 registers edge renderers as WebGL programs, not canvas draw functions:
// @sigma/edge-curve 3.x exports EdgeCurveProgram (default) instead of drawCurvedEdge.
import EdgeCurveProgram from "@sigma/edge-curve";
import { useEffect, type ReactNode } from "react";
import type Graph from "graphology";
import type { Settings } from "sigma/settings";
import { computeNodeColor } from "../graph/computeNodeColor";
import { edgeKey } from "../graph/edgeSalience";
import { hoverStore, selectionStore, topicFilterStore } from "../state/stores";
import {
  effectiveEdgesStore,
  initEdgeRanking,
  lodEdgesHiddenForRatio,
  lodEdgesHiddenStore,
} from "../state/visibleEdges";
import { useUrlSync } from "../hooks/useUrlSync";
import EventsBinder from "./EventsBinder";
import TopicOverlay from "./TopicOverlay";
import type { TopicRow } from "../graph/loadData";

/**
 * SigmaContainer child: store changes -> sigma.refresh() (reducers read store
 * snapshots), plus the camera LOD listener that gates the edge-density channel.
 */
function RefreshOnStoreChange() {
  const sigma = useSigma();
  useEffect(() => {
    const refresh = () => sigma.refresh();
    const unsubs = [selectionStore, topicFilterStore, hoverStore, effectiveEdgesStore].map((s) =>
      s.subscribe(refresh),
    );
    // Camera LOD: zoomed-out overview: density edges become overdraw noise;
    // zoomed-in keeps them. sigma's camera ratio shrinks below 1 when zooming
    // IN and grows above 1 when zooming OUT, so the gate hides the density
    // channel once ratio exceeds LOD_EDGES_MAX_RATIO (> only, boundary stays
    // visible); the effectiveEdgesStore subscription above performs the
    // refresh on flag flips. lodEdgesHiddenForRatio lives in visibleEdges.ts
    // so tests can pin the mapping (this module pulls WebGL at import time).
    const cam = sigma.getCamera();
    const onCam = () => lodEdgesHiddenStore.set(lodEdgesHiddenForRatio(cam.getState().ratio));
    cam.on("updated", onCam);
    return () => {
      unsubs.forEach((u) => u());
      // remove own handler by reference (not removeAllListeners), matching
      // EventsBinder: sibling/StrictMode-registered handlers must survive.
      cam.removeListener("updated", onCam);
    };
  }, [sigma]);
  // URL deep-link sync (restore on mount + debounced hash push-back). Declared
  // AFTER the effect above: camera.setState emits "updated" synchronously, so
  // the restore call inside must find the LOD listener already attached —
  // otherwise a restored zoomed-out camera (z > LOD_EDGES_MAX_RATIO) would not
  // gate the density channel.
  useUrlSync(sigma, true);
  return null;
}

/**
 * Module-level reducers + settings: react-sigma deep-compares the `settings` prop but
 * its isEqual matches functions by reference, so inline closures would recreate the
 * Sigma instance on every render. Reducers read store snapshots via .get(), so they
 * need no closure state.
 */

// sigma 3.0.3 invokes edgeReducer as (edge, data) only — the (edge, data, source,
// target) signature is sigma v2 behavior (verified in sigma/dist addEdge). Edge
// endpoints are recovered instead from the graph assigned by the active GraphView
// render; graphology extremities() is an O(1) key lookup.
let activeGraph: Graph | null = null;

const HIGHLIGHT_EDGE = { color: "#5b7bd5", size: 1 };
// Matches the default edge attributes set by buildGraph: the density channel
// shows global structure in the same subdued style, just gated by salience.
const DENSITY_EDGE = { color: "#26304a", size: 0.5 };

const edgeReducer: Settings["edgeReducer"] = (edge, data) => {
  const sel = selectionStore.get();
  const hov = hoverStore.get();
  if (!activeGraph) return data;
  const [source, target] = activeGraph.extremities(edge);
  if (sel) {
    // pinned: draw only closure-internal edges (both ends in {node} ∪ closure), bright
    const internal =
      (sel.closure.has(source) || source === sel.node) &&
      (sel.closure.has(target) || target === sel.node);
    return internal ? { ...data, ...HIGHLIGHT_EDGE } : { ...data, hidden: true };
  }
  if (hov && (source === hov || target === hov)) {
    return { ...data, ...HIGHLIGHT_EDGE };
  }
  // density channel: salient top-k edges dark, everything else hidden
  const vis = effectiveEdgesStore.get();
  if (vis.enabled && vis.keys.has(edgeKey(source, target))) {
    return { ...data, ...DENSITY_EDGE };
  }
  return { ...data, hidden: true };
};

const nodeReducer: Settings["nodeReducer"] = (node, data) => ({
  ...data,
  // TS strict: reducer data has sigma's index-signature type (Attributes), not the
  // concrete { color, topic } shape; our graph nodes always carry both attributes.
  color: computeNodeColor(node, data as { color: string; topic: string }, {
    selection: selectionStore.get(),
    topicFilter: topicFilterStore.get(),
    hover: hoverStore.get(),
  }),
});

const SIGMA_SETTINGS: Partial<Settings> = {
  defaultEdgeType: "curve",
  edgeProgramClasses: { curve: EdgeCurveProgram },
  labelRenderedSizeThreshold: 8,
  labelDensity: 0.3,
  labelGridCellSize: 60,
  labelColor: { color: "#cfd8ff" },
  minCameraRatio: 0.02,
  maxCameraRatio: 60,
  nodeReducer,
  edgeReducer,
};

/**
 * `children` render inside SigmaContainer so overlay components that need the
 * sigma instance (e.g. SearchBox via useSigma) can be passed from App.
 */
export default function GraphView({ graph, topics, children }: { graph: Graph; topics: TopicRow[]; children?: ReactNode }) {
  // reducers are module-scope (see above), so the current graph instance is shared
  // via a module-scope reference, assigned during render — before any effect (and
  // thus before sigma processes the graph) can run. The graph prop never changes
  // identity in this app (loaded once in App via useGraphData).
  activeGraph = graph;
  // Rank edges once per graph load. This effect runs after sigma's initial
  // processing, which is fine: the density channel starts disabled
  // (edgeDensityStore defaults to 0), so no ranking is needed before the
  // first slider interaction.
  useEffect(() => {
    initEdgeRanking(graph);
  }, [graph]);
  return (
    <div id="graph-container">
      <SigmaContainer graph={graph} settings={SIGMA_SETTINGS}>
        <RefreshOnStoreChange />
        <EventsBinder />
        <TopicOverlay topics={topics} />
        {children}
      </SigmaContainer>
    </div>
  );
}
