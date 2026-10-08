import type { DeclHit } from "./api";
import type { SearchDoc } from "./search";

export type MixedHit =
  | { type: "module"; name: string }
  | { type: "decl"; name: string; kind: string; module: string };

/** Modules first, declarations below (spec §13.4 — no cross-ranking to
 * reconcile: the client keeps its module scoring, the server ranks coarsely). */
export function mergeHits(modules: SearchDoc[], decls: DeclHit[]): MixedHit[] {
  return [
    ...modules.map((m): MixedHit => ({ type: "module", name: m.name })),
    ...decls.map((d): MixedHit => (
      { type: "decl", name: d.name, kind: d.kind, module: d.module })),
  ];
}
