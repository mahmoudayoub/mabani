#!/usr/bin/env python3
"""Quick benchmark: measure per-search time on 10 items."""
import asyncio, sys, time
from pathlib import Path
BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import logging, boto3
logging.basicConfig(level=logging.WARNING)

LOCAL_DB = "/tmp/pricecode_index.db"
S3_BUCKET = "pricecodestack-pricecodedata88b02d08-ciqjcb0pjn80"
S3_DB_KEY = "metadata/pricecode_index.db"

if not Path(LOCAL_DB).exists():
    print("Downloading DB from S3...")
    boto3.client("s3").download_file(S3_BUCKET, S3_DB_KEY, LOCAL_DB)
    print(f"Downloaded {Path(LOCAL_DB).stat().st_size:,} bytes")

# 10 representative items (mix of thin/rich, civil/mech)
ITEMS = [
    {"description": "25 mm diameter (Horizontal)", "parent": "uPVC pipes and fittings for above ground sanitary drainage system", "grandparent": "", "unit": "m", "item_code": "", "category_path": ""},
    {"description": "Ready mix concrete C32/40 MPa", "parent": "Cast In Situ Concrete", "grandparent": "CONCRETE WORK", "unit": "m3", "item_code": "", "category_path": "CONCRETE WORK"},
    {"description": "Reinforced Concrete Raft Foundations: 250mm", "parent": "Foundations", "grandparent": "SUBSTRUCTURE", "unit": "m3", "item_code": "", "category_path": ""},
    {"description": "150x150mm", "parent": "Rectangular ductwork galvanized duct", "grandparent": "HVAC DUCTWORK", "unit": "m", "item_code": "", "category_path": "HVAC"},
    {"description": "Inline centrifugal fan type; air flow rate 640 L/s; external static pressure 300 Pa", "parent": "Supply air fans", "grandparent": "HVAC EQUIPMENT", "unit": "nr", "item_code": "", "category_path": "HVAC"},
    {"description": "100mm thick blinding; to slab on grade", "parent": "Concrete blinding", "grandparent": "SUBSTRUCTURE", "unit": "m3", "item_code": "", "category_path": ""},
    {"description": "75 mm diameter; ref. HZ CCWP (Horizontal)", "parent": "Chilled Water Pipes", "grandparent": "PLUMBING", "unit": "m", "item_code": "", "category_path": "PLUMBING"},
    {"description": "Cold water plate heat exchanger; ref. CCWHE-01", "parent": "Heat Exchangers", "grandparent": "PLUMBING", "unit": "nr", "item_code": "", "category_path": ""},
    {"description": "Concrete tiles on slab, size: varies, light beige", "parent": "Floor Finishes", "grandparent": "FINISHES", "unit": "m2", "item_code": "", "category_path": ""},
    {"description": "Submersible Waste Water Pump, flow rate 6.9 L/s, duty head 20m", "parent": "Pumps", "grandparent": "PLUMBING", "unit": "nr", "item_code": "", "category_path": "PLUMBING"},
]

async def main():
    from almabani.pricecode.lexical_search import LexicalMatcher

    print("Loading index...")
    t0 = time.perf_counter()
    matcher = await LexicalMatcher.create(db_path=LOCAL_DB, source_files=None, max_candidates=20)
    t_load = time.perf_counter() - t0
    print(f"Index loaded in {t_load:.1f}s ({len(matcher._refs):,} refs)\n")

    # Warmup
    matcher.search_sync(ITEMS[0])

    times = []
    for i, item in enumerate(ITEMS):
        t1 = time.perf_counter()
        cands = matcher.search_sync(item)
        dt = (time.perf_counter() - t1) * 1000
        times.append(dt)
        desc = item["description"][:50]
        print(f"  [{i+1:2d}] {dt:7.0f}ms  {len(cands):3d} cands  {desc}")

    print(f"\n  Avg: {sum(times)/len(times):.0f}ms")
    print(f"  Min: {min(times):.0f}ms")
    print(f"  Max: {max(times):.0f}ms")
    print(f"  P50: {sorted(times)[len(times)//2]:.0f}ms")

asyncio.run(main())
