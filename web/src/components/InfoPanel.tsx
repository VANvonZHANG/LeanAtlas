import { useSyncExternalStore } from "react";
import { useSigma } from "@react-sigma/core";
import { selectionStore } from "../state/stores";

// EdgeSlider pattern (the brief's `@nanostores/react` is not a dependency):
// the atom integrates with React via the built-in hook. atom.get() returns
// the stored Selection by reference, stable between .set() calls, so the
// snapshot (which contains a Set) satisfies getSnapshot's identity requirement.
function useSelection() {
  return useSyncExternalStore(
    (onChange) => selectionStore.subscribe(onChange),
    () => selectionStore.get(),
  );
}

/** Must render inside SigmaContainer (uses useSigma) — mounted via GraphView children. */
export default function InfoPanel() {
  const sigma = useSigma();
  const sel = useSelection();
  if (!sel) return null;
  // buildGraph sets these attributes on every node (loadData.ts); the
  // graphology Attributes type is a plain index signature, hence the casts.
  const a = sigma.getGraph().getNodeAttributes(sel.node);
  return (
    <div className="panel info-panel">
      <div className="name">{sel.node}</div>
      <div className="title">{a.title as string}</div>
      <div className="meta">
        {a.declCount as number} decls · closure {a.closureSize as number} · {a.topic as string} · r{" "}
        {(a.r as number).toFixed(1)}
      </div>
    </div>
  );
}
