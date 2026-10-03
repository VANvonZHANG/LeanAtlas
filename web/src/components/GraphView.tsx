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
 * need no closure state. (edgeReducer is wired in T6 (closure) and T7 (density).)
 */
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
  edgeReducer: (_edge, data) => data,
};

export default function GraphView({ graph, topics }: { graph: Graph; topics: TopicRow[] }) {
  return (
    <div id="graph-container">
      <SigmaContainer graph={graph} settings={SIGMA_SETTINGS}>
        <RefreshOnStoreChange />
        <TopicOverlay topics={topics} />
      </SigmaContainer>
    </div>
  );
}
