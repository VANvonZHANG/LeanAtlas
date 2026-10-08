import { useEffect } from "react";
import DeclBar from "./components/DeclBar";
import EdgePanel from "./components/EdgePanel";
import ExportButton from "./components/ExportButton";
import GraphView from "./components/GraphView";
import InfoPanel from "./components/InfoPanel";
import SearchBox from "./components/SearchBox";
import TopicPanel from "./components/TopicPanel";
import { probeApi } from "./graph/api";
import { backToOverview } from "./graph/declView";
import { useAtomValue } from "./hooks/useAtomValue";
import { useDeclGraph } from "./hooks/useDeclGraph";
import { useGraphData } from "./hooks/useGraphData";
import { viewStore } from "./state/stores";

export default function App() {
  const data = useGraphData();
  const view = useAtomValue(viewStore);
  const decl = useDeclGraph(view.mode === "decls" ? view.module : null);
  useEffect(() => { void probeApi(); }, []);
  if (!data) return <div className="placeholder">loading mathlib graph…</div>;
  // Two keyed GraphView mounts (never a graph-prop swap inside one live
  // SigmaContainer — remount is the verified-safe path, and the module-layer
  // GraphView internals stay untouched). Declaration view drops the
  // module-layer overlays (topics, search, topic panel); the edge density
  // panel and PNG export apply to whichever graph is shown.
  if (view.mode === "overview") {
    return (
      <>
        <GraphView key="overview" graph={data.graph} topics={data.doc.topics}>
          <SearchBox doc={data.doc} />
          <InfoPanel />
        </GraphView>
        <div className="left-column">
          <EdgePanel />
          <TopicPanel />
        </div>
        <ExportButton />
      </>
    );
  }
  if (decl.status === "loading" || decl.status === "idle")
    return <div className="placeholder">loading declarations…</div>;
  if (decl.status === "error")
    return (
      <div className="panel decl-error">
        <div>{decl.message}</div>
        <div className="hint">the declaration pack is a release asset — build it with
          `leanatlas declpack` or download `declpack.bin` from the releases (see
          web/DECLPACK.md) — or run `leanatlas serve` to serve blocks live</div>
        <button className="back" onClick={backToOverview}>← overview</button>
      </div>
    );
  return (
    <>
      <GraphView key={`decls-${view.module}`} graph={decl.graph} topics={[]}>
        <InfoPanel />
      </GraphView>
      <DeclBar module={view.module} decls={decl.block.decls.length} edges={decl.block.e.length} />
      <div className="left-column">
        <EdgePanel />
      </div>
      <ExportButton />
    </>
  );
}
