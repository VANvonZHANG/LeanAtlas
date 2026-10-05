import { atom } from "nanostores";
import type { Hover, Selection } from "../graph/computeNodeColor";
import { cloneEdgeStyleDefaults, type EdgeStyle, type RelKind } from "../graph/edgeStyle";

export const selectionStore = atom<Selection | null>(null);
export const topicFilterStore = atom<string | null>(null);
export const edgeDensityStore = atom<number>(0); // 0..1
export const hoverStore = atom<Hover | null>(null);

export interface StructureToggles { extends: boolean; instantiates: boolean; fields: boolean }
export const structureTogglesStore = atom<StructureToggles>({
  extends: true, instantiates: true, fields: true,
});
export const edgeStyleStore = atom<Record<RelKind, EdgeStyle>>(cloneEdgeStyleDefaults());
