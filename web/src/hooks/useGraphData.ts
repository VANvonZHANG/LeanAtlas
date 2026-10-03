import { useEffect, useState } from "react";
import Graph from "graphology";
import { buildGraph, loadData, type DataDoc } from "../graph/loadData";

export function useGraphData(): { doc: DataDoc; graph: Graph } | null {
  const [state, setState] = useState<{ doc: DataDoc; graph: Graph } | null>(null);
  useEffect(() => {
    let cancelled = false;
    loadData().then((doc) => {
      if (!cancelled) setState({ doc, graph: buildGraph(doc) });
    });
    return () => { cancelled = true; };
  }, []);
  return state;
}
