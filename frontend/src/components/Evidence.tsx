"use client";

import { useState } from "react";
import { classify, type EvidenceItem, sourceLabel } from "@/lib/evidence";
import { cx, Icon, Src } from "./ui";

/** Compact chip that opens a cited file. */
export function EvidenceLink({ raw }: { raw: string }) {
  const item = classify(raw);
  if (item.kind === "quote") return <span className="text-xs italic text-zinc-500">“{item.text}”</span>;
  if (item.kind === "ref")
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-zinc-50 px-1.5 py-0.5 text-xs text-zinc-500 ring-1 ring-inset ring-zinc-200">
        <Icon name="doc" className="h-3 w-3 text-zinc-400" />
        {item.label}
      </span>
    );
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex max-w-[280px] items-center gap-1 rounded-md bg-white px-1.5 py-0.5 text-xs text-zinc-600 ring-1 ring-inset ring-zinc-200 transition hover:text-zinc-900 hover:ring-zinc-400"
      title={item.path}
    >
      <Icon name={item.kind === "image" ? "image" : "doc"} className="h-3 w-3 text-zinc-400" />
      <span className="truncate">{item.label}</span>
    </a>
  );
}

/** Full evidence panel: scans inline, PDFs with an optional preview, refs and extracted quotes. */
export function EvidencePanel({ items }: { items: string[] }) {
  const uniq = Array.from(new Set(items));
  const parsed = uniq.map(classify);
  const images = parsed.filter((p): p is Extract<EvidenceItem, { kind: "image" }> => p.kind === "image");
  const pdfs = parsed.filter((p): p is Extract<EvidenceItem, { kind: "pdf" }> => p.kind === "pdf");
  const files = parsed.filter((p): p is Extract<EvidenceItem, { kind: "file" }> => p.kind === "file");
  const refs = parsed.filter((p): p is Extract<EvidenceItem, { kind: "ref" }> => p.kind === "ref");
  const quotes = parsed.filter((p): p is Extract<EvidenceItem, { kind: "quote" }> => p.kind === "quote");

  if (!parsed.length) return <p className="text-[13px] text-zinc-400">No documents cited.</p>;

  return (
    <div className="space-y-3">
      {images.map((img) => (
        <figure key={img.path} className="overflow-hidden rounded-lg ring-1 ring-zinc-200">
          <a href={img.url} target="_blank" rel="noreferrer" className="block bg-zinc-100">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={img.url} alt={img.label} className="max-h-[420px] w-full object-contain" />
          </a>
          <figcaption className="flex items-center justify-between gap-2 border-t border-zinc-200 bg-white px-3 py-2 text-xs text-zinc-500">
            <span className="flex min-w-0 items-center gap-1.5">
              <Src>Scan</Src>
              <span className="truncate">{img.label}</span>
            </span>
            <a href={img.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-zinc-900">
              Open <Icon name="external" className="h-3 w-3" />
            </a>
          </figcaption>
        </figure>
      ))}

      {quotes.map((q, i) => (
        <blockquote
          key={i}
          className="border-l-2 border-amber-400 bg-amber-50/40 py-1.5 pl-3 pr-2 text-[13px] italic leading-snug text-zinc-700"
        >
          “{q.text}”<span className="ml-1 not-italic text-[11px] text-zinc-400">read by the Document Reader</span>
        </blockquote>
      ))}

      {pdfs.map((p) => (
        <PdfCard key={p.path} url={p.url} label={p.label} path={p.path} />
      ))}

      {(files.length > 0 || refs.length > 0) && (
        <div className="flex flex-wrap gap-1.5">
          {files.map((f) => (
            <a
              key={f.path}
              href={f.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md bg-white px-2 py-1 text-xs text-zinc-600 ring-1 ring-inset ring-zinc-200 hover:text-zinc-900 hover:ring-zinc-400"
            >
              <Src>{sourceLabel(f.path)}</Src>
              {f.label}
            </a>
          ))}
          {refs.map((r) => (
            <span
              key={r.label}
              className="inline-flex items-center gap-1.5 rounded-md bg-zinc-50 px-2 py-1 text-xs text-zinc-500 ring-1 ring-inset ring-zinc-200"
            >
              <Icon name="doc" className="h-3 w-3 text-zinc-400" />
              {r.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function PdfCard({ url, label, path }: { url: string; label: string; path: string }) {
  const [preview, setPreview] = useState(false);
  return (
    <div className="overflow-hidden rounded-lg ring-1 ring-zinc-200">
      <div className="flex items-center justify-between gap-2 bg-white px-3 py-2">
        <span className="flex min-w-0 items-center gap-2 text-[13px] text-zinc-700" title={path}>
          <Icon name="doc" className="text-zinc-400" />
          <span className="truncate">{label}</span>
        </span>
        <span className="flex shrink-0 items-center gap-3 text-xs text-zinc-500">
          <button onClick={() => setPreview(!preview)} className="hover:text-zinc-900">
            {preview ? "Hide preview" : "Preview"}
          </button>
          <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-zinc-900">
            Open <Icon name="external" className="h-3 w-3" />
          </a>
        </span>
      </div>
      {preview && <iframe src={url} title={label} className={cx("h-[440px] w-full border-t border-zinc-200 bg-zinc-100")} />}
    </div>
  );
}
