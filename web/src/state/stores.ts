import { atom } from "nanostores";
import type { Hover, Selection } from "../graph/computeNodeColor";

export const selectionStore = atom<Selection | null>(null);
export const topicFilterStore = atom<string | null>(null);
export const edgeDensityStore = atom<number>(0); // 0..1
export const hoverStore = atom<Hover | null>(null);
