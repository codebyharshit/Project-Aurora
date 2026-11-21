"""Loaders for the structured part of the drop (CSV/XLSX) with explicit typing.

Conventions (also documented in REPORT.md):
    * IDs (PO, GR/batch, part, supplier) are always TEXT.
    * Date-only fields are ISO 'YYYY-MM-DD' strings and mean the local calendar day in Europe/Berlin.
    * Timestamps keep their original offset (column) and get a normalised UTC copy (<col>_utc).
    * Quantities are INTEGER, prices REAL.
    * Every inferred value carries a flag column so nothing is silently assumed.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import openpyxl
import pandas as pd

LEGACY_STATUS = {"GL": "delivered", "LO": "cancelled"}  # GL=geliefert; LO only on the negative 00510 storno line
LEGACY_BUYER = {"FBRUNN": "Felix Brunner", "PWINTE": "Paul Winter", "MLIN": "Mei Lin"}

DATE_COLS = {"gr_date", "order_date", "requested_date", "promised_date", "actual_delivery_date", "etd", "eta",
             "snapshot_date", "last_count", "date", "valid_from", "valid_to", "launch_date", "supplier_since"}
INT_COLS = {"po_line", "qty_ordered", "qty_received", "quantity", "safety_stock", "units_packed", "qty_per",
            "plan_weekly_units", "lead_time_days", "moq", "transit_days"}
FLOAT_COLS = {"unit_price", "weeks_of_cover", "share", "std_cost_eur", "lat", "lon", "last_lat", "last_lon"}


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV as text only; typing happens explicitly afterwards."""
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])


def type_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the column-name based typing conventions to a frame."""
    out = df.copy()
    for col in out.columns:
        if col in DATE_COLS:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%Y-%m-%d")
        elif col in INT_COLS:
            out[col] = pd.to_numeric(out[col], errors="coerce").round().astype("Int64")
        elif col in FLOAT_COLS:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        elif col.endswith("_at"):
            ts = pd.to_datetime(out[col], errors="coerce", utc=True)
            out[f"{col}_utc"] = ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def load_purchase_orders(erp: Path, profiles: pd.DataFrame) -> pd.DataFrame:
    """Unify the legacy SAP export (;-separated, decimal comma, US dates) with the new export."""
    new = type_frame(_read_csv(erp / "purchase_orders_2025H2-2026.csv"))
    new["source_system"] = "erp_export_2025H2"
    new["source_file"] = "soony/erp/purchase_orders_2025H2-2026.csv"
    new["inferred_fields"] = ""

    raw = pd.read_csv(erp / "purchase_orders_legacy_2024-2025H1.csv", sep=";", dtype=str)
    us_date = lambda s: pd.to_datetime(s, format="%m/%d/%Y", errors="coerce").dt.strftime("%Y-%m-%d")
    supplier = "SUP-" + raw["LIFNR"].str.zfill(4)
    prof = profiles.set_index("supplier_id")
    legacy = pd.DataFrame({
        "po_number": raw["EBELN"],
        "po_line": (pd.to_numeric(raw["EBELP"]) // 10).astype("Int64"),  # SAP item 00010 -> line 1
        "supplier_id": supplier,
        "material_id": raw["MATNR"],
        "plant": raw["WERKS"],
        "quantity": pd.to_numeric(raw["MENGE"]).astype("Int64"),
        "unit_price": pd.to_numeric(raw["NETPR"].str.replace(",", ".", regex=False)),
        "currency": supplier.map(prof["currency"]),
        "order_date": us_date(raw["BEDAT"]),
        "requested_date": us_date(raw["EINDT"]),
        "promised_date": us_date(raw["ZZCONF"]),
        "actual_delivery_date": us_date(raw["WEDAT"]),
        "status": raw["ZZSTAT"].map(LEGACY_STATUS).fillna("unknown:" + raw["ZZSTAT"]),
        "buyer": raw["ERNAM"].map(LEGACY_BUYER).fillna(raw["ERNAM"]),
        "incoterm": supplier.map(prof["incoterm"]),
        "note": raw["ZZSTAT"].map({"LO": "cancellation"}),
    })
    legacy["source_system"] = "sap_legacy_2024-2025H1"
    legacy["source_file"] = "soony/erp/purchase_orders_legacy_2024-2025H1.csv"
    legacy["inferred_fields"] = "currency,incoterm(from supplier profile);status(GL/LO mapping);buyer(from ERNAM)"
    po = pd.concat([legacy, new], ignore_index=True)
    po["is_cancellation"] = (po["quantity"] < 0) | po["note"].eq("cancellation")
    return po


def load_supplier_folders(suppliers_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Concatenate profile.csv and components.csv of every supplier folder."""
    profiles, comps = [], []
    for folder in sorted(p for p in suppliers_root.iterdir() if p.is_dir()):
        sup_id = folder.name.split("_")[0]
        if (folder / "profile.csv").exists():
            profiles.append(_read_csv(folder / "profile.csv"))
        if (folder / "components.csv").exists():
            c = _read_csv(folder / "components.csv")
            c.insert(0, "supplier_id", sup_id)
            comps.append(c)
    return type_frame(pd.concat(profiles, ignore_index=True)), type_frame(pd.concat(comps, ignore_index=True))


def _sheet_rows(ws) -> list[list]:
    """All non-empty rows of a worksheet as lists."""
    return [list(r) for r in ws.iter_rows(values_only=True) if any(v is not None for v in r)]


def load_price_lists(suppliers_root: Path, xref: dict[str, str]) -> pd.DataFrame:
    """Read supplier price-list XLSX notices; map supplier part numbers via the contract cross-reference."""
    rows = []
    for path in sorted(suppliers_root.glob("*/notices/*.xlsx")):
        sup_id = path.parts[-3].split("_")[0]
        sheet = _sheet_rows(openpyxl.load_workbook(path, data_only=True).worksheets[0])
        header, body = sheet[0], sheet[1:]
        reason = next((r[0] for r in body if isinstance(r[0], str) and r[0].startswith("Reason")), None)
        pct = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", reason or "")
        for r in body:
            rec = dict(zip(header, r))
            if not rec.get("New price"):
                continue
            raw_part = str(rec["Material"])
            rows.append({
                "supplier_id": sup_id, "source_file": path.relative_to(suppliers_root.parent).as_posix(),
                "part_raw": raw_part, "part_id": raw_part if raw_part.startswith("CMP-") else xref.get(raw_part),
                "part_mapping": "direct" if raw_part.startswith("CMP-") else ("contract_annex_c" if raw_part in xref else "unmapped"),
                "description": rec.get("Description"), "old_price": rec.get("Current price"),
                "new_price": rec.get("New price"), "currency": rec.get("Currency"),
                "valid_from": str(rec.get("Valid from"))[:10], "reason": reason,
                "change_pct": float(pct.group(1)) if pct else None,
            })
    return pd.DataFrame(rows)


def load_tracker(path: Path, profiles: pd.DataFrame) -> pd.DataFrame:
    """Manual shipment tracker; supplier names mapped to IDs via the supplier profiles."""
    sheet = _sheet_rows(openpyxl.load_workbook(path, data_only=True).worksheets[0])
    df = pd.DataFrame(sheet[1:], columns=[str(c).strip().lower().replace("/", "_").replace(" ", "_") for c in sheet[0]])
    name_to_id = dict(zip(profiles["name"], profiles["supplier_id"]))
    df["supplier_id"] = df["supplier"].map(name_to_id)
    df["pos"] = df["pos"].astype(str).str.replace(" ", "", regex=False).str.replace(",", "|", regex=False)
    df["status"] = df["status"].str.strip().str.replace(" ", "_")
    for c in ("etd", "eta"):
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.strftime("%Y-%m-%d")
    df["source_file"] = path.name
    return df.rename(columns={"shipment": "shipment_id", "container_awb": "reference", "pos": "po_numbers"})


def load_launch_plan(path: Path) -> dict[str, pd.DataFrame]:
    """Launch plan workbook: one table per sheet (header row auto-detected)."""
    wb = openpyxl.load_workbook(path, data_only=True)
    out: dict[str, pd.DataFrame] = {}
    for ws in wb.worksheets:
        rows = _sheet_rows(ws)
        filled = lambda r: sum(v is not None for v in r)
        # a single-cell first row followed by a wider row is a sheet title, not a header
        start = 1 if len(rows) > 1 and filled(rows[0]) == 1 and filled(rows[1]) > 1 else 0
        header = [re.sub(r"[^a-z0-9]+", "_", str(h).lower()).strip("_") if h is not None else f"col{i}" for i, h in enumerate(rows[start])]
        df = pd.DataFrame(rows[start + 1:], columns=header)
        if start:
            df.attrs["title"] = rows[0][0]
        out[f"lp_{ws.title.lower()}"] = df
    if "lp_inbound" in out:
        for c in ("etd", "eta"):
            out["lp_inbound"][c] = pd.to_datetime(out["lp_inbound"][c]).dt.strftime("%Y-%m-%d")
    return out


def explode_pipe(df: pd.DataFrame, key: str, col: str, new: str) -> pd.DataFrame:
    """Turn a pipe-separated list column into a bridge table (key, value)."""
    return (df[[key, col]].dropna().assign(**{new: lambda d: d[col].str.split("|")}).explode(new)[[key, new]]
            .assign(**{new: lambda d: d[new].str.strip()}))


def load_all(data: Path, con: sqlite3.Connection, xref: dict[str, str]) -> dict[str, int]:
    """Load every structured source into SQLite (replace semantics). Returns row counts per table."""
    soony, sup_root = data / "soony", data / "suppliers"
    profiles, supplier_components = load_supplier_folders(sup_root)
    tables: dict[str, pd.DataFrame] = {
        "supplier_profiles": profiles,
        "supplier_components": supplier_components,
        "purchase_orders": load_purchase_orders(soony / "erp", profiles),
        "goods_receipts": type_frame(_read_csv(soony / "erp/goods_receipts.csv")),
        "stock_snapshot": type_frame(_read_csv(soony / "erp/stock_snapshot.csv")),
        "packout_log": type_frame(_read_csv(soony / "erp/packout_log.csv")),
        "shipments_erp": type_frame(_read_csv(soony / "erp/open_shipments.csv")),
        "shipments_tracker": load_tracker(next((soony / "logistics").glob("*.xlsx")), profiles),
        "price_lists": load_price_lists(sup_root, xref),
    }
    for name in ("bom", "components", "products", "routes", "ports", "sites", "logistics_providers"):
        tables[f"m_{name}"] = type_frame(_read_csv(soony / f"master/{name}.csv"))
    tables.update(load_launch_plan(soony / "context/launch_plan_GH6.xlsx"))
    tables["shipment_po"] = explode_pipe(tables["shipments_erp"], "shipment_id", "po_numbers", "po_number")
    tables["shipment_material"] = explode_pipe(tables["shipments_erp"], "shipment_id", "material_ids", "material_id")
    tables["tracker_po"] = explode_pipe(tables["shipments_tracker"], "shipment_id", "po_numbers", "po_number")
    for name, df in tables.items():
        df.to_sql(name, con, if_exists="replace", index=False)
    return {k: len(v) for k, v in tables.items()}
