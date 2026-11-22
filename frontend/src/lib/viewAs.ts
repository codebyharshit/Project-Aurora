"use client";

import { useCallback, useSyncExternalStore } from "react";

const KEY = "aurora.viewAs";
const NAME_KEY = "aurora.name";
const listeners = new Set<() => void>();
let urlApplied = false;

/** `?as=Paul%20Winter` opens the page as that person (demo deep links); it is remembered afterwards. */
function applyUrl() {
  if (urlApplied || typeof window === "undefined") return;
  urlApplied = true;
  try {
    const as = new URLSearchParams(window.location.search).get("as");
    if (as === null) return;
    if (as === "" || /^everyone$/i.test(as)) localStorage.removeItem(KEY);
    else {
      localStorage.setItem(KEY, as);
      localStorage.setItem(NAME_KEY, as);
    }
  } catch {}
}

function read(): string | null {
  applyUrl();
  try {
    return localStorage.getItem(KEY) || null;
  } catch {
    return null;
  }
}

/**
 * Who is looking at the launch room: null = Everyone. Setting a person also sets the name used to
 * prefill Approve / Decide / Confirm, so one choice carries through every form.
 */
export function useViewAs(): [string | null, (v: string | null) => void] {
  const who = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    read,
    () => null,
  );
  const set = useCallback((v: string | null) => {
    try {
      if (v) {
        localStorage.setItem(KEY, v);
        localStorage.setItem(NAME_KEY, v);
      } else localStorage.removeItem(KEY);
    } catch {}
    listeners.forEach((l) => l());
    nameListeners.forEach((l) => l());
  }, []);
  return [who, set];
}

/** Shared with useName so both stores refresh when a person is chosen. */
export const nameListeners = new Set<() => void>();

/** "Dr. Maren Vogt" → "Maren" */
export function firstName(name: string): string {
  return name.replace(/^(Dr\.|Prof\.|Mr\.|Ms\.)\s+/i, "").split(/\s+/)[0] || name;
}
