import { backToOverview } from "../graph/declView";

/** Top bar in declaration mode: where you are + the way back. Carries the
 * .panel class so PNG export hides it like every other overlay panel. */
export default function DeclBar({ module, decls, edges }: { module: string; decls: number; edges: number }) {
  return (
    <div className="panel decl-bar">
      <button className="back" onClick={backToOverview}>← overview</button>
      <span className="mod">{module}</span>
      <span className="meta">{decls} decls · {edges} edges</span>
    </div>
  );
}
