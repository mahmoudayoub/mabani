#!/usr/bin/env python3
"""
Targeted sample test — runs search on specific known-problem rows
and reports whether the fixes improved their ranking.

Tests:
  Civil:
    Row 18:  X 41 00 AAA — was in pool@41, didn't make final
    Row 435: C 31 13 ABA — was in pool@538, didn't make final
    Row 615: C 11 13 IAA — was in pool@250, final fam@17

  Mechanical:
    Row 214:  P 07 19 FAC — was pool@6 fam=MISS, not in final
    Row 278:  P 13 16 ACH — was pool@59 fam=MISS, not in final
    Row 976:  P 11 17 CAB — was pool=1 → final=6 (reranking hurt)
    Row 2164: H 33 13 AAO — was pool=1 → final=21 (reranking hurt badly)
    Row 2166: H 33 13 ABS — was pool=1 → final=7
    Row 1152: P 32 00 AAD — was pool=4 → final=6

Usage:
    cd backend && ../.venv/bin/python ../scripts/sample_test.py
    (or from repo root: cd backend && .venv/bin/python ../scripts/sample_test.py)
"""

import asyncio
import logging
import sys
import os
import re as _re
from pathlib import Path
from collections import defaultdict

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("sample_test")

LOCAL_DB_PATH = "/tmp/pricecode_index.db"
BASE_DIR = Path(__file__).resolve().parent.parent

_PRESETS = {
    "civil": {
        "input": BASE_DIR / "Astoria trial 1 (Copy).xlsx",
        "gt_col": "agc",
        "rows": {
            18:  ("X 41 00 AAA", "pool@41 → NOT_IN_FINAL"),
            435: ("C 31 13 ABA", "pool@538 → NOT_IN_FINAL"),
            615: ("C 11 13 IAA", "pool@250 → fam@17"),
        },
    },
    "mechanical": {
        "input": BASE_DIR / "Astoria-Mechanical Commented.xlsx",
        "gt_col": "estimator",
        "rows": {
            214:  ("P 07 19 FAC", "pool@6 → NOT_IN_FINAL"),
            278:  ("P 13 16 ACH", "pool@59 → NOT_IN_FINAL"),
            976:  ("P 11 17 CAB", "pool=1 → final=6"),
            2164: ("H 33 13 AAO", "pool=1 → final=21"),
            2166: ("H 33 13 ABS", "pool=1 → final=7"),
            1152: ("P 32 00 AAD", "pool=4 → final=6"),
        },
    },
}

_COMPACT_RE = _re.compile(r'^([A-Za-z])(\d{2})(\d{2})([A-Za-z][A-Za-z0-9]{1,2})$')

def _compact_to_spaced(code: str) -> str:
    m = _COMPACT_RE.match(code.strip())
    if m:
        return f"{m.group(1).upper()} {m.group(2)} {m.group(3)} {m.group(4).upper()}"
    return code.strip().upper()


def _normalize_code(code: str) -> str:
    c = _compact_to_spaced(code)
    return _re.sub(r'\s+', ' ', c).strip().upper()


def _family(code: str) -> str:
    parts = code.split()
    return " ".join(parts[:3]) if len(parts) >= 3 else code


async def run_sample(preset_name: str):
    preset = _PRESETS[preset_name]
    target_rows = preset["rows"]

    print(f"\n{'='*70}")
    print(f"SAMPLE TEST — {preset_name.upper()}")
    print(f"Testing {len(target_rows)} specific rows")
    print(f"{'='*70}\n")

    # ── Load matcher ────────────────────────────────────────────────
    from almabani.pricecode.lexical_search import LexicalMatcher
    print("Loading index...", flush=True)
    matcher = await LexicalMatcher.create(
        db_path=LOCAL_DB_PATH,
        source_files=None,
        max_candidates=20,
    )
    print(f"Index loaded: {len(matcher._refs):,} refs\n")

    # ── Parse items ─────────────────────────────────────────────────
    from almabani.parsers.excel_parser import ExcelParser
    from almabani.parsers.hierarchy_processor import HierarchyProcessor
    from almabani.pricecode.pipeline import PriceCodePipeline

    parser = ExcelParser()
    sheets_data = parser.excel_io.read_excel(str(preset["input"]))
    sheet_name = next(iter(sheets_data.keys()))
    df, header_row_idx = sheets_data[sheet_name]
    columns = parser.excel_io.detect_columns(df)

    detected_code_col = None
    for col in df.columns:
        if 'price code' in str(col).lower():
            detected_code_col = col
            break
    if detected_code_col:
        columns['code'] = detected_code_col

    dummy = PriceCodePipeline.__new__(PriceCodePipeline)
    dummy.excel_parser = parser
    dummy.hierarchy_processor = HierarchyProcessor()
    parent_map = dummy._build_parent_map(df, header_row_idx, columns)
    items = dummy._extract_items_for_allocation(df, header_row_idx, columns, parent_map)

    # Build row→item mapping
    row_to_item = {}
    for item in items:
        excel_row = item['row_index'] + 1
        row_to_item[excel_row] = item

    # ── Run search on target rows ───────────────────────────────────
    results = []
    for row_num in sorted(target_rows.keys()):
        gt_code, old_behavior = target_rows[row_num]
        gt_norm = _normalize_code(gt_code)
        gt_fam = _family(gt_norm)

        item = row_to_item.get(row_num)
        if not item:
            print(f"  Row {row_num}: SKIPPED (not found in parsed items)")
            continue

        item_dict = {
            "description": item.get('description', ''),
            "parent": item.get('parent'),
            "grandparent": item.get('grandparent'),
            "unit": item.get('unit'),
            "item_code": item.get('item_code'),
            "category_path": item.get('category_path'),
        }

        candidates = matcher.search_sync(item_dict)

        # Find exact rank and family rank
        exact_rank = None
        fam_rank = None
        for i, cand in enumerate(candidates):
            cand_code = _normalize_code(cand.get("price_code", ""))
            cand_fam = _family(cand_code)
            if cand_code == gt_norm and exact_rank is None:
                exact_rank = i + 1
            if cand_fam == gt_fam and fam_rank is None:
                fam_rank = i + 1

        # Report
        desc_short = (item.get('description', '') or '')[:50]
        exact_str = f"exact@{exact_rank}" if exact_rank else "exact=MISS"
        fam_str = f"fam@{fam_rank}" if fam_rank else "fam=MISS"

        # Color coding for terminal
        if exact_rank == 1:
            status = "✓ EXACT@1"
        elif exact_rank:
            status = f"~ exact@{exact_rank}"
        elif fam_rank:
            status = f"~ {fam_str}"
        else:
            status = "✗ MISS"

        improved = ""
        # Compare with old behavior
        if "NOT_IN_FINAL" in old_behavior:
            if exact_rank:
                improved = "  ← IMPROVED (was missing)"
            elif fam_rank:
                improved = "  ← IMPROVED (was missing, now fam match)"
        elif "final=" in old_behavior:
            old_rank = int(old_behavior.split("final=")[1])
            if exact_rank and exact_rank < old_rank:
                improved = f"  ← IMPROVED ({old_rank}→{exact_rank})"
            elif exact_rank and exact_rank >= old_rank:
                improved = f"  ← SAME/WORSE ({old_rank}→{exact_rank})"

        print(f"  Row {row_num:>5d}: GT={gt_code}")
        print(f"           {desc_short}")
        print(f"           OLD: {old_behavior}")
        print(f"           NOW: {exact_str} | {fam_str} | {len(candidates)} candidates{improved}")

        # Show top 3 candidates
        for i, cand in enumerate(candidates[:3]):
            pc = cand.get("price_code", "?")
            sc = cand.get("score", 0)
            cd = (cand.get("leaf_description", "") or cand.get("description", ""))[:50]
            mark = " ◄" if _normalize_code(pc) == gt_norm else ""
            print(f"           #{i+1}: {pc} (score={sc:.2f}) {cd}{mark}")
        print()

    print(f"{'='*70}\n")


def main():
    presets_to_run = sys.argv[1:] if len(sys.argv) > 1 else list(_PRESETS.keys())
    for preset in presets_to_run:
        if preset not in _PRESETS:
            print(f"Unknown preset: {preset}")
            continue
        asyncio.run(run_sample(preset))


if __name__ == "__main__":
    main()
