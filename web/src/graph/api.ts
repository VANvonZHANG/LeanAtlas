/** Typed client for the leanatlas serve API (P3). Helpers resolve to null /
 * empty instead of throwing wherever a fallback exists: the app never assumes
 * the API is up — callers fall back to static files or hide API-only UI
 * (spec §2 degradation ladder). */
import type { DataDoc } from "./loadData";
import { declPack, type DeclBlock } from "./declPack";
import { apiStore } from "../state/stores";

async function apiJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`api: ${path} -> ${res.status}`);
  const body = (await res.json()) as { ok: boolean; data: T };
  if (!body.ok) throw new Error(`api: ${path} -> ok:false`);
  return body.data;
}

export async function probeApi(): Promise<void> {
  try {
    const d = await apiJson<{
      decls: number; modules: number; layoutPresent: boolean; kgVersion: number | null;
    }>("/api/healthz");
    apiStore.set({
      status: "up", decls: d.decls, modules: d.modules,
      layoutPresent: d.layoutPresent, kgVersion: d.kgVersion,
    });
  } catch {
    apiStore.set({
      status: "down", decls: null, modules: null, layoutPresent: false, kgVersion: null,
    });
  }
}

/** Overview document from the API, or null when it cannot serve one (server
 * absent, DB down, or layout never stored — spec levels 2–3). */
export async function loadOverviewFromApi(): Promise<DataDoc | null> {
  try {
    const doc = await apiJson<DataDoc>("/api/graph");
    if (doc.schemaVersion !== 2) throw new Error(`api: schemaVersion ${doc.schemaVersion}`);
    return doc;
  } catch {
    return null;
  }
}

export interface DeclHit { name: string; kind: string; module: string }

export async function searchDecls(q: string, limit = 20): Promise<DeclHit[]> {
  try {
    return await apiJson<DeclHit[]>(
      `/api/search?q=${encodeURIComponent(q)}&limit=${limit}`);
  } catch {
    return [];
  }
}

export interface DeclDetail {
  name: string; shortName: string | null; kind: string | null;
  module: string | null; typeSignature: string | null; docstring: string | null;
  sourceFile: string | null; startLine: number | null; endLine: number | null;
  sourceText: string | null; attrs: string[] | null;
  isDeprecated: boolean | null; isExternal: boolean | null; sourceUrl: string | null;
}

export function fetchDeclDetail(name: string): Promise<DeclDetail> {
  return apiJson<DeclDetail>(`/api/decl/${encodeURIComponent(name)}`);
}

export interface DepsEdge { from: string; fromKind: string | null; to: string; toKind: string | null }
export interface DepsPayload {
  dir: "in" | "out"; total: number;
  groups: { module: string; count: number; edges: DepsEdge[] }[];
}

export function fetchDeclDeps(name: string, dir: "in" | "out", limit = 200): Promise<DepsPayload> {
  return apiJson<DepsPayload>(
    `/api/decl/${encodeURIComponent(name)}/deps?dir=${dir}&limit=${limit}`);
}

/** One module's declaration block from whichever source is available: the
 * live API when up (fresh database), else the static pack. null = module
 * unknown to both. API failure mid-request falls through to the pack. */
export async function getModuleBlock(name: string): Promise<DeclBlock | null> {
  if (apiStore.get().status === "up") {
    try {
      const block = await apiJson<DeclBlock>(
        `/api/module/${encodeURIComponent(name)}/decls`);
      if (block.schemaVersion !== 1) throw new Error(`api: block schemaVersion ${block.schemaVersion}`);
      return block;
    } catch {
      // fall through to the static pack
    }
  }
  return declPack.getModule(name);
}
