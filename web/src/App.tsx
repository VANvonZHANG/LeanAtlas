import EdgePanel from "./components/EdgePanel";
import ExportButton from "./components/ExportButton";
import GraphView from "./components/GraphView";
import InfoPanel from "./components/InfoPanel";
import SearchBox from "./components/SearchBox";
import TopicPanel from "./components/TopicPanel";
import { useGraphData } from "./hooks/useGraphData";

export default function App() {
  const data = useGraphData();
  if (!data) return <div className="placeholder">loading mathlib graph…</div>;
  return (
    <>
      <GraphView graph={data.graph} topics={data.doc.topics}>
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
