// @react-sigma/core ships its container CSS as a separate export (the ESM bundle
// does not inject it); without it .react-sigma has zero height.
import "@react-sigma/core/lib/style.css";
import { SigmaContainer, useSigma } from "@react-sigma/core";
// sigma v3 registers edge renderers as WebGL programs, not canvas draw functions:
// @sigma/edge-curve 3.x exports EdgeCurveProgram (default) instead of drawCurvedEdge.
import EdgeCurveProgram from "@sigma/edge-curve";
import { useEffect } from "react";
import type Graph from "graphology";
import type { Settings } from "sigma/settings";
import { computeNodeColor } from "../graph/computeNodeColor";
import { hoverStore, selectionStore, topicFilterStore } from "../state/stores";
import EventsBinder from "./EventsBinder";
import TopicOverlay from "./TopicOverlay";
import type { TopicRow } from "../graph/loadData";

/** SigmaContainer child: store changes -> sigma.refresh() (reducers read store snapshots). */
function RefreshOnStoreChange() {
  const sigma = useSigma();
  useEffect(() => {
    const refresh = () => sigma.refresh();
    const unsubs = [selectionStore, topicFilterStore, hoverStore].map((s) => s.subscribe(refresh));
    return () => unsubs.forEach((u) => u());
  }, [sigma]);
  return null;
}

/**
 * Module-level reducers + settings: react-sigma deep-compares the `settings` prop but
 * its isEqual matches functions by reference, so inline closures would recreate the
 * Sigma instance on every render. Reducers read store snapshots via .get(), so they
 * need no closure state. (edgeReducer density channel is wired in T7.)
 */

// sigma 3.0.3 invokes edgeReducer as (edge, data) only — the (edge, data, source,
// target) signature is sigma v2 behavior (verified in sigma/dist addEdge). Edge
// endpoints are recovered instead from the graph assigned by the active GraphView
// render; graphology extremities() is an O(1) key lookup.
let activeGraph: Graph | null = null;

const HIGHLIGHT_EDGE = { color: "#5b7bd5", size: 1 };

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
  return data; // density channel wired in T7
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

export default function GraphView({ graph, topics }: { graph: Graph; topics: TopicRow[] }) {
  // reducers are module-scope (see above), so the current graph instance is shared
  // via a module-scope reference, assigned during render — before any effect (and
  // thus before sigma processes the graph) can run. The graph prop never changes
  // identity in this app (loaded once in App via useGraphData).
  activeGraph = graph;
  return (
    <div id="graph-container">
      <SigmaContainer graph={graph} settings={SIGMA_SETTINGS}>
        <RefreshOnStoreChange />
        <EventsBinder />
        <TopicOverlay topics={topics} />
      </SigmaContainer>
    </div>
  );
}
