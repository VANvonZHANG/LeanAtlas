/** Per-relation visual encoding defaults; user-adjustable at runtime via the
 * edge panel (style changes never enter the URL — deep links stay semantic). */
export type RelKind = "import" | "extends" | "instantiates" | "fields";
export interface EdgeStyle { color: string; curvature: number }

export const EDGE_STYLE_DEFAULTS: Record<RelKind, EdgeStyle> = {
  import: { color: "#26304a", curvature: 0.08 },
  extends: { color: "#e0a458", curvature: 0.25 },
  instantiates: { color: "#4ec9b0", curvature: 0.45 },
  fields: { color: "#b48ead", curvature: 0.65 },
};
