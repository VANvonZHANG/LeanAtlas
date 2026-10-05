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

/** Fresh per-relation style map; nested EdgeStyle objects are copied, never
 * aliased — resets/inits must not share mutable state with the defaults. */
export function cloneEdgeStyleDefaults(): Record<RelKind, EdgeStyle> {
  // explicit per-key spread: Object.fromEntries returns an index-signature
  // type that does not satisfy Record<RelKind, EdgeStyle> under tsc
  return {
    import: { ...EDGE_STYLE_DEFAULTS.import },
    extends: { ...EDGE_STYLE_DEFAULTS.extends },
    instantiates: { ...EDGE_STYLE_DEFAULTS.instantiates },
    fields: { ...EDGE_STYLE_DEFAULTS.fields },
  };
}
