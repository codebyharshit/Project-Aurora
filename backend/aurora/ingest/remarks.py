"""Receipt remarks: receiving writes free text ("qty short", "1 pallet holds the wrong part").
The AI reads each remark once and says whether it changes the usable quantity of a part."""
from __future__ import annotations

import hashlib
import json

from aurora.agents import llm
from aurora.world import World

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["index", "affects_usable_qty", "part_id", "usable_delta", "reason"],
        "properties": {"index": {"type": "integer"}, "affects_usable_qty": {"type": "boolean"},
                       "part_id": {"type": ["string", "null"]}, "usable_delta": {"type": "number"},
                       "reason": {"type": "string"}}}}}}

SYSTEM = """You read goods-receipt remarks written by warehouse staff. For each numbered receipt decide
whether the remark means the usable stock of the booked part differs from the booked quantity, and by
how much (negative = fewer usable units than booked). Examples: wrong part on a pallet booked under this
part, damaged and unusable units, quantity short but booked in full. "qty short" where the booked
quantity already reflects the short delivery, or "damaged packaging" with usable goods, is 0.
Return one item per index; reason in one plain-English sentence."""


def usable_deltas(world: World) -> list[dict]:
    r = world.t("receipts")
    rows = r[r["remark"].astype(str).str.strip().ne("") & r["remark"].notna()].to_dict("records")
    if not rows or not llm.available():
        return []
    cands = [{"gr_number": str(x["gr_number"]), "part_id": x["part_id"], "qty_received": x["qty_received"],
              "qty_ordered": x["qty_ordered"], "remark": x["remark"], "delivery_note": x.get("delivery_note", ""),
              "source": x.get("_source", "")} for x in rows]
    key = hashlib.sha256(json.dumps(cands, sort_keys=True, default=str).encode()).hexdigest()[:16]
    cache = world.tenant.state_dir / f"remarks_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    text = "\n".join(f"[{i}] receipt {c['gr_number']}, part {c['part_id']}, ordered {c['qty_ordered']}, "
                     f"booked {c['qty_received']}: {c['remark']}" for i, c in enumerate(cands))
    res = llm.structured(system=SYSTEM, content=text, schema=SCHEMA, role="exec", effort="medium")
    out = []
    for it in res["items"]:
        if it["affects_usable_qty"] and 0 <= it["index"] < len(cands):
            c = cands[it["index"]]
            out.append({**c, "part_id": c["part_id"], "usable_delta": it["usable_delta"], "reason": it["reason"]})
    cache.write_text(json.dumps(out, indent=1, default=str))
    return out
