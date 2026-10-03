import { useSyncExternalStore } from "react";
import { edgeDensityStore } from "../state/stores";

// @nanostores/react is not a dependency of this project; a nanostores atom is
// an external store that integrates with React via the built-in hook. The
// number snapshot is a primitive, so identity-stability is guaranteed.
function useEdgeDensity(): number {
  return useSyncExternalStore(
    (onChange) => edgeDensityStore.subscribe(onChange),
    () => edgeDensityStore.get(),
  );
}

export default function EdgeSlider() {
  const density = useEdgeDensity();
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
