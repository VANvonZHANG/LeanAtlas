import { EDGE_STYLE_DEFAULTS, cloneEdgeStyleDefaults, type RelKind } from "../graph/edgeStyle";
import { edgeDensityStore, edgeStyleStore, structureTogglesStore } from "../state/stores";
import { useAtomValue } from "../hooks/useAtomValue";

const STRUCTURE_ROWS: { key: keyof typeof EDGE_STYLE_DEFAULTS & ("extends" | "instantiates" | "fields"); label: string }[] = [
  { key: "extends", label: "extends" },
  { key: "instantiates", label: "instantiates" },
  { key: "fields", label: "fields" },
];

/** Edge controls: import density slider (as before) plus a collapsible
 * per-relation style section (color + curvature, page-adjustable; structure
 * rows also carry their visibility toggle, default all on). Style is
 * session-local — reset restores the in-code defaults. */
export default function EdgePanel() {
  const density = useAtomValue(edgeDensityStore);
  const style = useAtomValue(edgeStyleStore);
  const toggles = useAtomValue(structureTogglesStore);

  const setStyle = (rel: RelKind, patch: Partial<{ color: string; curvature: number }>) =>
    edgeStyleStore.set({ ...edgeStyleStore.get(), [rel]: { ...edgeStyleStore.get()[rel], ...patch } });

  return (
    <div className="panel edge-panel">
      <label className="density-row">
        edges {Math.round(density * 100)}%
        <input
          type="range" min={0} max={100} value={Math.round(density * 100)}
          onChange={(e) => edgeDensityStore.set(Number(e.target.value) / 100)}
        />
      </label>
      <details className="style-rows">
        <summary>style</summary>
        {STRUCTURE_ROWS.map(({ key, label }) => (
          <div key={key} className="style-row">
            <input
              type="checkbox" aria-label={label} checked={toggles[key]}
              onChange={(e) => structureTogglesStore.set({ ...structureTogglesStore.get(), [key]: e.target.checked })}
            />
            <span className="style-label">{label}</span>
            <input
              type="color" value={style[key].color}
              onChange={(e) => setStyle(key, { color: e.target.value })}
            />
            <input
              type="range" min={0} max={1} step={0.05} value={style[key].curvature}
              onChange={(e) => setStyle(key, { curvature: Number(e.target.value) })}
            />
          </div>
        ))}
        <div className="style-row">
          <span className="style-label">imports</span>
          <input type="color" value={style.import.color}
            onChange={(e) => setStyle("import", { color: e.target.value })} />
          <input type="range" min={0} max={1} step={0.05} value={style.import.curvature}
            onChange={(e) => setStyle("import", { curvature: Number(e.target.value) })} />
        </div>
        <button className="reset" onClick={() => edgeStyleStore.set(cloneEdgeStyleDefaults())}>
          reset
        </button>
      </details>
    </div>
  );
}
