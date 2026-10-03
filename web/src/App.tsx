import GraphView from "./components/GraphView";
import { useGraphData } from "./hooks/useGraphData";

export default function App() {
  const data = useGraphData();
  if (!data) return <div className="placeholder">loading mathlib graph…</div>;
  return <GraphView graph={data.graph} topics={data.doc.topics} />;
}
