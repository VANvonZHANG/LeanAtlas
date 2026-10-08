import { atom } from "nanostores";
import type { Hover, Selection } from "../graph/computeNodeColor";
import { cloneEdgeStyleDefaults, type EdgeStyle, type RelKind } from "../graph/edgeStyle";
import { cloneTopicStyleDefaults, type TopicStyle } from "../graph/topicStyle";

export const selectionStore = atom<Selection | null>(null);
export const topicFilterStore = atom<string | null>(null);
export const edgeDensityStore = atom<number>(0); // 0..1
export const hoverStore = atom<Hover | null>(null);

export interface StructureToggles { extends: boolean; instantiates: boolean; fields: boolean }
export const structureTogglesStore = atom<StructureToggles>({
  extends: true, instantiates: true, fields: true,
});
export const edgeStyleStore = atom<Record<RelKind, EdgeStyle>>(cloneEdgeStyleDefaults());
export const topicStyleStore = atom<TopicStyle>(cloneTopicStyleDefaults());

/** Which graph the page shows: the module-layer overview, or the declaration
 * subgraph of one module (P2 drill-down). Switching mounts a fresh
 * SigmaContainer (App keys the GraphView by view), so every overlay and
 * binder re-runs its mount logic against the new graph. */
export type View = { mode: "overview" } | { mode: "decls"; module: string };
export const viewStore = atom<View>({ mode: "overview" });

/** Live-API availability (P3): probed once per page load from App. "down"
 * hides every API-only feature; rendering never depends on it (static files
 * remain the data source of last resort — spec §2 degradation ladder). */
export interface ApiState {
  status: "probing" | "up" | "down";
  decls: number | null;
  modules: number | null;
  layoutPresent: boolean;
  kgVersion: number | null;
}
export const apiStore = atom<ApiState>({
  status: "probing", decls: null, modules: null, layoutPresent: false, kgVersion: null,
});
