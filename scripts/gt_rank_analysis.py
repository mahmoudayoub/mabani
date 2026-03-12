#!/usr/bin/env python3
"""
GT Rank Distribution Analyzer
For every GT item, find where the GT lands in the ranking, and if it's
not rank-1, compute the FULL score breakdown for both GT ref and Winner ref.
Then identify which score component(s) are responsible for GT losing.
"""
import sys, os, re, math
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

from almabani.pricecode.lexical_search import (
    tokenize, tokenize_normalized, extract_specs, normalize_text,
    clean_text, _unit_family, _infer_ref_unit_family,
    _rapidfuzz_ratio, _infer_discipline_from_context,
    _extract_scope_letter, _parse_compact_code, OBJECT_TOKENS,
    _detect_expected_scope, _detect_mep_prefix, infer_discipline_from_query,
    is_generic_item,
)

def compute_score_breakdown(matcher, item_dict, ref, wq):
    """Compute individual score components for a single ref, mirroring the rerank loop."""
    qweights, desc_specs, ctx_specs, guessed_disc, distinctive, alpha_dist, short = wq

    description = item_dict.get("description", "") or ""
    parent_str = item_dict.get("parent", "") or ""
    gp_str = item_dict.get("grandparent", "") or ""
    _catpath_str = item_dict.get("category_path", "") or ""
    unit = item_dict.get("unit", "") or ""

    core_norm = normalize_text(description)
    _query_toks_list = tokenize_normalized(core_norm)
    boq_unit_fam = _unit_family(unit)
    distinctive_objects = distinctive & OBJECT_TOKENS

    _parent_alpha = matcher._alpha_tokens(set(tokenize(parent_str))) if parent_str else set()
    _gp_alpha = matcher._alpha_tokens(set(tokenize(gp_str))) if gp_str else set()
    _cp_alpha = matcher._alpha_tokens(set(tokenize(_catpath_str))) if _catpath_str else set()
    _ctx_alpha = _parent_alpha | _gp_alpha | _cp_alpha
    _ctx_alpha -= alpha_dist

    route_toks = alpha_dist | matcher._alpha_tokens(
        set(tokenize(" ; ".join([parent_str, gp_str, _catpath_str])))
    )

    _all_ctx_low = (parent_str + " " + gp_str + " " + _catpath_str).lower()
    _ctx_has_precast = bool(re.search(r"\bprecast\b", _all_ctx_low))
    _ctx_is_rebar = (
        bool(re.search(
            r"\b(?:steel\s*)?bar\s*reinforcement\b|\brebar\b|\bhigh\s*yield\b"
            r"|\bsteel\s*reinforc(?:ement|ing)\b",
            _all_ctx_low,
        ))
        and boq_unit_fam == "weight"
    )

    expected_scope = _detect_expected_scope(parent_str, gp_str)

    # Sheet affinity
    sheet_aff = {}
    _sa_best_aff = 0.0
    _sa_rank_2 = 0.0
    if matcher.sheet_sigs and route_toks:
        sheet_aff = matcher._sheet_affinity(route_toks, qweights)
        if sheet_aff:
            _sa_best_aff = max(sheet_aff.values())
            if _sa_best_aff > 0:
                sorted_aff = sorted(sheet_aff.values(), reverse=True)
                _sa_rank_2 = sorted_aff[1] / _sa_best_aff if len(sorted_aff) > 1 else 0.0

    # -- Score components --
    leaf_norm = clean_text(ref["norm_leaf"])
    full_norm = clean_text(ref["norm_text"])
    _cached_toks = ref.get("_tok_tuple")
    ref_toks = set(_cached_toks) if _cached_toks else set(tokenize_normalized(full_norm))
    overlap = distinctive & ref_toks
    alpha_overlap = alpha_dist & ref_toks
    obj_overlap = bool(distinctive_objects & ref_toks)

    # 1. TF-IDF lex score
    lex_score = 0.0
    for tok, qw in qweights.items():
        if tok in ref_toks:
            lex_score += qw * matcher.idf.get(tok, 0.0)
    final = lex_score

    # 2. Fuzzy
    fuzzy_add = 0.0
    if core_norm and leaf_norm:
        ratio = _rapidfuzz_ratio(core_norm, leaf_norm) / 100.0
        fuzzy_add += 1.35 * ratio
        if core_norm in full_norm or leaf_norm in core_norm:
            fuzzy_add += 0.8
        if full_norm and full_norm != leaf_norm:
            full_ratio = _rapidfuzz_ratio(core_norm, full_norm) / 100.0
            if full_ratio > ratio:
                fuzzy_add += 0.45 * (full_ratio - ratio)
    final += fuzzy_add

    # 3. Bigram1
    bigram1_add = 0.0
    if len(_query_toks_list) >= 2:
        _bigram_hits = 0
        for _bi in range(len(_query_toks_list) - 1):
            _bg = _query_toks_list[_bi] + " " + _query_toks_list[_bi + 1]
            if _bg in full_norm:
                _bigram_hits += 1
        if _bigram_hits > 0:
            bigram1_add = 0.30 * min(_bigram_hits, 4)
    final += bigram1_add

    # 4. Leaf overlap (mult)
    leaf_toks = set(ref.get("_leaf_tok_tuple") or ()) or set(tokenize_normalized(leaf_norm))
    leaf_alpha = matcher._alpha_tokens(leaf_toks)
    leaf_overlap = alpha_dist & leaf_alpha
    leaf_mult = 1.0
    if alpha_dist and leaf_alpha:
        leaf_ratio = len(leaf_overlap) / max(1, len(alpha_dist))
        if leaf_ratio >= 0.5:
            leaf_mult = 1.0 + 0.80 * leaf_ratio
        elif leaf_ratio == 0.0:
            leaf_mult = 0.50
    final *= leaf_mult

    # 5. Segment hierarchy (mult)
    seg_mult = 1.0
    precast_pen = 1.0
    if _ctx_alpha:
        _prefix_desc = clean_text(ref["prefixed_description"])
        _seg_parts = [s.strip() for s in _prefix_desc.split(";")]
        if len(_seg_parts) > 1:
            _intermediate = " ".join(_seg_parts[:-1])
            _inter_toks = matcher._alpha_tokens(
                set(tokenize_normalized(normalize_text(_intermediate)))
            )
            if _inter_toks:
                _seg_overlap = _ctx_alpha & _inter_toks
                _seg_ratio = len(_seg_overlap) / max(1, len(_ctx_alpha))
                if _seg_ratio >= 0.3:
                    seg_mult = 1.0 + 0.35 * _seg_ratio
                _inter_low = _intermediate.lower()
                if "precast" in _inter_low and not _ctx_has_precast:
                    precast_pen = 0.55
                elif _ctx_has_precast and "cast in situ" in _inter_low:
                    precast_pen = 0.65
    final *= seg_mult
    final *= precast_pen

    # 6. Token overlap (add)
    tok_add = 0.0
    if distinctive:
        tok_add += 1.25 * (len(overlap) / max(1, len(distinctive)))
    if alpha_dist:
        tok_add += 1.1 * (len(alpha_overlap) / max(1, len(alpha_dist)))
    final += tok_add

    # 7. Bigram2 (add)
    bigram2_add = 0.0
    if len(_query_toks_list) >= 2:
        _ref_tok_list = list(_cached_toks) if _cached_toks else tokenize_normalized(full_norm)
        _ref_tok_set_idx = defaultdict(list)
        for _ri, _rt in enumerate(_ref_tok_list):
            _ref_tok_set_idx[_rt].append(_ri)
        _bigram_hits = 0
        for _qi in range(len(_query_toks_list) - 1):
            _t1, _t2 = _query_toks_list[_qi], _query_toks_list[_qi + 1]
            _positions1 = _ref_tok_set_idx.get(_t1, [])
            _positions2 = _ref_tok_set_idx.get(_t2, [])
            if _positions1 and _positions2:
                for _p1 in _positions1:
                    if (_p1 + 1) in _positions2:
                        _bigram_hits += 1
                        break
        if _bigram_hits > 0:
            _bigram_ratio = _bigram_hits / max(1, len(_query_toks_list) - 1)
            bigram2_add = 0.6 * _bigram_ratio
    final += bigram2_add

    # 8. Spec add
    spec_add = matcher._spec_score(ctx_specs, ref, has_object_support=obj_overlap or bool(alpha_overlap))
    final += spec_add

    # 9. Spec mult
    spec_mult = matcher._spec_multiplier(desc_specs, ctx_specs, ref)
    final *= spec_mult

    # 10. Discipline
    ref_disc = clean_text(ref["discipline"])
    ref_sheet = clean_text(ref["sheet_name"])
    if ref_disc == "unknown":
        ref_disc = _infer_discipline_from_context(ref["source_file"], ref_sheet)
    disc_mult = 1.0
    if guessed_disc:
        if guessed_disc == ref_disc:
            disc_mult = 1.15
        elif short:
            disc_mult = 0.40
        else:
            disc_mult = 0.70
    final *= disc_mult

    # 11. Sheet routing
    sheet_mult = 1.0
    if sheet_aff and _sa_best_aff > 0:
        aff = sheet_aff.get(ref_sheet, 0.0)
        norm_aff = aff / _sa_best_aff
        if short:
            if norm_aff >= 0.95: sheet_mult = 1.15
            elif norm_aff > _sa_rank_2 * 0.9 and norm_aff >= 0.5: sheet_mult = 1.05
            elif norm_aff < 0.15: sheet_mult = 0.80
            else: sheet_mult = 0.92
        else:
            if norm_aff >= 0.95: sheet_mult = 1.35
            elif norm_aff > _sa_rank_2 * 0.9 and norm_aff >= 0.5: sheet_mult = 1.10
            elif norm_aff < 0.15: sheet_mult = 0.65
            else: sheet_mult = 0.85
    final *= sheet_mult

    # 12. Unit compat
    unit_mult = 1.0
    ref_unit_fam = None
    if boq_unit_fam:
        ref_unit_fam = _infer_ref_unit_family(clean_text(ref["prefixed_description"]))
        if ref_unit_fam:
            if ref_unit_fam == boq_unit_fam:
                unit_mult = 1.15
            else:
                unit_mult = 0.45
    final *= unit_mult

    # 13. Num penalty
    num_pen = 0.0
    if ctx_specs and not alpha_overlap and not obj_overlap:
        num_pen = -0.55
    final += num_pen

    # 14. Subcat
    _pc = clean_text(ref["price_code"])
    _pc_parts = _pc.split()
    subcat_mult = 1.0
    _subcat = None
    if len(_pc_parts) >= 3:
        _subcat = _pc_parts[2]
    if _subcat == "00":
        subcat_mult = 0.60
    final *= subcat_mult

    # 15. Scope
    scope_mult = 1.0
    if expected_scope:
        ref_scope = _extract_scope_letter(_pc)
        if ref_scope:
            if expected_scope in ("E", "F"):
                if ref_scope == expected_scope:
                    scope_mult = 1.25
                elif ref_scope in ("E", "F"):
                    scope_mult = 0.80
            else:
                _scope_disc = _pc_parts[0].upper() if _pc_parts else ""
                if _scope_disc == "C":
                    if ref_scope == expected_scope:
                        scope_mult = 1.25
                    else:
                        scope_mult = 0.85

    final *= scope_mult

    # 16. Rebar routing
    rebar_mult = 1.0
    if _ctx_is_rebar:
        _rpc_fam = " ".join(_pc_parts[:3]) if len(_pc_parts) >= 3 else _pc
        if _rpc_fam.startswith("C 21"):
            rebar_mult = 2.0
        elif _rpc_fam.startswith(("C 31", "C 34", "C 41", "C 11")):
            rebar_mult = 0.35
    final *= rebar_mult

    return {
        "final": round(final, 4),
        "lex": round(lex_score, 4),
        "fuzzy": round(fuzzy_add, 4),
        "bg1": round(bigram1_add, 4),
        "leaf_m": round(leaf_mult, 4),
        "seg_m": round(seg_mult, 4),
        "precast_m": round(precast_pen, 4),
        "tok_add": round(tok_add, 4),
        "bg2": round(bigram2_add, 4),
        "spec_add": round(spec_add, 4),
        "spec_m": round(spec_mult, 4),
        "disc_m": round(disc_mult, 4),
        "sheet_m": round(sheet_mult, 4),
        "unit_m": round(unit_mult, 4),
        "num_pen": round(num_pen, 4),
        "subcat_m": round(subcat_mult, 4),
        "scope_m": round(scope_mult, 4),
        "rebar_m": round(rebar_mult, 4),
        # extra info
        "ref_disc": ref_disc,
        "ref_sheet": ref_sheet,
        "ref_unit_fam": ref_unit_fam,
        "boq_unit_fam": boq_unit_fam,
        "expected_scope": expected_scope,
        "leaf_overlap": sorted(leaf_overlap),
        "alpha_overlap": sorted(alpha_overlap),
        "short": short,
        "ctx_is_rebar": _ctx_is_rebar,
        "ctx_has_precast": _ctx_has_precast,
        "concrete_elem": ref.get("concrete_elem_csv", ""),
        "mpa_csv": ref.get("mpa_csv", ""),
    }


# ═══════════════════════════════════════════════════════════════════════
# MAIN ANALYSIS
# ═══════════════════════════════════════════════════════════════════════
print("Running search for all 167 GT items + computing score breakdowns...")
print("This takes ~6 min ...\n")

results = []
for item in items:
    excel_row = item.get('row_index', -1) + 1
    gt_code = gt.get(excel_row, '')
    if not gt_code:
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
        results.append({
            'row': excel_row, 'gt': gt_code, 'gt_rank': '>20',
            'winner': '???', 'winner_score': 0, 'gt_score': 0,
            'desc': item.get('description', '')[:60],
        })
        continue

    # Find GT rank
    gt_rank = '>20'
    for i, c in enumerate(candidates):
        if c.get('price_code') == gt_code:
            gt_rank = i + 1
            break

    winner_code = candidates[0].get('price_code', '???')

    # Build wq once
    wq = matcher._weighted_query(item_dict)

    # Get ref objects for GT and winner
    gt_ref = None
    winner_ref = None
    for rid, ref in matcher._refs.items():
        pc = ref.get('price_code', '')
        if pc == gt_code and gt_ref is None:
            gt_ref = ref
        if pc == winner_code and winner_ref is None:
            winner_ref = ref
        if gt_ref and winner_ref:
            break

    gt_breakdown = None
    winner_breakdown = None
    if gt_ref:
        gt_breakdown = compute_score_breakdown(matcher, item_dict, gt_ref, wq)
    if winner_ref and winner_code != gt_code:
        winner_breakdown = compute_score_breakdown(matcher, item_dict, winner_ref, wq)

    results.append({
        'row': excel_row,
        'gt': gt_code,
        'gt_rank': gt_rank,
        'winner': winner_code,
        'winner_score': candidates[0].get('score', 0),
        'gt_score': gt_breakdown['final'] if gt_breakdown else 0,
        'desc': item.get('description', '')[:60],
        'parent': item.get('parent', '')[:80],
        'unit': item.get('unit', ''),
        'gt_bd': gt_breakdown,
        'win_bd': winner_breakdown,
        'gt_family': gt_code[:7] if len(gt_code) >= 7 else gt_code,
        'win_family': winner_code[:7] if len(winner_code) >= 7 else winner_code,
    })

# ═══════════════════════════════════════════════════════════════════════
# SUMMARY STATS
# ═══════════════════════════════════════════════════════════════════════
print("=" * 90)
print("GT RANK DISTRIBUTION ANALYSIS")
print("=" * 90)

rank_buckets = Counter()
for r in results:
    rk = r['gt_rank']
    if rk == 1:
        rank_buckets['rank_1'] += 1
    elif isinstance(rk, int) and rk <= 3:
        rank_buckets['rank_2-3'] += 1
    elif isinstance(rk, int) and rk <= 5:
        rank_buckets['rank_4-5'] += 1
    elif isinstance(rk, int) and rk <= 10:
        rank_buckets['rank_6-10'] += 1
    elif isinstance(rk, int) and rk <= 20:
        rank_buckets['rank_11-20'] += 1
    else:
        rank_buckets['not_in_top20'] += 1

print(f"\n  rank 1:      {rank_buckets['rank_1']:3d}  (already exact@1)")
print(f"  rank 2-3:    {rank_buckets['rank_2-3']:3d}  ← closest to promote")
print(f"  rank 4-5:    {rank_buckets['rank_4-5']:3d}")
print(f"  rank 6-10:   {rank_buckets['rank_6-10']:3d}")
print(f"  rank 11-20:  {rank_buckets['rank_11-20']:3d}")
print(f"  not in top20:{rank_buckets['not_in_top20']:3d}")
print(f"  TOTAL:       {len(results):3d}")

# ═══════════════════════════════════════════════════════════════════════
# For items at rank 2-10 (best opportunity), analyze WHY GT loses
# ═══════════════════════════════════════════════════════════════════════
# Score component differences: for each factor, compute (GT_value - Winner_value)
# Negative means GT is worse in that dimension.

MULT_COMPONENTS = ['leaf_m', 'seg_m', 'precast_m', 'spec_m', 'disc_m', 'sheet_m', 'unit_m', 'subcat_m', 'scope_m', 'rebar_m']
ADD_COMPONENTS = ['lex', 'fuzzy', 'bg1', 'tok_add', 'bg2', 'spec_add', 'num_pen']

# Count how often each component hurts the GT
hurt_counts = Counter()  # component → count of items where GT is worse
help_counts = Counter()  # component → count of items where GT is better
hurt_magnitude = defaultdict(float)
help_magnitude = defaultdict(float)

promotable = []  # items at rank 2-20 with both breakdowns available

for r in results:
    rk = r['gt_rank']
    if rk == 1 or rk == '>20':
        continue
    if not r.get('gt_bd') or not r.get('win_bd'):
        continue
    promotable.append(r)
    gt_bd = r['gt_bd']
    win_bd = r['win_bd']

    for comp in MULT_COMPONENTS:
        gt_v = gt_bd[comp]
        win_v = win_bd[comp]
        if gt_v < win_v:
            hurt_counts[comp] += 1
            # For multiplicative: ratio tells us impact
            hurt_magnitude[comp] += (win_v - gt_v)
        elif gt_v > win_v:
            help_counts[comp] += 1
            help_magnitude[comp] += (gt_v - win_v)

    for comp in ADD_COMPONENTS:
        gt_v = gt_bd[comp]
        win_v = win_bd[comp]
        if gt_v < win_v:
            hurt_counts[comp] += 1
            hurt_magnitude[comp] += (win_v - gt_v)
        elif gt_v > win_v:
            help_counts[comp] += 1
            help_magnitude[comp] += (gt_v - win_v)

print(f"\n{'='*90}")
print(f"SCORE COMPONENT IMPACT ANALYSIS ({len(promotable)} items at rank 2-20)")
print(f"{'='*90}")
print(f"\n{'Component':<14s} {'Hurts GT':>10s} {'Avg hurt':>10s} {'Helps GT':>10s} {'Avg help':>10s} {'Net':>8s}")
print("-" * 62)
all_components = MULT_COMPONENTS + ADD_COMPONENTS
for comp in sorted(all_components, key=lambda c: hurt_counts[c], reverse=True):
    h = hurt_counts[comp]
    hp = help_counts[comp]
    avg_h = hurt_magnitude[comp] / max(1, h)
    avg_hp = help_magnitude[comp] / max(1, hp)
    net = hp - h
    marker = " ← FIX" if h > 5 and h > hp else ""
    print(f"  {comp:<12s} {h:>8d}   {avg_h:>8.3f}   {hp:>8d}   {avg_hp:>8.3f}   {net:>+6d}{marker}")

# ═══════════════════════════════════════════════════════════════════════
# DETAILED: rank 2-3 items (easiest to promote to rank 1)
# ═══════════════════════════════════════════════════════════════════════
rank_2_3 = [r for r in promotable if isinstance(r['gt_rank'], int) and r['gt_rank'] <= 3]
rank_2_3.sort(key=lambda x: x['gt_rank'])

print(f"\n{'='*90}")
print(f"DETAILED: {len(rank_2_3)} items at RANK 2-3 (easiest to promote)")
print(f"{'='*90}")

for r in rank_2_3:
    gt_bd = r['gt_bd']
    win_bd = r['win_bd']
    score_gap = win_bd['final'] - gt_bd['final']

    print(f"\n  Row {r['row']:5d} | rank={r['gt_rank']} | gap={score_gap:+.3f}")
    print(f"    desc: {r['desc']}")
    print(f"    parent: {r.get('parent','')}")
    print(f"    unit={r.get('unit','')}  short={gt_bd['short']}")
    print(f"    GT={r['gt']:18s}  score={gt_bd['final']:8.3f}  elem={gt_bd['concrete_elem']}  mpa={gt_bd['mpa_csv']}")
    print(f"    WN={r['winner']:18s}  score={win_bd['final']:8.3f}  elem={win_bd['concrete_elem']}  mpa={win_bd['mpa_csv']}")
    # Show component deltas
    diffs = []
    for comp in MULT_COMPONENTS:
        g, w = gt_bd[comp], win_bd[comp]
        if g != w:
            diffs.append(f"{comp}:GT={g:.3f}/WN={w:.3f}")
    for comp in ADD_COMPONENTS:
        g, w = gt_bd[comp], win_bd[comp]
        if abs(g - w) > 0.001:
            diffs.append(f"{comp}:GT={g:.3f}/WN={w:.3f}")
    print(f"    DIFFS: {' | '.join(diffs)}")

# ═══════════════════════════════════════════════════════════════════════
# DETAILED: rank 4-5 items
# ═══════════════════════════════════════════════════════════════════════
rank_4_5 = [r for r in promotable if isinstance(r['gt_rank'], int) and 4 <= r['gt_rank'] <= 5]
rank_4_5.sort(key=lambda x: x['gt_rank'])

print(f"\n{'='*90}")
print(f"DETAILED: {len(rank_4_5)} items at RANK 4-5")
print(f"{'='*90}")

for r in rank_4_5:
    gt_bd = r['gt_bd']
    win_bd = r['win_bd']
    score_gap = win_bd['final'] - gt_bd['final']

    print(f"\n  Row {r['row']:5d} | rank={r['gt_rank']} | gap={score_gap:+.3f}")
    print(f"    desc: {r['desc']}")
    print(f"    parent: {r.get('parent','')}")
    print(f"    unit={r.get('unit','')}  short={gt_bd['short']}")
    print(f"    GT={r['gt']:18s}  score={gt_bd['final']:8.3f}  elem={gt_bd['concrete_elem']}  mpa={gt_bd['mpa_csv']}")
    print(f"    WN={r['winner']:18s}  score={win_bd['final']:8.3f}  elem={win_bd['concrete_elem']}  mpa={win_bd['mpa_csv']}")
    diffs = []
    for comp in MULT_COMPONENTS:
        g, w = gt_bd[comp], win_bd[comp]
        if g != w:
            diffs.append(f"{comp}:GT={g:.3f}/WN={w:.3f}")
    for comp in ADD_COMPONENTS:
        g, w = gt_bd[comp], win_bd[comp]
        if abs(g - w) > 0.001:
            diffs.append(f"{comp}:GT={g:.3f}/WN={w:.3f}")
    print(f"    DIFFS: {' | '.join(diffs)}")

# ═══════════════════════════════════════════════════════════════════════
# PATTERN ANALYSIS: Group by which component set hurts GT
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'='*90}")
print(f"PATTERN GROUPS: What combination of factors hurts GT?")
print(f"{'='*90}")

pattern_groups = defaultdict(list)
for r in promotable:
    gt_bd = r['gt_bd']
    win_bd = r['win_bd']
    hurting = []
    for comp in MULT_COMPONENTS + ADD_COMPONENTS:
        g = gt_bd[comp]
        w = win_bd[comp]
        if comp in MULT_COMPONENTS:
            if g < w - 0.01:  # GT gets smaller multiplier
                hurting.append(comp)
        else:
            if g < w - 0.1:  # GT gets smaller additive
                hurting.append(comp)
    pattern = "+".join(sorted(hurting)) if hurting else "ALL_EQUAL_OR_GT_BETTER"
    pattern_groups[pattern].append(r)

for pattern, items_list in sorted(pattern_groups.items(), key=lambda kv: -len(kv[1])):
    print(f"\n  [{len(items_list):2d}] {pattern}")
    for r in items_list[:3]:  # show first 3 examples
        print(f"       Row {r['row']:5d}: rank={r['gt_rank']}  GT={r['gt']}  WN={r['winner']}  desc={r['desc'][:50]}")
    if len(items_list) > 3:
        print(f"       ... and {len(items_list)-3} more")

# ═══════════════════════════════════════════════════════════════════════
# FAMILY-LEVEL: How many promotable items per GT family?
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'='*90}")
print("PROMOTABLE ITEMS BY GT FAMILY (rank 2-20)")
print("=" * 90)

family_counts = Counter()
for r in promotable:
    family_counts[r['gt_family']] += 1

for fam, cnt in family_counts.most_common(15):
    # Avg rank for this family
    ranks = [r['gt_rank'] for r in promotable if r['gt_family'] == fam]
    avg_rank = sum(ranks) / len(ranks)
    print(f"  {fam:10s}  {cnt:3d} items  avg_rank={avg_rank:.1f}")

# ═══════════════════════════════════════════════════════════════════════
# SPECIAL: rank 6-10 items grouped by hurt pattern
# ═══════════════════════════════════════════════════════════════════════
rank_6_10 = [r for r in promotable if isinstance(r['gt_rank'], int) and 6 <= r['gt_rank'] <= 10]
print(f"\n{'='*90}")
print(f"RANK 6-10: {len(rank_6_10)} items")
print(f"{'='*90}")

for r in rank_6_10[:15]:
    gt_bd = r['gt_bd']
    win_bd = r['win_bd']
    score_gap = win_bd['final'] - gt_bd['final']
    print(f"\n  Row {r['row']:5d} | rank={r['gt_rank']} | gap={score_gap:+.3f}")
    print(f"    desc: {r['desc']}")
    print(f"    GT={r['gt']:18s}  score={gt_bd['final']:8.3f}")
    print(f"    WN={r['winner']:18s}  score={win_bd['final']:8.3f}")
    diffs = []
    for comp in MULT_COMPONENTS:
        g, w = gt_bd[comp], win_bd[comp]
        if g != w:
            diffs.append(f"{comp}:GT={g:.2f}/WN={w:.2f}")
    for comp in ADD_COMPONENTS:
        g, w = gt_bd[comp], win_bd[comp]
        if abs(g - w) > 0.1:
            diffs.append(f"{comp}:GT={g:.2f}/WN={w:.2f}")
    print(f"    DIFFS: {' | '.join(diffs)}")

print("\n" + "=" * 90)
print("DONE")
