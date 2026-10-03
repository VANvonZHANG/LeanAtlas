import { useEffect } from "react";
import { useSigma } from "@react-sigma/core";
import type { SigmaNodeEventPayload, SigmaStageEventPayload } from "sigma/types";
import { closureOf, neighborsOf } from "../graph/bfs";
import { hoverStore, selectionStore } from "../state/stores";

/**
 * SigmaContainer child: binds sigma mouse events to the hover/selection stores.
 * Cleanup removes this component's own handlers per (type, ref) pair instead of
 * removeAllListeners(type), which would also drop handlers registered by sibling
 * components (e.g. react-sigma hooks) and misbehave under React 19 StrictMode
 * double-mount, where add/remove pairs must balance exactly.
 */
export default function EventsBinder() {
  const sigma = useSigma();
  useEffect(() => {
    const g = sigma.getGraph();
    const onEnterNode = ({ node }: SigmaNodeEventPayload) => hoverStore.set(node);
    const onLeaveNode = () => hoverStore.set(null);
    const onClickNode = ({ node }: SigmaNodeEventPayload) => {
      const cur = selectionStore.get();
      if (cur && cur.node === node) {
        selectionStore.set(null);
        return;
      }
      const n = neighborsOf(g, node);
      const cl = closureOf(g, node);
      selectionStore.set({
        node,
        neighbors: [...n.deps, ...n.dependents],
        closure: new Set([...cl.deps, ...cl.dependents]),
      });
    };
    const onClickStage = (_payload: SigmaStageEventPayload) => selectionStore.set(null);
    sigma.on("enterNode", onEnterNode);
    sigma.on("leaveNode", onLeaveNode);
    sigma.on("clickNode", onClickNode);
    sigma.on("clickStage", onClickStage);
    return () => {
      sigma.removeListener("enterNode", onEnterNode);
      sigma.removeListener("leaveNode", onLeaveNode);
      sigma.removeListener("clickNode", onClickNode);
      sigma.removeListener("clickStage", onClickStage);
    };
  }, [sigma]);
  return null;
}
