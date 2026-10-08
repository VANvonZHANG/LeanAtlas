import { useEffect, useRef, useState } from "react";
import {
  fetchDeclDeps,
  fetchDepStrip,
  type DepsPayload,
  type StripPayload,
} from "../graph/api";
import { pendingPinStore } from "../state/stores";
import { drillTo, kindColor } from "../graph/declView";

type DepsState =
  | { status: "loading" }
  | { status: "ready"; payload: DepsPayload }
  | { status: "error"; message: string };
type StripState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; payload: StripPayload }
  | { status: "error"; message: string };

/** Cross-module dependency panel (spec C-1 + C-2). in/out: one grouped
 * request per (node, dir); groups by the opposite module; picking an entry
 * drills into that module and pins the other endpoint via pendingPinStore
 * (the same seam the search picks use). strip: a module-pair A→B edge strip
 * fetched on Go (entries are non-interactive — there is no single node to
 * pin for a module pair). */
export default function DepsPanel({ node, mod, onClose }: {
  node: string;
  mod?: string | null;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<"in" | "out" | "strip">("in");
  const [state, setState] = useState<DepsState>({ status: "loading" });
  const [modA, setModA] = useState("");
  const [modB, setModB] = useState("");
  const [strip, setStrip] = useState<StripState>({ status: "idle" });

  useEffect(() => {
    if (mode === "strip") return; // strip fetches on Go, not per effect run
    setState({ status: "loading" });
    let cancelled = false;
    fetchDeclDeps(node, mode)
      .then((payload) => { if (!cancelled) setState({ status: "ready", payload }); })
      .catch((err: unknown) => {
        if (!cancelled) setState({ status: "error", message: String(err) });
      });
    return () => { cancelled = true; };
  }, [node, mode]);

  const openStrip = () => {
    setMode("strip");
    if (!modA) setModA(mod ?? ""); // prefill A with the current node's module
  };

  // cancelled-flag pattern: each Go bumps the seq, so responses from a
  // superseded request (or after closing the panel) are dropped
  const stripSeq = useRef(0);
  const go = () => {
    const a = modA.trim(), b = modB.trim();
    if (!a || !b || a === b) return;
    const mine = ++stripSeq.current;
    setStrip({ status: "loading" });
    fetchDepStrip(a, b)
      .then((payload) => { if (mine === stripSeq.current) setStrip({ status: "ready", payload }); })
      .catch((err: unknown) => {
        if (mine === stripSeq.current) setStrip({ status: "error", message: String(err) });
      });
  };

  const jump = (groupModule: string, edge: { from: string; to: string }) => {
    pendingPinStore.set(mode === "in" ? edge.from : edge.to);
    drillTo(groupModule);
  };

  const canGo = !!modA.trim() && !!modB.trim() && modA.trim() !== modB.trim();

  return (
    <div className="deps-panel">
      <div className="deps-head">
        <button className={mode === "in" ? "active" : ""} onClick={() => setMode("in")}
                title="declarations that depend on this one">← uses it</button>
        <button className={mode === "out" ? "active" : ""} onClick={() => setMode("out")}
                title="declarations this one depends on">uses →</button>
        <button className={mode === "strip" ? "active" : ""} onClick={openStrip}
                title="all declaration edges from module A to module B">strip</button>
        <span className="deps-node">{node}</span>
        <button className="close" onClick={onClose}>×</button>
      </div>
      {mode !== "strip" && (
        <>
          {state.status === "loading" && <div className="deps-body">loading…</div>}
          {state.status === "error" && <div className="deps-body">{state.message}</div>}
          {state.status === "ready" && (
            <div className="deps-body">
              {state.payload.total === 0 && <div>no cross-module dependencies</div>}
              {state.payload.groups.map((g) => (
                <div key={g.module} className="deps-group">
                  <div className="deps-group-head">{g.module} ({g.count})</div>
                  <ul>
                    {g.edges.map((e) => {
                      const other = mode === "in" ? e.from : e.to;
                      const otherKind = (mode === "in" ? e.fromKind : e.toKind) ?? "def";
                      // external names carry no module to drill into: render, don't jump
                      return (
                        <li key={`${e.from}->${e.to}`}
                            style={g.module === "(external)" ? { cursor: "default" } : undefined}
                            onMouseDown={(ev) => {
                              ev.preventDefault();
                              if (g.module !== "(external)") jump(g.module, e);
                            }}>
                          <span className="kind-dot" style={{ background: kindColor(otherKind) }} />
                          {other}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </>
      )}
      {mode === "strip" && (
        <div className="deps-body">
          <div className="deps-strip-form">
            <input value={modA} placeholder="module A" spellCheck={false}
                   onChange={(e) => setModA(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter" && canGo) go(); }} />
            <span className="deps-strip-arrow">→</span>
            <input value={modB} placeholder="module B" spellCheck={false}
                   onChange={(e) => setModB(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter" && canGo) go(); }} />
            <button className="go" disabled={!canGo} onClick={go}>go</button>
          </div>
          {strip.status === "loading" && <div>loading…</div>}
          {strip.status === "error" && <div>{strip.message}</div>}
          {strip.status === "ready" && (
            <>
              {strip.payload.total === 0 && <div>no dependencies from A to B</div>}
              {strip.payload.groups.map((g) => (
                <div key={g.from} className="deps-group">
                  <div className="deps-group-head">{g.from} ({g.kind ?? "?"}, {g.count})</div>
                  <ul>
                    {g.edges.map((e) => (
                      // module-pair entries: nothing to drill into — render only
                      <li key={`${g.from}->${e.to}`} style={{ cursor: "default" }}>
                        <span className="kind-dot" style={{ background: kindColor(e.kind ?? "def") }} />
                        {e.to}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
