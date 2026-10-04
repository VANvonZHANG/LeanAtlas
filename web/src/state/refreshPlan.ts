import type Graph from "graphology";
import type { Hover } from "../graph/computeNodeColor";

/**
 * Which renderer work a store transition requires. "full" re-runs the
 * node/edge reducers over the whole graph (caller frame-gates these to at
 * most one per rAF); "partial" lists exactly the items whose reducer output
 * can change, applied via sigma.refresh({ partialGraph, skipIndexation: true }).
 */
export type RefreshPlan =
  | { kind: "full" }
  | { kind: "partial"; nodes: string[]; edges: string[] };

export type StoreKind = "hover" | "selection" | "topicFilter" | "edges";

// Hover transitions are the only O(degree) case: they recolor the incident
// edges and (under an active topic filter) restore the hovered node and its
// direct neighbors. Every other kind changes all node colors or all edge
// visibility at once, so its dirty set IS the whole graph — mapping them here
// (instead of inlining "full" at the call site) keeps the decision testable
// against future "optimizations" that would silently skip items.
export function planRefresh(
  kind: "hover",
  graph: Graph,
  from: Hover | null,
  to: Hover | null,
): RefreshPlan;
export function planRefresh(
  kind: "selection" | "topicFilter" | "edges",
  graph: Graph,
  from: unknown,
  to: unknown,
): RefreshPlan;
export function planRefresh(
  kind: "hover" | "selection" | "topicFilter" | "edges",
  graph: Graph,
  from: unknown,
  to: unknown,
): RefreshPlan {
  if (kind !== "hover") return { kind: "full" };
  // implementation params stay `unknown` (widest) so both overloads are
  // signature-compatible; the guard narrows for the hover branch.
  const sides = [from, to].filter((h): h is Hover => h !== null);
  const nodes = new Set<string>();
  const edges = new Set<string>();
  for (const h of sides) {
    nodes.add(h.node);
    for (const n of h.neighbors) nodes.add(n);
    // graphology: edges(node) returns all incident edge keys, both directions.
    for (const e of graph.edges(h.node)) edges.add(e);
  }
  // sorted output: a deterministic contract (tests, and stable partialGraph order)
  return { kind: "partial", nodes: [...nodes].sort(), edges: [...edges].sort() };
}
