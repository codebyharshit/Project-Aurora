"use client";

import { useCallback, useSyncExternalStore } from "react";
import { nameListeners } from "./viewAs";

const KEY = "aurora.name";

function read(): string {
  try {
    return localStorage.getItem(KEY) || "";
  } catch {
    return "";
  }
}

/** The person using this browser, remembered locally so forms come prefilled. Set by View-as too. */
export function useName(): [string, (v: string) => void] {
  const name = useSyncExternalStore(
    (cb) => {
      nameListeners.add(cb);
      return () => nameListeners.delete(cb);
    },
    read,
    () => "",
  );
  const set = useCallback((v: string) => {
    try {
      localStorage.setItem(KEY, v);
    } catch {}
    nameListeners.forEach((l) => l());
  }, []);
  return [name, set];
}
