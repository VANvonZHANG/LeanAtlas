import EdgeSlider from "./components/EdgeSlider";
import ExportButton from "./components/ExportButton";
import GraphView from "./components/GraphView";
import InfoPanel from "./components/InfoPanel";
import SearchBox from "./components/SearchBox";
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
      <EdgeSlider />
      <ExportButton />
    </>
  );
}
