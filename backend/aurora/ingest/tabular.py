"""Load the tenant's tabular files into canonical pandas tables.

Files differ in delimiter, decimal separator, date format and column names (e.g. a
legacy SAP export with EBELN/LIFNR). Column synonyms come from the tenant config;
nothing here knows about a particular customer.
"""
from __future__ import annotations

import csv
import fnmatch
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from aurora.config import Tenant


@dataclass
class TableLoad:
    name: str
    frame: pd.DataFrame
    sources: list[str] = field(default_factory=list)
    unmapped_columns: dict[str, list[str]] = field(default_factory=dict)


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_csv(path: Path) -> pd.DataFrame:
    text = _read_text(path)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        sep = dialect.delimiter
    except csv.Error:
        sep = ","
    df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    return df


def _read_json(path: Path) -> pd.DataFrame:
    """Flatten a JSON export: either a list of records or one record nested under a key."""
    import json
    data = json.loads(_read_text(path))
    if isinstance(data, list):
        records = data
    else:
        payloads = [v for v in data.values() if isinstance(v, (dict, list))]
        main = max(payloads, key=lambda v: len(json.dumps(v))) if payloads else data
        records = main if isinstance(main, list) else [main]
    df = pd.json_normalize(records, sep="_").astype(str).replace({"None": "", "nan": ""})
    meta = {k: v for k, v in data.items() if not isinstance(v, (dict, list))} if isinstance(data, dict) else {}
    for k, v in meta.items():
        df[f"_meta_{k}"] = str(v)
    return df


def _camel_to_snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def _to_number(series: pd.Series) -> pd.Series:
    """Parse numbers written as 1234.5, 1,2345 (decimal comma) or 640.000 (thousands dot)."""
    def conv(v: str):
        v = (v or "").strip()
        if not v:
            return None
        if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", v):      # 640.000 -> 640000
            v = v.replace(".", "")
        elif re.fullmatch(r"-?\d+,\d+", v):               # 1,5200 -> 1.52
            v = v.replace(",", ".")
        else:
            v = v.replace(",", "")
        try:
            return float(v)
        except ValueError:
            return None
    return series.map(conv)


def _to_date(series: pd.Series) -> pd.Series:
    """Accept ISO dates and US-style MM/DD/YYYY from legacy exports."""
    def conv(v: str):
        v = (v or "").strip()
        if not v or v.startswith("9999"):
            return pd.NaT
        fmt = "%m/%d/%Y" if re.fullmatch(r"\d{2}/\d{2}/\d{4}", v) else None
        return pd.to_datetime(v, format=fmt, errors="coerce", utc=False)
    return series.map(conv)


NUMERIC_HINTS = ("qty", "quantity", "price", "units", "share", "lead_time", "moq",
                 "transit", "safety", "cover", "lat", "lon", "rate", "std_cost", "per")
DATE_HINTS = ("date", "etd", "eta", "valid_from", "valid_to", "last_count", "since", "effective")


class TabularLoader:
    def __init__(self, tenant: Tenant):
        self.tenant = tenant
        self.root = tenant.data_root
        syn = tenant.cfg.get("column_synonyms", {})
        self.synonyms = {alias.lower(): canon for canon, aliases in syn.items() for alias in aliases}

    def _files(self, spec: dict) -> list[Path]:
        matches = sorted(self.root.glob(spec["glob"]))
        excl = spec.get("exclude", [])
        return [p for p in matches if not any(fnmatch.fnmatch(p.name, e) for e in excl)]

    def _canonicalise(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.rename(columns={c: self.synonyms.get(c.lower(), c) for c in df.columns})
        for col in df.columns:
            low = col.lower()
            if any(h in low for h in DATE_HINTS):
                df[col] = _to_date(df[col])
            elif any(h in low for h in NUMERIC_HINTS):
                df[col] = _to_number(df[col])
        return df

    def _read_excel(self, path: Path, spec: dict, extra_known: set[str] | None = None) -> pd.DataFrame:
        """Read every sheet; find the header row (title rows above it are kept as metadata)."""
        if not spec.get("header_detect"):
            return pd.read_excel(path, dtype=str)
        import openpyxl
        frames = []
        wb = openpyxl.load_workbook(path, data_only=True)
        for ws in wb:
            rows = [["" if c is None else str(c).strip() for c in r] for r in ws.iter_rows(values_only=True)]
            rows = [r for r in rows if any(r)]
            known = set(self.synonyms) | {v.lower() for v in self.synonyms.values()} | {k.lower() for k in (extra_known or ())}
            hdr_i = next((i for i, r in enumerate(rows) if sum(c.lower() in known for c in r) >= 2), None)
            if hdr_i is None:
                continue
            title = " ".join(" ".join(r) for r in rows[:hdr_i])
            hdr = rows[hdr_i]
            body = [r[:len(hdr)] for r in rows[hdr_i + 1:]]
            df = pd.DataFrame(body, columns=hdr)
            df["_sheet"] = ws.title
            df["_title"] = title
            m = re.search(r"(\d{4}-\d{2}-\d{2})(?:[ ,T]+(\d{1,2}:\d{2}))?", title)
            df["_as_of"] = f"{m.group(1)}T{m.group(2) or '00:00'}" if m else ""
            frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def load(self, name: str) -> TableLoad:
        spec = self.tenant.cfg["tables"][name]
        frames, sources = [], []
        for path in self._files(spec):
            suffix = path.suffix.lower()
            if suffix in (".csv", ".txt"):
                df = _read_csv(path)
            elif suffix == ".json":
                df = _read_json(path)
                df.columns = [_camel_to_snake(c) for c in df.columns]
            else:
                df = self._read_excel(path, spec)
            df = self._canonicalise(df)
            if spec.get("supplier_from_path"):
                df["supplier_id"] = path.parent.name.split("_")[0]
            df["_source"] = str(path.relative_to(self.root))
            frames.append(df)
            sources.append(str(path.relative_to(self.root)))
        # files nobody configured, understood by the Schema Mapper agent
        from aurora.ingest.schema_mapper import SchemaMapper
        for m in SchemaMapper(self.tenant).learned_for(name):
            path = self.root / m["path"]
            if str(path.relative_to(self.root)) in sources:
                continue
            suffix = path.suffix.lower()
            if suffix in (".csv", ".tsv", ".txt"):
                df = _read_csv(path)
            elif suffix == ".json":
                df = _read_json(path)
                df.columns = [_camel_to_snake(c) for c in df.columns]
            else:
                df = self._read_excel(path, {"header_detect": True}, set(m["column_map"]))
            df = df.rename(columns={c: m["column_map"].get(c, c) for c in df.columns})
            df = df.loc[:, ~df.columns.duplicated()]
            df = df.astype(str).replace({"nan": "", "None": "", "NaT": ""})
            df = self._canonicalise(df)
            if "supplier_id" not in df.columns and m["path"].startswith("suppliers/"):
                df["supplier_id"] = m["path"].split("/")[1].split("_")[0]   # file lives in the supplier's folder
            df["_source"] = m["path"]
            df["_mapped_by"] = m["status"]
            frames.append(df)
            sources.append(m["path"])
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        key = spec.get("key")
        if key and not frame.empty and key in frame.columns:
            # Several exports of the same record (e.g. profile.csv and a newer profile.json):
            # keep the newest per key, preferring JSON/v2 exports, but keep older columns.
            frame["_rank"] = frame["_source"].str.endswith(".json").astype(int)
            frame = (frame.sort_values("_rank").groupby(key, as_index=False).last()
                     .drop(columns="_rank"))
        return TableLoad(name=name, frame=frame, sources=sources)

    def load_all(self) -> dict[str, TableLoad]:
        return {name: self.load(name) for name in self.tenant.cfg["tables"]}


def normalise_supplier_ids(df: pd.DataFrame, known: list[str]) -> pd.DataFrame:
    """Map bare vendor numbers (legacy '7') onto known IDs ('VEND-0007')."""
    if "supplier_id" not in df.columns:
        return df
    by_num = {int(re.sub(r"\D", "", k)): k for k in known if re.search(r"\d", k)}

    def conv(v):
        s = str(v).strip()
        if s in known:
            return s
        digits = re.sub(r"\D", "", s)
        return by_num.get(int(digits), s) if digits else s
    df = df.copy()
    df["supplier_id"] = df["supplier_id"].map(conv)
    return df
