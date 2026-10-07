/** declpack.bin client: lazy per-module declaration blocks over HTTP Range.
 *
 * File layout (web/DECLPACK.md): [8B LE u64 headerLen][header JSON][module
 * blocks…]. The index is fetched once; each drill fetches exactly one
 * module's byte range. Servers that ignore Range (vite dev / sirv) answer
 * 200 with the whole file — then the pack is buffered once and later reads
 * are local slices, so dev works unchanged (first drill downloads the full
 * pack). A failed probe resets the index promise so a retry is possible. */
export interface DeclRow { name: string; k: string; x: number; y: number; s: number }
export interface DeclBlock {
  schemaVersion: number;
  module: string;
  decls: DeclRow[];
  e: [number, number][];
}
export interface PackIndex {
  schemaVersion: number;
  modules: Record<string, { o: number; l: number }>;
}

const PREFIX_LEN = 8;

export class DeclPackClient {
  private readonly url: string;
  private indexPromise: Promise<PackIndex> | null = null;
  private base = 0; // byte offset where module blocks start
  private full: ArrayBuffer | null = null; // set when the server ignored Range
  private readonly cache = new Map<string, DeclBlock>();

  constructor(url = "declpack.bin") {
    this.url = url;
  }

  getIndex(): Promise<PackIndex> {
    this.indexPromise ??= this.loadIndex().catch((err: unknown) => {
      this.indexPromise = null; // a failed probe must stay retryable
      throw err;
    });
    return this.indexPromise;
  }

  private async loadIndex(): Promise<PackIndex> {
    const prefix = await this.fetchRange(0, PREFIX_LEN - 1);
    const headerLen = Number(new DataView(prefix.buf).getBigUint64(0, true));
    if (!Number.isSafeInteger(headerLen) || headerLen <= 0)
      throw new Error("declpack: bad header length");
    const header = await this.fetchRange(PREFIX_LEN, PREFIX_LEN + headerLen - 1);
    this.base = PREFIX_LEN + headerLen;
    const idx = JSON.parse(new TextDecoder().decode(header.buf)) as PackIndex;
    if (idx.schemaVersion !== 1)
      throw new Error(`declpack: unsupported schemaVersion ${idx.schemaVersion}`);
    return idx;
  }

  async getModule(name: string): Promise<DeclBlock | null> {
    const cached = this.cache.get(name);
    if (cached) return cached;
    const idx = await this.getIndex();
    const hit = idx.modules[name];
    if (!hit) return null; // module alive at layout time but absent from the pack
    const res = await this.fetchRange(this.base + hit.o, this.base + hit.o + hit.l - 1);
    const block = JSON.parse(new TextDecoder().decode(res.buf)) as DeclBlock;
    if (block.schemaVersion !== 1)
      throw new Error(`declpack: block ${name} schemaVersion ${block.schemaVersion}`);
    this.cache.set(name, block);
    return block;
  }

  /** One ranged GET. A 200 answer means the server ignored Range: buffer the
   * whole file and slice locally from now on. */
  private async fetchRange(start: number, end: number): Promise<{ buf: ArrayBuffer }> {
    if (this.full) return { buf: this.full.slice(start, end + 1) };
    const res = await fetch(this.url, { headers: { Range: `bytes=${start}-${end}` } });
    if (!res.ok) throw new Error(`declpack: fetch ${this.url} -> ${res.status}`);
    const buf = await res.arrayBuffer();
    if (res.status === 206) return { buf };
    this.full = buf;
    return { buf: buf.slice(start, end + 1) };
  }
}

/** Singleton: one pack per page, shared index + block caches. */
export const declPack = new DeclPackClient();
