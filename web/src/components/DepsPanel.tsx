import { useEffect, useState } from "react";
import { fetchDeclDeps, type DepsPayload } from "../graph/api";
import { pendingPinStore } from "../state/stores";
import { drillTo, kindColor } from "../graph/declView";

/** Cross-module dependency panel (spec C-1). One grouped request per (node,
 * dir); groups by the opposite module; picking an entry drills into that
 * module and pins the other endpoint via pendingPinStore (the same seam the
 * search picks use). */
export default function DepsPanel({ node, onClose }: { node: string; onClose: () => void }) {
  const [dir, setDir] = useState<"in" | "out">("in");
  const [state, setState] = useState<
    | { status: "loading" }
    | { status: "ready"; payload: DepsPayload }
    | { status: "error"; message: string }
  >({ status: "loading" });

  useEffect(() => {
    setState({ status: "loading" });
    let cancelled = false;
    fetchDeclDeps(node, dir)
      .then((payload) => { if (!cancelled) setState({ status: "ready", payload }); })
      .catch((err: unknown) => {
        if (!cancelled) setState({ status: "error", message: String(err) });
      });
    return () => { cancelled = true; };
  }, [node, dir]);

  const jump = (groupModule: string, edge: { from: string; to: string }) => {
    pendingPinStore.set(dir === "in" ? edge.from : edge.to);
    drillTo(groupModule);
  };

  return (
    <div className="deps-panel">
      <div className="deps-head">
        <button className={dir === "in" ? "active" : ""} onClick={() => setDir("in")}
                title="declarations that depend on this one">← uses it</button>
        <button className={dir === "out" ? "active" : ""} onClick={() => setDir("out")}
                title="declarations this one depends on">uses →</button>
        <span className="deps-node">{node}</span>
        <button className="close" onClick={onClose}>×</button>
      </div>
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
                  const other = dir === "in" ? e.from : e.to;
                  const otherKind = (dir === "in" ? e.fromKind : e.toKind) ?? "def";
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
    </div>
  );
}
