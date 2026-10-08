import { useEffect, useState } from "react";
import type Graph from "graphology";
import type { DeclBlock } from "../graph/declPack";
import { getModuleBlock } from "../graph/api";
import { buildDeclGraph } from "../graph/declView";

export type DeclGraphState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; graph: Graph; block: DeclBlock }
  | { status: "error"; message: string };

/** Load one module's declaration block and its graph. module === null keeps
 * the hook idle (hooks are called unconditionally in App). A late response
 * from a superseded module is dropped via the cancelled flag. */
export function useDeclGraph(module: string | null): DeclGraphState {
  const [state, setState] = useState<DeclGraphState>({ status: "idle" });
  useEffect(() => {
    if (!module) {
      setState({ status: "idle" });
      return;
    }
    let cancelled = false;
    setState({ status: "loading" });
    getModuleBlock(module)
      .then((block) => {
        if (cancelled) return;
        if (!block) setState({ status: "error", message: `no declaration data for ${module}` });
        else setState({ status: "ready", graph: buildDeclGraph(block), block });
      })
      .catch((err: unknown) => {
        if (!cancelled) setState({ status: "error", message: String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [module]);
  return state;
}
