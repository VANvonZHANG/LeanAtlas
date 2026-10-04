import { edgeDensityStore } from "../state/stores";
import { useAtomValue } from "../hooks/useAtomValue";

export default function EdgeSlider() {
  const density = useAtomValue(edgeDensityStore);
  return (
    <label className="panel edge-slider">
      edges {Math.round(density * 100)}%
      <input
        type="range"
        min={0}
        max={100}
        value={Math.round(density * 100)}
        onChange={(e) => edgeDensityStore.set(Number(e.target.value) / 100)}
      />
    </label>
  );
}
