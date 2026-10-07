import { useEffect } from "react";
import type Sigma from "sigma";
import { parseUrl, serializeUrl, type UrlState } from "../graph/urlState";
import { pinNode } from "../graph/pin";
import {
  edgeDensityStore,
  selectionStore,
  structureTogglesStore,
  topicFilterStore,
  viewStore,
} from "../state/stores";

// Interactions -> #node&topic&edges&se&z&x&y, written via history.replaceState (no
// back-button spam) after a 200ms debounce. On mount the hash is parsed once
// and pushed back into the stores/camera (deep-link restore); every subsequent
// store/camera change rewrites the hash, so a copied URL always round-trips.
const DEBOUNCE_MS = 200;

// The STORE restore runs exactly once per PAGE LOAD; the node pin and the
// camera restore run on EVERY mount, view-matched. App keys GraphView by
// view, so every overview <-> declarations switch remounts this hook. A
// remount-time re-restore of the stores would re-read the hash that the
// leaving view never rewrote — its cleanup cancels the pending debounced
// push in the same commit — so the stale `#mod=` would flip a just-left
// declaration view straight back and turn the back button into a no-op
// (caught by the P2 real-pack CDP smoke). Module scope outlives the
// remounts; a fresh page load starts with the stores unrestored again. The
// pin is naturally view-safe (hasNode misses on the other graph's names),
// and the view-matched camera applies each view's coordinates to its own
// sigma exactly once — restoring the camera INTO the declaration view on a
// deep link, keeping it out of the overview on the back-button remount, and
// suppressing the quirk of teleporting a freshly drilled declaration camera
// by stale overview coordinates.
let storesRestored = false;

export function useUrlSync(sigma: Sigma, initial: boolean) {
  useEffect(() => {
    if (!initial) return;
    // parseUrl throws URIError when decodeURIComponent meets a malformed
    // %-escape (e.g. "#node=%E0%A4%A"). A hand-mangled hash must not crash
    // the app: degrade to "no restore" and let the first debounced push
    // below rewrite the hash with clean state. (Caught here rather than
    // hardened in urlState.ts to keep T4's pure function and its pinned
    // tests unchanged.)
    let st: UrlState;
    try {
      st = parseUrl(window.location.hash);
    } catch {
      st = {};
    }
    // per mount, view-safe: a declaration name misses the overview graph and
    // a module name misses the declaration graph, so exactly the mount whose
    // graph owns the node pins it — #mod=X&node=someDecl pins someDecl once
    // the declaration view mounts (pack declaration names are Lean full
    // names, NOT module-prefixed).
    if (st.node && sigma.getGraph().hasNode(st.node)) pinNode(sigma.getGraph(), st.node);
    if (!storesRestored) {
      storesRestored = true;
      if (st.topic) topicFilterStore.set(st.topic);
      if (st.mod) viewStore.set({ mode: "decls", module: st.mod });
      if (st.edges !== undefined) edgeDensityStore.set(st.edges / 100);
      // se: structure-relation visibility bitmask (1=extends, 2=instantiates,
      // 4=fields). Parsed values are already clamped to 0..7 by parseUrl.
      if (st.se !== undefined) {
        structureTogglesStore.set({
          extends: (st.se & 1) !== 0, instantiates: (st.se & 2) !== 0, fields: (st.se & 4) !== 0,
        });
      }
    }
    // z (ratio) is the marker for camera presence: x/y/z restore together only
    // when z parsed, so stray x/y without z does not teleport the camera.
    // View-matched: the hash's view must equal the mounted view, so each
    // view's camera receives its own coordinates (the opposite view's
    // mounts skip).
    if (
      st.z !== undefined &&
      (st.mod !== undefined) === (viewStore.get().mode === "decls")
    )
      sigma.getCamera().setState({ x: st.x ?? 0, y: st.y ?? 0, ratio: st.z });

    let timer: ReturnType<typeof setTimeout> | null = null;
    const push = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        const cam = sigma.getCamera().getState();
        const sel = selectionStore.get();
        const view = viewStore.get();
        window.history.replaceState(
          null, "",
          serializeUrl({
            node: sel?.node,
            topic: topicFilterStore.get() ?? undefined,
            edges: Math.round(edgeDensityStore.get() * 100),
            se: (() => { const t = structureTogglesStore.get();
              return (t.extends ? 1 : 0) | (t.instantiates ? 2 : 0) | (t.fields ? 4 : 0); })(),
            mod: view.mode === "decls" ? view.module : undefined,
            z: cam.ratio, x: cam.x, y: cam.y,
          }),
        );
      }, DEBOUNCE_MS);
    };
    const unsubs = [selectionStore, topicFilterStore, edgeDensityStore, structureTogglesStore, viewStore].map((s) =>
      s.subscribe(push),
    );
    sigma.getCamera().on("updated", push);
    return () => {
      unsubs.forEach((u) => u());
      // per-reference removal (not removeAllListeners): React StrictMode
      // double-mount must not leak this handler next to RefreshOnStoreChange's
      // own "updated" listener on the same camera.
      sigma.getCamera().removeListener("updated", push);
      if (timer) clearTimeout(timer);
    };
  }, [sigma, initial]);
}
