import { useSigma } from "@react-sigma/core";
import { selectionStore } from "../state/stores";
import { useAtomValue } from "../hooks/useAtomValue";

/** Must render inside SigmaContainer (uses useSigma) — mounted via GraphView children. */
export default function InfoPanel() {
  const sigma = useSigma();
  const sel = useAtomValue(selectionStore);
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
