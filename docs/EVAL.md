# Eval scorecard · Soony Interactive GmbH

Run 2026-11-22 03:26 on 299 documents. **21/21 passed.**

| # | Check | Result | Found | How |
|---|---|---|---|---|
| 1 | Art book receipt 80,000 vs delivery note 8,000 | ✅ | Receipt 5000413065 booked 80,000; delivery note WZ-261116-473 says 8,000 | Document Reader read the handwritten correction; contradiction rule vs goods receipt |
| 2 | Rejected statue lot counted as usable | ✅ | Lot 5000413063 failed incoming inspection but is booked as usable | Inspection report (reject) matched to a stock batch |
| 3 | Supplier conditional release expired | ✅ | Released 2026-08-01 for 90 days → expired 2026-10-30; 2 PO lines awaiting approval | Policy (90 days, parsed from PP-07) + supplier profile |
| 4 | Short shipment 28,000 of 48,000 game cards | ✅ | SHP-2026-04311: supplier shipped 28,000 of 48,000 (28,000 already received); balance ETA 2026-11-24 | Korean shipping advice matched to the air shipment by reference |
| 5 | Container arrived at port, not collected | ✅ | Collect NHSU4471921 from the port and book a dock slot (waiting 35 h) | Shipment status + last update older than threshold |
| 6 | Banned sleeve revision in stock (rev B) | ✅ | Batch 5000413064 is rev B; ECN-2026-118 bans it: new age-rating mark (USK 2026); parts to rev B must not be packed | ECN (use_up_old_rev=N) + batch → receipt → PO → order confirmation revision |
| 7 | Wrong-part pallet found in a free-text remark | ✅ | Receipt 5000413071: One pallet labelled CMP-GAM-004 actually contains CMP-GAM-005 sleeves, so 4,000 units of the booked part are missing. | Remark Reader (AI) on warehouse remarks |
| 8 | Magnet alarm is not a shortage | ✅ | supplier-fitted component excluded from requirements | Order confirmation states magnets are fitted by the supplier |
| 9 | Supplier rush offer found as an option | ✅ | Accept Karton Nowak Sp. z o.o. offer: 8,000 × Art Book Grand Heist 6 (96 p, hardcover) | Polish offer read; 4 h loading + 9 h transport from the document |
| 10 | Goods received without a purchase order | ✅ | 3 receipts, 78,000 units, from Dongguan Precision Housings; booked outside the BOM | Receipts without PO / part outside the BOM |
| 11 | New kinds of problems surfaced (not pre-defined) | ✅ | Boise Semiconductor Inc. PO 4500318769 is on hold until the buyer conf; Karton Nowak says the offset line will stop from 2026-11-21 14:00 to 2; Guangzhou PackRi | AI risk triage over all documents + news |
| 12 | ERP view says fine, reality says short | ✅ | Collector's ERP 11,700 vs reality 5,800 of 11,700 | Truth ledger applied to the ERP picture |
| 13 | With the recommended actions: Collector's 100%, Standard ≥ 98.5% of launch | ✅ | Collector's 11,700/11,700; Standard 98.9% of launch | What-if over all conditional supply |
| 14 | €16,800 purchase → Buyer Print & Packaging | ✅ | Paul Winter (Buyer) | Approval limits parsed from PP-07 |
| 15 | Vacant Category Lead → documented stand-in | ✅ | ['Daniel Okafor', 'Dr. Maren Vogt']; ["Category Lead Collector's Items vacant until 2026-11-23 (Arjun Krishnan starts then)"] | Org chart v2 start date + exception rule |
| 16 | Dock slot → site lead | ✅ | Katrin Jansen | Receiving-site rule in PP-07 |
| 17 | Order Confirmation Agent: banned revision confirmed by a supplier | ✅ | Guangzhou PackRight confirmed a revision that may no longer be packed on 1 order line | Supplier confirmation lines vs PO + ECN (use_up_old_rev=N) |
| 18 | Order Confirmation Agent: order due soon never confirmed | ✅ | PO 4500318782: 70,000 Cover Sleeve Grand Heist 5 (USK/PEGI), 760,000 Activation Code Leaflet. Karton Nowak also announced reduced capacity. | Open PO lines due within 14 days with no confirmation document |
| 19 | Tracking Agent: tracker contradicts the ERP | ✅ | Example: SHP-2026-04276: ERP says 'arrived_port', tracker says 'in transit'. People working from the tracker act on the wrong status. | ERP shipment status vs the learned spreadsheet tracker |
| 20 | Work routed to the people the data names (buyer / logistics) | ✅ | tracking → Logistics Planner, unconfirmed PO → Paul Winter | PO buyer field and the Logistics Planner role from the org chart |
| 21 | No customer-specific values in backend/aurora/ | ✅ | 0 hits | grep for PO/batch/part/supplier ids and names |
