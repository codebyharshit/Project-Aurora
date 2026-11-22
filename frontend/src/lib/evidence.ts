import { fileUrl } from "./api";

export type EvidenceItem =
  | { kind: "image"; path: string; url: string; label: string }
  | { kind: "pdf"; path: string; url: string; label: string }
  | { kind: "file"; path: string; url: string; label: string; ext: string }
  | { kind: "ref"; label: string }
  | { kind: "quote"; text: string };

const FILE_RE = /^[^\s]+\.(jpe?g|png|gif|webp|pdf|csv|docx?|xlsx?|json|txt|eml|md|yaml)$/i;

// The backend sometimes cites a bare file name ("goods_receipts.csv", "memo_launch_priorities.docx")
// instead of a path relative to the data root. Until it returns full paths, resolve the common ones.
const BARE_FILE_DIRS: Record<string, string> = {
  csv: "soony/erp/",
  pdf: "soony/context/",
  docx: "soony/context/",
  doc: "soony/context/",
};

export function basename(path: string): string {
  return path.split("/").pop() || path;
}

export function resolvePath(path: string): string {
  if (path.includes("/")) return path;
  const ext = path.split(".").pop()?.toLowerCase() || "";
  return (BARE_FILE_DIRS[ext] || "") + path;
}

/** Human label for a file: "Delivery note WZ-261116-473.jpg" stays a filename, but tidier. */
export function prettyName(path: string): string {
  return basename(path).replace(/_/g, " ");
}

export function classify(raw: string): EvidenceItem {
  const s = raw.trim();
  if (FILE_RE.test(s)) {
    const path = resolvePath(s);
    const ext = s.split(".").pop()!.toLowerCase();
    const url = fileUrl(path);
    const label = prettyName(s);
    if (/^(jpe?g|png|gif|webp)$/.test(ext)) return { kind: "image", path, url, label };
    if (ext === "pdf") return { kind: "pdf", path, url, label };
    return { kind: "file", path, url, label, ext };
  }
  // Short references like "bom_delta (ECN-2026-118)" vs. extracted sentences from a document.
  if (s.length < 60 && !/[.!?]$/.test(s)) return { kind: "ref", label: s };
  return { kind: "quote", text: s };
}

/** Friendly name for a source document: "Approval policy", "Launch memo", "Email" … */
export function docName(s: string): string {
  if (/pp-07|policy/i.test(s)) return "Approval policy";
  if (/memo/i.test(s)) return "Launch memo";
  if (/org_chart/i.test(s)) return "Org chart";
  if (/onboarding/i.test(s)) return "Onboarding notes";
  if (/^inbox\//.test(s) || /\.eml$/i.test(s)) return "Email";
  return prettyName(s);
}

export function sourceLabel(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase();
  if (ext === "csv") return "ERP";
  if (/^(jpe?g|png)$/.test(ext || "")) return "Scan";
  if (ext === "pdf") return "PDF";
  if (ext === "docx") return "Memo";
  return "File";
}
