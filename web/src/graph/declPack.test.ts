import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createServer, type Server } from "node:http";
import { DeclPackClient } from "./declPack";

/** Pack fixture builder mirroring the Python writer: offsets relative to the
 * end of the header, so header growth never shifts blocks. */
function buildPackBytes(headerMeta: object, blocks: Record<string, string>): Buffer {
  const parts: Buffer[] = [];
  let off = 0;
  const modules: Record<string, { o: number; l: number }> = {};
  for (const name of Object.keys(blocks)) {
    const b = Buffer.from(blocks[name], "utf8");
    modules[name] = { o: off, l: b.length };
    off += b.length;
    parts.push(b);
  }
  const hb = Buffer.from(JSON.stringify({ ...headerMeta, modules }), "utf8");
  const prefix = Buffer.alloc(8);
  new DataView(prefix.buffer, prefix.byteOffset, 8).setBigUint64(0, BigInt(hb.length), true);
  return Buffer.concat([prefix, hb, ...parts]);
}

const BLOCK_A =
  '{"schemaVersion":1,"module":"M.A","decls":[{"name":"M.A.f","k":"def","x":0,"y":0,"s":1.5},{"name":"M.A.thm","k":"theorem","x":1,"y":0,"s":2.5}],"e":[[0,1]]}';
const BLOCK_B =
  '{"schemaVersion":1,"module":"M.B","decls":[{"name":"M.B.g","k":"def","x":0,"y":0,"s":1.5}],"e":[]}';

function startServer(buf: Buffer, honorRange: boolean) {
  const requests: string[] = [];
  const server = createServer((req, res) => {
    requests.push(String(req.headers.range ?? "-"));
    const m = /^bytes=(\d+)-(\d+)$/.exec(String(req.headers.range ?? ""));
    if (honorRange && m) {
      const start = Number(m[1]);
      const end = Number(m[2]);
      res.statusCode = 206;
      res.setHeader("content-range", `bytes ${start}-${end}/${buf.length}`);
      res.end(buf.subarray(start, end + 1));
    } else {
      res.statusCode = 200;
      res.end(buf);
    }
  });
  return new Promise<{ server: Server; url: string; requests: string[] }>((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as { port: number }).port;
      resolve({ server, url: `http://127.0.0.1:${port}/declpack.bin`, requests });
    });
  });
}

let rangeSrv: Awaited<ReturnType<typeof startServer>>;
let fullSrv: Awaited<ReturnType<typeof startServer>>;
let badSrv: Awaited<ReturnType<typeof startServer>>;

beforeAll(async () => {
  rangeSrv = await startServer(buildPackBytes({ schemaVersion: 1, meta: { version: "t" } }, { "M.A": BLOCK_A, "M.B": BLOCK_B }), true);
  fullSrv = await startServer(buildPackBytes({ schemaVersion: 1, meta: { version: "t" } }, { "M.A": BLOCK_A }), false);
  badSrv = await startServer(buildPackBytes({ schemaVersion: 9, meta: {} }, { "M.A": BLOCK_A }), true);
});
afterAll(async () => {
  for (const s of [rangeSrv, fullSrv, badSrv]) {
    s.server.closeAllConnections();
    await new Promise<void>((r) => s.server.close(() => r()));
  }
});

describe("DeclPackClient", () => {
  it("loads index and module blocks via 206 ranged fetches", async () => {
    const c = new DeclPackClient(rangeSrv.url);
    const idx = await c.getIndex();
    expect(idx.schemaVersion).toBe(1);
    const block = await c.getModule("M.A");
    expect(block!.module).toBe("M.A");
    expect(block!.decls).toHaveLength(2);
    expect(block!.e).toEqual([[0, 1]]);
  });

  it("sends exact byte ranges for prefix, header, and module", async () => {
    const c = new DeclPackClient(rangeSrv.url);
    // rangeSrv is shared with the test above: assert only this client's own
    // requests, so the check holds no matter which tests ran first
    const n0 = rangeSrv.requests.length;
    await c.getModule("M.B");
    const buf = buildPackBytes({ schemaVersion: 1, meta: { version: "t" } }, { "M.A": BLOCK_A, "M.B": BLOCK_B });
    const hlen = Number(new DataView(buf.buffer, buf.byteOffset, 8).getBigUint64(0, true));
    const oA = JSON.parse(buf.subarray(8, 8 + hlen).toString("utf8")).modules["M.A"];
    const base = 8 + hlen;
    // fixture writes blocks in key order: M.A first, so M.B sits after A
    expect(rangeSrv.requests[n0]).toBe("bytes=0-7");
    expect(rangeSrv.requests[n0 + 1]).toBe(`bytes=8-${8 + hlen - 1}`);
    expect(rangeSrv.requests[n0 + 2]).toBe(`bytes=${base + oA.o + oA.l}-${base + oA.l + BLOCK_B.length - 1}`);
  });

  it("falls back to one full 200 download when the server ignores Range", async () => {
    const c = new DeclPackClient(fullSrv.url);
    const block = await c.getModule("M.A");
    expect(block!.decls[0]!.name).toBe("M.A.f");
    // the prefix GET downloaded the whole file and set the full buffer; the
    // header and module reads that follow are local slices — one wire request
    expect(fullSrv.requests).toHaveLength(1);
  });

  it("caches blocks: a repeated getModule issues no new request", async () => {
    const c = new DeclPackClient(rangeSrv.url);
    await c.getModule("M.A");
    const n = rangeSrv.requests.length;
    await c.getModule("M.A");
    expect(rangeSrv.requests.length).toBe(n);
  });

  it("returns null for a module missing from the index", async () => {
    const c = new DeclPackClient(rangeSrv.url);
    expect(await c.getModule("M.Zzz")).toBeNull();
  });

  it("throws on an unsupported pack schemaVersion", async () => {
    const c = new DeclPackClient(badSrv.url);
    await expect(c.getIndex()).rejects.toThrow(/schemaVersion/);
  });
});
