import { useEffect, useMemo, useRef, useState } from "react";
import { useSigma } from "@react-sigma/core";
import { buildSearchIndex, searchDocs } from "../graph/search";
import { searchDecls, type DeclHit } from "../graph/api";
import { mergeHits, type MixedHit } from "../graph/mixedSearch";
import { flyTo, pinNode } from "../graph/pin";
import { drillTo, kindColor } from "../graph/declView";
import { apiStore, pendingPinStore, selectionStore } from "../state/stores";
import { useAtomValue } from "../hooks/useAtomValue";
import type { DataDoc } from "../graph/loadData";

/** Must render inside SigmaContainer (uses useSigma) — mounted via GraphView
 * children. Mixed search: local module hits (existing scoring over data.json)
 * plus debounced API declaration hits; modules and declarations render as two
 * sections without cross-ranking. */
export default function SearchBox({ doc }: { doc: DataDoc }) {
  const sigma = useSigma();
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const [open, setOpen] = useState(false);
  const [declHits, setDeclHits] = useState<DeclHit[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const api = useAtomValue(apiStore);
  const index = useMemo(() => buildSearchIndex(doc.nodes), [doc]);
  const moduleHits = useMemo(() => searchDocs(index, q), [index, q]);
  const hits = useMemo(() => mergeHits(moduleHits, declHits), [moduleHits, declHits]);
  const sel = useAtomValue(selectionStore);

  useEffect(() => { setCursor(0); }, [q]);

  // declaration search over the live API (150 ms debounce); down API = no
  // declaration section at all, module search keeps working offline
  // (a seq counter drops responses from superseded queries)
  const declSeq = useRef(0);
  useEffect(() => {
    const mine = ++declSeq.current;
    const query = q.trim();
    if (api.status !== "up" || !query) {
      setDeclHits([]);
      return;
    }
    const t = setTimeout(() => {
      void searchDecls(query).then((hits) => {
        if (mine === declSeq.current) setDeclHits(hits);
      });
    }, 150);
    return () => clearTimeout(t);
  }, [q, api.status]);

  const pick = (hit: MixedHit) => {
    const g = sigma.getGraph();
    if (hit.type === "module") {
      flyTo(sigma, hit.name);
      pinNode(g, hit.name);
    } else {
      // fly near the defining module, then pin the declaration once the
      // declaration view mounts (App consumes pendingPinStore)
      if (g.hasNode(hit.module)) flyTo(sigma, hit.module);
      pendingPinStore.set(hit.name);
      drillTo(hit.module);
    }
    setOpen(false);
    setQ("");
    inputRef.current?.blur();
  };

  return (
    <div className="panel search-box">
      <input
        ref={inputRef}
        value={q}
        placeholder={api.status === "up" ? "search modules & declarations…" : "search modules…"}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown")
            setCursor((c) => (hits.length ? Math.min(c + 1, hits.length - 1) : 0));
          else if (e.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
          else if (e.key === "Enter" && hits[cursor]) pick(hits[cursor]!);
          else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && hits.length > 0 && (
        <ul>
          {hits.map((h, i) => (
            <li key={`${h.type}:${h.name}`} className={i === cursor ? "active" : ""}
                onMouseEnter={() => setCursor(i)}
                onMouseDown={(e) => { e.preventDefault(); pick(h); }}>
              {h.type === "module" ? (
                h.name
              ) : (
                <>
                  <span className="kind-dot" style={{ background: kindColor(h.kind) }} />
                  {h.name} <span className="hit-meta">{h.kind} · {h.module}</span>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {sel && <div className="pinned">pinned: {sel.node}</div>}
    </div>
  );
}
