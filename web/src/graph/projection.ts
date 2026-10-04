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
