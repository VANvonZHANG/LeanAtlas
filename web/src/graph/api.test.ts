import { afterEach, describe, expect, it, vi } from "vitest";
import { apiStore } from "../state/stores";
import { declPack, type DeclBlock } from "./declPack";
import {
  fetchDepStrip,
  getModuleBlock,
  loadOverviewFromApi,
  probeApi,
  searchDecls,
  type StripPayload,
} from "./api";

const DOC = { schemaVersion: 2, meta: {}, topics: [], nodes: [], edges: [], structureEdges: {} };
const BLOCK: DeclBlock = {
  schemaVersion: 1, module: "M",
  decls: [{ name: "M.a", k: "def", x: 0, y: 0, s: 1.5 }], e: [],
};

function stubFetch(handler: (url: string) => { status: number; body: string } | null) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const r = handler(url);
    if (!r) throw new Error(`unexpected fetch: ${url}`);
    return new Response(r.body, {
      status: r.status, headers: { "Content-Type": "application/json" },
    });
  }));
}

function api(status: number, body: unknown) {
  return { status, body: JSON.stringify({ ok: status < 400, data: body }) };
}

afterEach(() => {
  vi.unstubAllGlobals();
  apiStore.set({ status: "probing", decls: null, modules: null, layoutPresent: false, kgVersion: null });
});

describe("probeApi", () => {
  it("marks up on healthy healthz", async () => {
    stubFetch((u) => (u === "/api/healthz"
      ? api(200, { decls: 9, modules: 3, layoutPresent: true, kgVersion: 2 }) : null));
    await probeApi();
    expect(apiStore.get()).toEqual({
      status: "up", decls: 9, modules: 3, layoutPresent: true, kgVersion: 2,
    });
  });

  it("marks down on html garbage (static hosting answers 200 with a page)", async () => {
    stubFetch((u) => (u === "/api/healthz" ? { status: 200, body: "<!doctype html>" } : null));
    await probeApi();
    expect(apiStore.get().status).toBe("down");
  });

  it("marks down on network failure", async () => {
    stubFetch(() => null);
    await probeApi();
    expect(apiStore.get().status).toBe("down");
  });
});

describe("loadOverviewFromApi", () => {
  it("returns the document when the API serves it", async () => {
    stubFetch((u) => (u === "/api/graph" ? api(200, DOC) : null));
    expect(await loadOverviewFromApi()).toEqual(DOC);
  });

  it("returns null on 503 (no stored layout) and on bad schema", async () => {
    stubFetch((u) => (u === "/api/graph" ? api(503, null) : null));
    expect(await loadOverviewFromApi()).toBeNull();
    stubFetch((u) => (u === "/api/graph" ? api(200, { schemaVersion: 1 }) : null));
    expect(await loadOverviewFromApi()).toBeNull();
  });
});

describe("searchDecls", () => {
  it("resolves to [] instead of throwing when the API is down", async () => {
    stubFetch(() => null);
    expect(await searchDecls("foo")).toEqual([]);
  });
});

describe("fetchDepStrip", () => {
  const STRIP: StripPayload = {
    total: 2,
    groups: [
      { from: "Mathlib.A.user", kind: "theorem", count: 2,
        edges: [{ to: "Mathlib.B.base", kind: "def" }, { to: "Mathlib.B.aux", kind: "lemma" }] },
    ],
  };

  it("fetches the grouped module-pair strip", async () => {
    stubFetch((u) => (u === "/api/depstrip?a=Mathlib.A&b=Mathlib.B&limit=500"
      ? api(200, STRIP) : null));
    expect(await fetchDepStrip("Mathlib.A", "Mathlib.B")).toEqual(STRIP);
  });

  it("throws on API error", async () => {
    stubFetch((u) => (u === "/api/depstrip?a=X&b=Y&limit=500" ? api(503, null) : null));
    await expect(fetchDepStrip("X", "Y")).rejects.toThrow("503");
  });
});

describe("getModuleBlock", () => {
  it("uses the API when up", async () => {
    apiStore.set({ status: "up", decls: 1, modules: 1, layoutPresent: true, kgVersion: 1 });
    const pack = vi.spyOn(declPack, "getModule");
    stubFetch((u) => (u === "/api/module/M/decls" ? api(200, BLOCK) : null));
    expect(await getModuleBlock("M")).toEqual(BLOCK);
    expect(pack).not.toHaveBeenCalled();
    pack.mockRestore();
  });

  it("falls back to the static pack when the API fails", async () => {
    apiStore.set({ status: "up", decls: 1, modules: 1, layoutPresent: false, kgVersion: null });
    const pack = vi.spyOn(declPack, "getModule").mockResolvedValue(BLOCK);
    stubFetch((u) => (u === "/api/module/M/decls" ? api(503, null) : null));
    expect(await getModuleBlock("M")).toEqual(BLOCK);
    expect(pack).toHaveBeenCalled();
    pack.mockRestore();
  });

  it("goes straight to the pack when the API is down", async () => {
    apiStore.set({ status: "down", decls: null, modules: null, layoutPresent: false, kgVersion: null });
    const pack = vi.spyOn(declPack, "getModule").mockResolvedValue(null);
    stubFetch(() => null);
    expect(await getModuleBlock("M")).toBeNull();
    expect(pack).toHaveBeenCalledWith("M");
    pack.mockRestore();
  });
});
