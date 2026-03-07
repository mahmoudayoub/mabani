#!/usr/bin/env python3
"""Categorize all C 31 13 within-family misses.

For each miss, shows:
- GT leaf code decoded (element, mpa, scope, type)
- Winner leaf code decoded
- Which component(s) differ (element? mpa? scope? type?)
- The BOQ description, parent, and extracted specs

Goal: find systematic patterns we can fix.
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.dirname(__file__))
sys.argv = [sys.argv[0], "civil"]

import asyncio
from collections import Counter, defaultdict
from local_pricecode_eval import download_db, load_matcher, parse_input, load_ground_truth

download_db()
matcher = asyncio.run(load_matcher())
items, sheet_name, df, header_row_idx, columns = parse_input()
gt = load_ground_truth()

from almabani.pricecode.lexical_search import extract_specs, clean_text

# ── C 31 13 leaf code decoder ──────────────────────────────────────────
_ELEM_MAP = {
    'A': 'IsoFoot', 'B': 'StripFoot', 'C': 'Raft', 'D': 'TieBeam',
    'E': 'SOG', 'F': 'RetWall_Type?', 'G': 'GradeBeam', 'H': 'Column',
    'I': 'ShearWall', 'J': 'RetWall', 'K': 'Beam', 'L': 'PileCap',
    'M': 'Pile', 'N': 'Slab', 'O': 'FlatSlab', 'P': 'Parapet',
    'Q': 'Stair', 'R': 'Pedestal', 'S': 'Kerb', 'T': 'Ramp',
    'U': 'Neck', 'V': 'DropBeam', 'W': 'TransBeam', 'X': 'SuspSlab',
    'Y': 'DropPanel', 'Z': 'Upstand', 'a': 'Lean/Blinding',
}
_MPA_MAP = {
    'A': '10', 'B': '15', 'C': '20', 'D': '25', 'E': '30',
    'F': '35', 'G': '40', 'H': '45', 'I': '50', 'J': '55', 'K': '60',
    'L': '10V', 'M': '15V', 'N': '20V', 'O': '25V', 'P': '30V',
    'Q': '35V', 'R': '40V', 'S': '45V', 'T': '50V', 'U': '55V', 'V': '60V',
}
_SCOPE_MAP = {
    'A': 'ConcOnly', 'B': 'WithRebar', 'C': 'WithFormwork',
    'D': 'Form+Rebar', 'E': 'SupplyOnly', 'F': 'Supply+Install',
}

def decode_leaf(code):
    """Decode C 31 13 XYZ suffix."""
    parts = code.strip().split()
    if len(parts) < 4 or len(parts[3]) < 3:
        return {'raw': code, 'elem': '?', 'mpa': '?', 'scope': '?'}
    suffix = parts[3]
    return {
        'raw': code,
        'elem_letter': suffix[0],
        'elem': _ELEM_MAP.get(suffix[0], f'?{suffix[0]}'),
        'mpa_letter': suffix[1],
        'mpa': _MPA_MAP.get(suffix[1], f'?{suffix[1]}'),
        'scope_letter': suffix[2],
        'scope': _SCOPE_MAP.get(suffix[2], f'?{suffix[2]}'),
        'type': 'TypeV' if suffix[1] >= 'L' else 'TypeI',
    }

# ── Run search and categorize misses ───────────────────────────────────
miss_categories = Counter()
miss_details = []
elem_misses = Counter()
mpa_misses = Counter()
scope_misses = Counter()
type_misses = Counter()

for item in items:
    excel_row = item.get('row_index', -1) + 1
    gt_code = gt.get(excel_row, '')
    if not gt_code.startswith('C 31 13'):
        continue

    item_dict = {
        "description": item.get("description", ""),
        "parent": item.get("parent", ""),
        "grandparent": item.get("grandparent", ""),
        "unit": item.get("unit", ""),
        "item_code": item.get("item_code"),
        "category_path": item.get("category_path", ""),
    }
    candidates = matcher.search_sync(item_dict)
    if not candidates:
        continue

    winner_code = candidates[0].get('price_code', '???')
    if winner_code == gt_code:
        continue  # exact match, skip

    gt_d = decode_leaf(gt_code)
    win_d = decode_leaf(winner_code)

    desc = item.get('description', '')[:60]
    parent = item.get('parent', '')[:80]
    gp = item.get('grandparent', '')[:50]

    # Categorize the difference
    diffs = []
    if gt_d['elem'] != win_d.get('elem', '?'):
        diffs.append('ELEM')
        elem_misses[f"{gt_d['elem']}→{win_d.get('elem','?')}"] += 1
    if gt_d['mpa'] != win_d.get('mpa', '?'):
        diffs.append('MPA')
        mpa_misses[f"{gt_d['mpa']}→{win_d.get('mpa','?')}"] += 1
    if gt_d['scope'] != win_d.get('scope', '?'):
        diffs.append('SCOPE')
        scope_misses[f"{gt_d['scope']}→{win_d.get('scope','?')}"] += 1
    if gt_d.get('type') != win_d.get('type'):
        diffs.append('TYPE')
        type_misses[f"{gt_d.get('type','?')}→{win_d.get('type','?')}"] += 1

    diff_key = '+'.join(sorted(diffs)) if diffs else 'SAME_FAMILY_DIFF_CODE'
    miss_categories[diff_key] += 1

    # Spec extraction
    ctx_specs = extract_specs(
        f"{desc} ; {parent} ; {gp}"
    )
    mpa_specs = ctx_specs.get('mpa', ())
    elem_specs = ctx_specs.get('concrete_elem', ())

    miss_details.append({
        'row': excel_row,
        'desc': desc,
        'parent': parent,
        'gt': gt_code,
        'winner': winner_code,
        'gt_decoded': gt_d,
        'win_decoded': win_d,
        'diffs': diffs,
        'diff_key': diff_key,
        'mpa_specs': mpa_specs,
        'elem_specs': elem_specs,
        # Check if GT is in top-5
        'gt_rank': next((i+1 for i, c in enumerate(candidates[:20]) if c.get('price_code') == gt_code), '>20'),
    })

# ── Summary ────────────────────────────────────────────────────────────
print("=" * 80)
print(f"C 31 13 WITHIN-FAMILY MISS ANALYSIS ({len(miss_details)} misses)")
print("=" * 80)

print(f"\n── Difference categories ──")
for cat, cnt in miss_categories.most_common():
    print(f"  {cat:30s} {cnt:3d}")

print(f"\n── Element mismatches ──")
for k, cnt in elem_misses.most_common(15):
    print(f"  {k:30s} {cnt:3d}")

print(f"\n── MPa mismatches ──")
for k, cnt in mpa_misses.most_common(15):
    print(f"  {k:30s} {cnt:3d}")

print(f"\n── Scope mismatches ──")
for k, cnt in scope_misses.most_common(10):
    print(f"  {k:30s} {cnt:3d}")

print(f"\n── Type mismatches ──")
for k, cnt in type_misses.most_common(10):
    print(f"  {k:30s} {cnt:3d}")

print(f"\n── GT rank distribution ──")
rank_dist = Counter(d['gt_rank'] for d in miss_details)
for rank in sorted(rank_dist.keys(), key=lambda x: x if isinstance(x, int) else 999):
    print(f"  rank {rank:>4s}: {rank_dist[rank]:3d}")

# ── Detailed miss list grouped by diff category ──
print(f"\n{'='*80}")
print("DETAILED MISSES BY CATEGORY")
print("=" * 80)
for cat, _cnt in miss_categories.most_common():
    print(f"\n── {cat} ({_cnt} misses) ──")
    for d in miss_details:
        if d['diff_key'] != cat:
            continue
        gt_d = d['gt_decoded']
        win_d = d['win_decoded']
        print(f"  Row {d['row']:5d}: {d['desc']}")
        print(f"    GT={d['gt']:16s}  elem={gt_d['elem']:12s} mpa={gt_d['mpa']:4s} scope={gt_d['scope']:12s} type={gt_d.get('type','?')}")
        print(f"    WN={d['winner']:16s}  elem={win_d.get('elem','?'):12s} mpa={win_d.get('mpa','?'):4s} scope={win_d.get('scope','?'):12s} type={win_d.get('type','?')}")
        print(f"    extracted: mpa={d['mpa_specs']}  elem={d['elem_specs']}  gt_rank={d['gt_rank']}")
