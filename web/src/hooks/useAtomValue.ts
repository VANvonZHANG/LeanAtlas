import { useSyncExternalStore } from "react";
import type { ReadableAtom } from "nanostores";

/**
 * Read a nanostores atom as React state. @nanostores/react is not a
 * dependency; an atom IS an external store: subscribe for changes, get()
 * for the snapshot (nanostores notifies only on value changes, so the
 * snapshot satisfies getSnapshot's identity requirement). Replaces the four
 * per-component wrappers this project hand-rolled before consolidating.
 */
export function useAtomValue<T>(store: ReadableAtom<T>): T {
  return useSyncExternalStore(
    (onChange) => store.subscribe(onChange),
    () => store.get(),
  );
}
