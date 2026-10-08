import { useEffect, useState } from "react";
import Graph from "graphology";
import { buildGraph, loadData, type DataDoc } from "../graph/loadData";
import { loadOverviewFromApi } from "../graph/api";

export function useGraphData(): { doc: DataDoc; graph: Graph } | null {
  const [state, setState] = useState<{ doc: DataDoc; graph: Graph } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      // DB-first when the API can serve the overview document (spec level 1);
      // anything else falls back to the static data.json (levels 2–3)
      const doc = (await loadOverviewFromApi()) ?? (await loadData());
      if (!cancelled) setState({ doc, graph: buildGraph(doc) });
    })();
    return () => { cancelled = true; };
  }, []);
  return state;
}
