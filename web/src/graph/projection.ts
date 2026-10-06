/** World-space anchor for a topic band label (see TopicOverlay). */
export interface Anchor { id: string; label: string; x: number; y: number }
export interface ProjectedAnchor { id: string; x: number; y: number; visible: boolean }

/**
 * Project topic anchors to viewport coordinates through the injected
 * projector (sigma.graphToViewport in the component, identity in tests) and
 * apply the legacy visibility margins: strict inequalities, labels allowed
 * to overflow the canvas by 80px horizontally / 24px vertically.
 */
export function projectAnchors(
  anchors: Anchor[],
  viewport: { width: number; height: number },
  project: (p: { x: number; y: number }) => { x: number; y: number },
): ProjectedAnchor[] {
  return anchors.map((a) => {
    const p = project(a);
    const visible =
      p.x > -80 && p.x < viewport.width + 80 &&
      p.y > -24 && p.y < viewport.height + 24;
    return { id: a.id, x: p.x, y: p.y, visible };
  });
}

/** Screen-space scale factor for world-anchored topic labels. sigma's camera
 * ratio is < 1 zoomed in and > 1 zoomed out, so 1/ratio tracks how many
 * screen pixels one world unit occupies; clamped so overview labels stay
 * readable and deep-zoom labels stay on screen. Not following zoom, or a
 * degenerate ratio (non-finite / non-positive), reads as 1 — no scaling. */
export function topicScale(
  ratio: number,
  opts: { followZoom?: boolean; min?: number; max?: number } = {},
): number {
  const min = opts.min ?? 0.5;
  const max = opts.max ?? 4;
  if (opts.followZoom === false) return 1;
  if (!Number.isFinite(ratio) || ratio <= 0) return 1;
  return Math.min(max, Math.max(min, 1 / ratio));
}
