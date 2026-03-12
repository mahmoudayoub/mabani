#!/usr/bin/env python3
"""
Debug trace script: shows exactly what happens for specific BOQ items
through the search pipeline (specs extracted, pool scores, rerank factors).

Usage:
    cd /home/ali/Desktop/ammar/Almabani/backend
    .venv/bin/python ../scripts/debug_search_trace.py
"""
import asyncio
import sys
import os
import logging
from pathlib import Path
from collections import defaultdict

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("debug_trace")

LOCAL_DB_PATH = "/tmp/pricecode_index.db"
BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = BASE_DIR / "Astoria trial 1 (Copy).xlsx"

# Rows to trace (Excel 1-based row numbers from the missed-items report)
TRACE_ROWS = [449, 455, 577, 435, 447, 613]


async def main():
    from almabani.pricecode.lexical_search import (
        LexicalMatcher, extract_specs, clean_text, normalize_text,
        tokenize, tokenize_normalized,
    )

    # Force civil preset
    sys.argv = [sys.argv[0], "civil"]
    from local_pricecode_eval import parse_input, download_db

    # 1. Download DB if needed
    download_db()

    # 2. Load matcher
    matcher = await LexicalMatcher.create(
        db_path=LOCAL_DB_PATH,
        source_files=None,
        max_candidates=20,
    )

    # 3. Parse items
    items, sheet_name, df, header_row_idx, columns = parse_input()
    logger.info(f"Parsed {len(items)} items from sheet '{sheet_name}'")

    # Build row→item lookup (excel_row = row_index + 1)
    row_items = {}
    for item in items:
        excel_row = item.get('row_index', -1) + 1
        row_items[excel_row] = item

    for row_num in TRACE_ROWS:
        item = row_items.get(row_num)
        if not item:
            print(f"\n{'='*80}")
            print(f"ROW {row_num}: NOT FOUND in parsed items")
            continue

        desc = item.get('description', '')
        parent = item.get('parent', '')
        grandparent = item.get('grandparent', '')
        category_path = item.get('category_path', '')
        unit = item.get('unit', '')

        print(f"\n{'='*80}")
        print(f"ROW {row_num}: {desc[:80]}")
        print(f"  parent:      {parent[:100]}")
        print(f"  grandparent: {grandparent[:100]}")
        print(f"  category_path: {category_path[:100]}")
        print(f"  unit: {unit}")

        # Extract specs
        desc_specs = extract_specs(desc)
        ctx_text = " ; ".join(filter(None, [desc, parent, grandparent, category_path]))
        ctx_specs = extract_specs(ctx_text)

        # Show non-empty specs
        print(f"\n  desc_specs (non-empty):")
        for k, v in desc_specs.items():
            if v:
                print(f"    {k}: {v}")
        print(f"  ctx_specs (non-empty):")
        for k, v in ctx_specs.items():
            if v:
                print(f"    {k}: {v}")

        # Build effective_specs
        _NUMERIC_SPEC_KEYS = ("mpa", "dn", "dia", "kv", "mm2", "cores", "pn")
        effective_specs = dict(desc_specs)
        for k in _NUMERIC_SPEC_KEYS:
            if ctx_specs.get(k, ()) and not desc_specs.get(k, ()):
                effective_specs[k] = ctx_specs[k]
        print(f"  effective_specs (non-empty):")
        for k, v in effective_specs.items():
            if v:
                print(f"    {k}: {v}")

        # Run search
        item_dict = {
            "description": desc,
            "parent": parent,
            "grandparent": grandparent,
            "unit": unit,
            "item_code": item.get('item_code'),
            "category_path": category_path,
            "has_subcategory_ancestor": item.get('has_subcategory_ancestor', False),
        }
        candidates = matcher.search_sync(item_dict)

        # Show top candidates
        print(f"\n  Top {min(10, len(candidates))} candidates:")
        for i, c in enumerate(candidates[:10]):
            pc = c.get('price_code', '')
            score = c.get('score', 0)
            cdesc = c.get('description', '')[:80]
            print(f"    #{i+1}  {pc:16s}  score={score:7.3f}  {cdesc}")

        # Check if any candidate in our DB matches the GT families
        # (we don't know GT here, just show what we found)
        print()

    # Also: dump what the DB has for some key families
    print(f"\n{'='*80}")
    print("DB INSPECTION: Sample refs by family")
    import sqlite3
    conn = sqlite3.connect(LOCAL_DB_PATH)
    conn.row_factory = sqlite3.Row

    for family_prefix in ["C 31 13", "C 21 11", "C 34 00", "C 11 13"]:
        # Find refs whose price_code starts with this family
        # Price codes can be spaced or compact
        compact = family_prefix.replace(" ", "")
        rows = conn.execute(
            "SELECT price_code, leaf_description, mpa_csv, concrete_elem_csv, prefixed_description "
            "FROM refs WHERE price_code LIKE ? OR price_code LIKE ? LIMIT 8",
            (f"{family_prefix}%", f"{compact}%")
        ).fetchall()
        if rows:
            print(f"\n  Family {family_prefix} ({len(rows)} shown):")
            for r in rows:
                pc = r['price_code']
                leaf = (r['leaf_description'] or '')[:60]
                mpa = r['mpa_csv'] or ''
                elem = r['concrete_elem_csv'] or ''
                print(f"    {pc:16s}  mpa={mpa:6s}  elem={elem:30s}  leaf={leaf}")
        else:
            print(f"\n  Family {family_prefix}: NO REFS FOUND")

    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
