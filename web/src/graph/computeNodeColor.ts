export interface Selection { node: string; neighbors: string[]; closure: Set<string> }
export interface Hover { node: string; neighbors: string[] }
export interface ColorState { selection: Selection | null; topicFilter: string | null; hover: Hover | null }

const DARK = "#151a26";

function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

export function computeNodeColor(
  name: string,
  attrs: { color: string; topic: string },
  st: ColorState,
): string {
  if (st.selection) {
    if (name === st.selection.node || st.selection.neighbors.includes(name)) return attrs.color;
    if (st.selection.closure.has(name)) return hexToRgba(attrs.color, 0.45);
    if (st.topicFilter) return attrs.topic === st.topicFilter ? attrs.color : hexToRgba(attrs.color, 0.15);
    return DARK;
  }
  if (st.topicFilter) {
    if (attrs.topic === st.topicFilter) return attrs.color;
    // hover restores the node itself + its direct neighbors (spec §5)
    if (st.hover && (st.hover.node === name || st.hover.neighbors.includes(name))) return attrs.color;
    return hexToRgba(attrs.color, 0.15);
  }
  return attrs.color;
}
