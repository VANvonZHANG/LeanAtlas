import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useSigma } from "@react-sigma/core";
import { buildSearchIndex, searchDocs } from "../graph/search";
import { flyTo, pinNode } from "../graph/pin";
import { selectionStore } from "../state/stores";
import type { DataDoc } from "../graph/loadData";

// @nanostores/react is not a dependency of this project (see EdgeSlider); an
// atom integrates with React via the built-in hook. atom.get() returns the
// stored Selection by reference, stable between .set() calls, so the snapshot
// (which contains a Set) satisfies getSnapshot's identity requirement.
function useSelection() {
  return useSyncExternalStore(
    (onChange) => selectionStore.subscribe(onChange),
    () => selectionStore.get(),
  );
}

/** Must render inside SigmaContainer (uses useSigma) — mounted via GraphView children. */
export default function SearchBox({ doc }: { doc: DataDoc }) {
  const sigma = useSigma();
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const index = useMemo(() => buildSearchIndex(doc.nodes), [doc]);
  const results = useMemo(() => searchDocs(index, q), [index, q]);
  const sel = useSelection();

  useEffect(() => { setCursor(0); }, [q]);

  const pick = (name: string) => {
    const g = sigma.getGraph();
    flyTo(sigma, name);
    pinNode(g, name);
    setOpen(false);
    setQ("");
    inputRef.current?.blur();
  };

  return (
    <div className="panel search-box">
      <input
        ref={inputRef}
        value={q}
        placeholder="search modules…"
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setCursor((c) => Math.min(c + 1, results.length - 1));
          else if (e.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
          else if (e.key === "Enter" && results[cursor]) pick(results[cursor]!.name);
          else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && results.length > 0 && (
        <ul>
          {results.map((r, i) => (
            <li key={r.name} className={i === cursor ? "active" : ""}
                onMouseEnter={() => setCursor(i)} onMouseDown={(e) => { e.preventDefault(); pick(r.name); }}>
              {r.name}
            </li>
          ))}
        </ul>
      )}
      {sel && <div className="pinned">pinned: {sel.node}</div>}
    </div>
  );
}
