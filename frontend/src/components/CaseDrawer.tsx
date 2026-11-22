"use client";

import Link from "next/link";
import { useEffect } from "react";
import { CaseDetailView } from "./CaseDetail";
import { btn, Icon } from "./ui";

export function CaseDrawer({
  id,
  names,
  onClose,
}: {
  id: string | null;
  names: Record<string, string>;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!id) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.querySelector('[role="dialog"]')) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [id, onClose]);

  if (!id) return null;
  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 animate-fade bg-zinc-900/20 backdrop-blur-[1px]" onClick={onClose} />
      <aside className="absolute inset-y-0 right-0 flex w-full max-w-[720px] animate-slide flex-col bg-white shadow-2xl ring-1 ring-zinc-200">
        <div className="flex h-12 shrink-0 items-center justify-between border-b border-zinc-100 px-4">
          <Link href={`/cases/${encodeURIComponent(id)}`} className={btn.quiet}>
            <Icon name="external" className="h-3.5 w-3.5" />
            <span className="text-[13px]">Open as page</span>
          </Link>
          <button className={btn.quiet} onClick={onClose} aria-label="Close">
            <span className="text-xs text-zinc-400">Esc</span>
            <Icon name="close" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <CaseDetailView id={id} names={names} />
        </div>
      </aside>
    </div>
  );
}
