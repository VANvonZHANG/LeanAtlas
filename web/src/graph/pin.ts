import type Graph from "graphology";
import type Sigma from "sigma";
import { closureOf, neighborsOf } from "./bfs";
import { selectionStore } from "../state/stores";

/**
 * Pin a node: derive direct neighbors and transitive closure, then publish a
 * Selection. Extracted from EventsBinder's clickNode so SearchBox reuses the
 * exact same closure semantics for its Enter-to-pin action.
 */
export function pinNode(g: Graph, node: string) {
  const n = neighborsOf(g, node);
  const cl = closureOf(g, node);
  selectionStore.set({
    node,
    neighbors: [...n.deps, ...n.dependents],
    closure: new Set([...cl.deps, ...cl.dependents]),
  });
}

/**
 * Animate the camera onto a node's position at ratio 0.4 (a zoom-in level).
 * sigma 3.0.3 camera.animate(state, opts) returns a promise; fire-and-forget.
 */
export function flyTo(sigma: Sigma, node: string) {
  const attrs = sigma.getGraph().getNodeAttributes(node);
  sigma.getCamera().animate({ x: attrs.x as number, y: attrs.y as number, ratio: 0.4 }, { duration: 400 });
}
