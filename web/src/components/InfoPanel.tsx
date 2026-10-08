import { useEffect, useState } from "react";
import { useSigma } from "@react-sigma/core";
import { apiStore, selectionStore, viewStore } from "../state/stores";
import { drillTo } from "../graph/declView";
import { fetchDeclDetail, type DeclDetail } from "../graph/api";
import { useAtomValue } from "../hooks/useAtomValue";
import DepsPanel from "./DepsPanel";

/** Must render inside SigmaContainer (uses useSigma) — mounted via GraphView
 * children. In the declaration view (API up) it lazy-loads the selected
 * declaration's details (spec B) and offers cross-module deps (spec C-1). */
export default function InfoPanel() {
  const sigma = useSigma();
  const sel = useAtomValue(selectionStore);
  const view = useAtomValue(viewStore);
  const api = useAtomValue(apiStore);
  const [detail, setDetail] = useState<DeclDetail | null>(null);
  const [depsFor, setDepsFor] = useState<string | null>(null);

  // cross-view guard + API-gated lazy detail fetch: one request per selection;
  // a failed fetch leaves the panel on its static graph attrs
  useEffect(() => {
    setDetail(null);
    setDepsFor(null);
    if (view.mode !== "decls" || !sel || api.status !== "up") return;
    if (!sigma.getGraph().hasNode(sel.node)) return;
    let cancelled = false;
    fetchDeclDetail(sel.node)
      .then((d) => { if (!cancelled) setDetail(d); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [sel, view.mode, api.status, sigma]);

  if (!sel) return null;
  // a selection may name a node of the OTHER view's graph (hand-crafted
  // #node=&mod= URL, or any future cross-view leak): graphology throws on
  // unknown nodes, which during render would unmount the whole tree.
  if (!sigma.getGraph().hasNode(sel.node)) return null;
  const a = sigma.getGraph().getNodeAttributes(sel.node);
  return (
    <div className="panel info-panel">
      <div className="name">{sel.node}</div>
      <div className="title">{a.title as string}</div>
      <div className="meta">
        {a.declCount as number} decls · closure {a.closureSize as number} · {a.topic as string} · r{" "}
        {(a.r as number).toFixed(1)}
      </div>
      {view.mode === "overview" && (
        <button className="drill" onClick={() => drillTo(sel.node)}>
          explore declarations ⟶
        </button>
      )}
      {view.mode === "decls" && detail && (
        <div className="decl-detail">
          {detail.sourceUrl && (
            <a className="source" href={detail.sourceUrl} target="_blank" rel="noreferrer">
              source ↗
            </a>
          )}
          {detail.docstring && <div className="doc">{detail.docstring.split("\n")[0]}</div>}
          {detail.typeSignature && (
            <details>
              <summary>type signature</summary>
              <pre>{detail.typeSignature}</pre>
            </details>
          )}
          {detail.sourceText && (
            <details>
              <summary>source text</summary>
              <pre>{detail.sourceText}</pre>
            </details>
          )}
        </div>
      )}
      {view.mode === "decls" && api.status === "up" && (
        <button className="deps-toggle"
                onClick={() => setDepsFor(depsFor === sel.node ? null : sel.node)}>
          cross-module dependencies…
        </button>
      )}
      {depsFor && <DepsPanel node={depsFor} onClose={() => setDepsFor(null)} />}
    </div>
  );
}
