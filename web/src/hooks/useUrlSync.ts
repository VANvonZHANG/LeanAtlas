import { useEffect } from "react";
import type Sigma from "sigma";
import { parseUrl, serializeUrl, type UrlState } from "../graph/urlState";
import { pinNode } from "../graph/pin";
import { edgeDensityStore, selectionStore, topicFilterStore } from "../state/stores";

// Interactions -> #node&topic&edges&z&x&y, written via history.replaceState (no
// back-button spam) after a 200ms debounce. On mount the hash is parsed once
// and pushed back into the stores/camera (deep-link restore); every subsequent
// store/camera change rewrites the hash, so a copied URL always round-trips.
const DEBOUNCE_MS = 200;

export function useUrlSync(sigma: Sigma, initial: boolean) {
  useEffect(() => {
    if (!initial) return;
    // parseUrl throws URIError when decodeURIComponent meets a malformed
    // %-escape (e.g. "#node=%E0%A4%A"). A hand-mangled hash must not crash the
    // app: degrade to "no restore" and let the first debounced push below
    // rewrite the hash with clean state. (Caught here rather than hardened in
    // urlState.ts to keep T4's pure function and its pinned tests unchanged.)
    let st: UrlState;
    try {
      st = parseUrl(window.location.hash);
    } catch {
      st = {};
    }
    if (st.node && sigma.getGraph().hasNode(st.node)) pinNode(sigma.getGraph(), st.node);
    if (st.topic) topicFilterStore.set(st.topic);
    if (st.edges !== undefined) edgeDensityStore.set(st.edges / 100);
    // z (ratio) is the marker for camera presence: x/y/z restore together only
    // when z parsed, so stray x/y without z does not teleport the camera.
    if (st.z !== undefined)
      sigma.getCamera().setState({ x: st.x ?? 0, y: st.y ?? 0, ratio: st.z });

    let timer: ReturnType<typeof setTimeout> | null = null;
    const push = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        const cam = sigma.getCamera().getState();
        const sel = selectionStore.get();
        window.history.replaceState(
          null, "",
          serializeUrl({
            node: sel?.node,
            topic: topicFilterStore.get() ?? undefined,
            edges: Math.round(edgeDensityStore.get() * 100),
            z: cam.ratio, x: cam.x, y: cam.y,
          }),
        );
      }, DEBOUNCE_MS);
    };
    const unsubs = [selectionStore, topicFilterStore, edgeDensityStore].map((s) =>
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
