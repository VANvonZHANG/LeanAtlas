import Graph from "graphology";
import type { DeclBlock } from "./declPack";
import { selectionStore, topicFilterStore, viewStore } from "../state/stores";

/** Node colors by declaration kind (single palette, shared by the graph and
 * any future legend; unknown kinds get the muted default). */
export const KIND_COLORS: Record<string, string> = {
  theorem: "#7fd1b9", lemma: "#8fd8c4", def: "#7fb1d1", instance: "#d1a97f",
  class: "#d17fb1", inductive: "#b1a97f", structure: "#c2b28a", abbrev: "#9aa4bf",
};
export const DEFAULT_KIND_COLOR = "#9aa4bf";

export function kindColor(kind: string): string {
  return KIND_COLORS[kind] ?? DEFAULT_KIND_COLOR;
}

/** Build the declaration-layer graphology graph from one pack block. Edge
 * attr rel:"import" deliberately reuses the module-layer import channel —
 * pin/closure, density slider, hover highlight and edge styling keep their
 * semantics here for free (structure toggles simply match no edges). */
export function buildDeclGraph(block: DeclBlock): Graph {
  const g = new Graph({ type: "directed" }); // single edges: pairs deduped upstream
  for (const d of block.decls) {
    g.addNode(d.name, {
      x: d.x, y: d.y, size: d.s * 2, color: kindColor(d.k),
      label: d.name.split(".").pop() ?? d.name,
      // InfoPanel reads these attrs on every selected node; declarations get
      // honest stand-ins (topic column shows the kind, declCount the out-degree)
      title: d.name, declCount: 0, closureSize: 0, topic: d.k, r: d.s,
    });
  }
  for (const [src, dst] of block.e) {
    // e pairs are [src, dst] = src depends on dst (see DECLPACK.md)
    const s = block.decls[src]!.name, t = block.decls[dst]!.name;
    if (s !== t && !g.hasEdge(s, t)) g.addEdge(s, t, { rel: "import", color: "#26304a", size: 0.5 });
  }
  for (const d of block.decls) {
    g.setNodeAttribute(d.name, "declCount", g.outDegree(d.name));
    g.setNodeAttribute(d.name, "closureSize", g.degree(d.name));
  }
  return g;
}

/** Enter the declaration view of one module. Overview-only interactions must
 * not leak in: a pinned module name does not exist here, and an active topic
 * filter would dim every declaration node (their topic attr is the kind). */
export function drillTo(module: string): void {
  selectionStore.set(null);
  topicFilterStore.set(null);
  viewStore.set({ mode: "decls", module });
}

/** Leave the declaration view; the pin of a declaration stays behind with
 * the graph it belonged to. */
export function backToOverview(): void {
  selectionStore.set(null);
  viewStore.set({ mode: "overview" });
}
