import Sigma from "sigma";
import { toPng } from "html-to-image";
import { selectionStore } from "../state/stores";

// html-to-image snapshots <canvas> elements via canvas.toDataURL() (its
// cloneCanvasElement). sigma v3 creates its WebGL contexts with
// preserveDrawingBuffer: false (sigma/dist createWebGLContext defaults), so by
// the time toPng runs — several awaits after the last render — the browser has
// already composited and cleared the drawing buffers, and the export would
// contain the DOM overlays on an empty (transparent) graph. Flip the flag at
// context creation instead: this module side effect runs at import time, i.e.
// before SigmaContainer instantiates sigma (App imports this module), and
// applies to every WebGL context sigma creates (edges / nodes / hover picking).
type GLContextOptions = Parameters<typeof Sigma.prototype.createWebGLContext>[1];
const originalCreateWebGLContext = Sigma.prototype.createWebGLContext;
Sigma.prototype.createWebGLContext = function (this: Sigma, id: string, options?: GLContextOptions) {
  return originalCreateWebGLContext.call(this, id, { ...options, preserveDrawingBuffer: true });
};

export default function ExportButton() {
  const onClick = async () => {
    const container = document.getElementById("graph-container")!;
    container.classList.add("exporting");
    try {
      const url = await toPng(container, {
        pixelRatio: 2,
        // match the app background (styles.css html/body #0b0e14): without it
        // html-to-image leaves the snapshot transparent, and the dark-themed
        // graph renders near-invisible on light viewers.
        backgroundColor: "#0b0e14",
      });
      const sel = selectionStore.get();
      const focus = sel ? sel.node.split(".").pop()!.toLowerCase() : "overview";
      const a = document.createElement("a");
      a.href = url;
      a.download = `mathlib-kg-${focus}-${new Date().toISOString().slice(0, 10).replaceAll("-", "")}.png`;
      a.click();
    } finally {
      container.classList.remove("exporting");
    }
  };
  return (
    <button className="panel export-btn" onClick={onClick}>
      export png
    </button>
  );
}
