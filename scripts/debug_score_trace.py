#!/usr/bin/env python3
"""Score-component tracer for GT ref vs Winner ref.

For each traced row, instruments the reranking loop to show
exactly which scoring components cause the GT to lose to the winner.
"""
import sys, os, re, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.argv = [sys.argv[0], "civil"]

import asyncio
from collections import defaultdict
from local_pricecode_eval import download_db, load_matcher, parse_input, load_ground_truth

download_db()
matcher = asyncio.run(load_matcher())
items, sheet_name, df, header_row_idx, columns = parse_input()
gt = load_ground_truth()

# Rows to trace — remaining miss groups
# C 31 13 within-family: 501 (Upstand→PGA), 505 (Ground floor slabs→EHA), 11249 (blinding→ABE)
# C 21 11 rebar: 577 (Raft slab, parent=steel bar reinforcement, unit=t)
# C 11 13 formwork: 613 (foundations; sides→AAA)
TRACE_ROWS = [501, 505, 577, 613, 11249]

from almabani.pricecode.lexical_search import (
    tokenize, tokenize_normalized, extract_specs, normalize_text,
    clean_text, _unit_family, _infer_ref_unit_family,
    _rapidfuzz_ratio, _infer_discipline_from_context,
    _extract_scope_letter, _parse_compact_code, OBJECT_TOKENS,
    _detect_expected_scope, _detect_mep_prefix
)

print("=" * 80)
print("SCORE COMPONENT TRACE: GT vs WINNER")
print("=" * 80)

for item in items:
    excel_row = item.get('row_index', -1) + 1
    if excel_row not in TRACE_ROWS:
        continue

    gt_code = gt.get(excel_row, '???')
    gt_family = gt_code[:7] if len(gt_code) >= 7 else gt_code

    desc = item.get('description', '')
    parent = item.get('parent', '')
    grandparent = item.get('grandparent', '')
    unit = item.get('unit', '')
    cat_path = item.get('category_path', '')

    item_dict = {
        "description": desc,
        "parent": parent,
        "grandparent": grandparent,
        "unit": unit,
        "item_code": item.get('item_code'),
        "category_path": cat_path,
    }

    print(f"\n{'='*80}")
    print(f"ROW {excel_row}: {desc[:70]}")
    print(f"  parent={parent[:70]}")
    print(f"  grandparent={grandparent[:70]}")
    print(f"  unit={unit}  GT={gt_code}")
    print(f"{'='*80}")

    # Run real search
    candidates = matcher.search_sync(item_dict)
    winner_code = candidates[0].get('price_code', '???') if candidates else '???'
    
    # Get weighted query
    wq = matcher._weighted_query(item_dict)
    qweights, desc_specs, ctx_specs, guessed_disc, distinctive, alpha_dist, short = wq
    
    print(f"  desc_specs: {dict((k,v) for k,v in desc_specs.items() if v)}")
    print(f"  ctx_specs:  {dict((k,v) for k,v in ctx_specs.items() if v)}")
    print(f"  guessed_disc: {guessed_disc}  short={short}")
    
    # Find the GT ref and winner ref IDs
    gt_rid = None
    winner_rid = None
    for rid, ref in matcher._refs.items():
        pc = ref.get('price_code', '')
        if pc == gt_code and gt_rid is None:
            gt_rid = rid
        if pc == winner_code and winner_rid is None:
            winner_rid = rid
    
    if gt_rid is None:
        print(f"  *** GT ref not found in DB! ***")
        continue
    
    # Trace score components for both GT and winner
    core_norm = normalize_text(desc)
    _query_toks_list = tokenize_normalized(core_norm)
    boq_unit_fam = _unit_family(unit or "")
    distinctive_objects = distinctive & OBJECT_TOKENS
    parent_str = parent or ""
    gp_str = grandparent or ""
    _catpath_str = cat_path or ""
    
    _parent_alpha = matcher._alpha_tokens(set(tokenize(parent_str))) if parent_str else set()
    _gp_alpha = matcher._alpha_tokens(set(tokenize(gp_str))) if gp_str else set()
    _cp_alpha = matcher._alpha_tokens(set(tokenize(_catpath_str))) if _catpath_str else set()
    _ctx_alpha = _parent_alpha | _gp_alpha | _cp_alpha
    _ctx_alpha -= alpha_dist
    
    route_toks = alpha_dist | matcher._alpha_tokens(
        set(tokenize(" ; ".join([parent_str, gp_str, _catpath_str])))
    )
    
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
    
    # Scope & MEP prefix detection
    expected_scope = _detect_expected_scope(parent_str, gp_str)
    expected_mep_prefix = _detect_mep_prefix(parent_str, gp_str)
    is_airfield = False  # civil items
    
    for ref_id, label in [(gt_rid, "GT"), (winner_rid, "WINNER")]:
        if ref_id is None:
            continue
        ref = matcher._refs[ref_id]
        
        # Compute TF-IDF score
        ref_toks_all = set(ref.get("_tok_tuple", ())) or set(tokenize_normalized(clean_text(ref["norm_text"])))
        lex_score = 0.0
        for tok, qw in qweights.items():
            if tok in ref_toks_all:
                lex_score += qw * matcher.idf.get(tok, 0.0)
        
        final = lex_score
        components = {"lex_score": round(lex_score, 4)}
        
        leaf_norm = clean_text(ref["norm_leaf"])
        full_norm = clean_text(ref["norm_text"])
        _cached_toks = ref.get("_tok_tuple")
        ref_toks = set(_cached_toks) if _cached_toks else set(tokenize_normalized(full_norm))
        overlap = distinctive & ref_toks
        alpha_overlap = alpha_dist & ref_toks
        obj_overlap = bool(distinctive_objects & ref_toks)
        
        components["overlap"] = sorted(overlap)
        components["alpha_overlap"] = sorted(alpha_overlap)

        # Fuzzy
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
        components["fuzzy_add"] = round(fuzzy_add, 4)

        # Bigram (string-based)
        bigram1_add = 0.0
        if len(_query_toks_list) >= 2:
            _ref_norm_str = full_norm
            _bigram_hits = 0
            for _bi in range(len(_query_toks_list) - 1):
                _bg = _query_toks_list[_bi] + " " + _query_toks_list[_bi + 1]
                if _bg in _ref_norm_str:
                    _bigram_hits += 1
            if _bigram_hits > 0:
                bigram1_add = 0.30 * min(_bigram_hits, 4)
        final += bigram1_add
        components["bigram1_add"] = round(bigram1_add, 4)

        # Leaf overlap
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
        components["leaf_overlap"] = sorted(leaf_overlap)
        components["leaf_ratio"] = round(len(leaf_overlap) / max(1, len(alpha_dist)), 3)
        components["leaf_mult"] = round(leaf_mult, 4)

        # Segment hierarchy matching
        seg_mult = 1.0
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
                    components["seg_overlap"] = sorted(_seg_overlap)
                    components["seg_ratio"] = round(_seg_ratio, 3)
        final *= seg_mult
        components["seg_mult"] = round(seg_mult, 4)

        # Token overlap bonuses
        tok_add = 0.0
        if distinctive:
            tok_add += 1.25 * (len(overlap) / max(1, len(distinctive)))
        if alpha_dist:
            tok_add += 1.1 * (len(alpha_overlap) / max(1, len(alpha_dist)))
        final += tok_add
        components["tok_overlap_add"] = round(tok_add, 4)

        # Bigram2
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
        components["bigram2_add"] = round(bigram2_add, 4)

        # Spec score (additive)
        spec_add = matcher._spec_score(
            ctx_specs, ref, has_object_support=obj_overlap or bool(alpha_overlap)
        )
        final += spec_add
        components["spec_add"] = round(spec_add, 4)

        # Spec multiplier
        spec_mult = matcher._spec_multiplier(desc_specs, ctx_specs, ref)
        final *= spec_mult
        components["spec_mult"] = round(spec_mult, 4)

        # Discipline routing
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
        components["disc_mult"] = round(disc_mult, 4)
        components["ref_disc"] = ref_disc

        # Sheet routing
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
        components["sheet_mult"] = round(sheet_mult, 4)
        components["sheet_name"] = ref_sheet

        # Unit compatibility
        unit_mult = 1.0
        if boq_unit_fam:
            ref_unit_fam = _infer_ref_unit_family(clean_text(ref["prefixed_description"]))
            if ref_unit_fam:
                if ref_unit_fam == boq_unit_fam:
                    unit_mult = 1.15
                else:
                    unit_mult = 0.45
            components["boq_unit"] = boq_unit_fam
            components["ref_unit"] = ref_unit_fam
        final *= unit_mult
        components["unit_mult"] = round(unit_mult, 4)

        # Numeric-only penalty
        num_pen = 0.0
        if ctx_specs and not alpha_overlap and not obj_overlap:
            num_pen = -0.55
        final += num_pen
        components["num_pen"] = round(num_pen, 4)

        # Subcategory "00" penalty
        _pc = clean_text(ref["price_code"])
        _pc_parts = _pc.split()
        subcat_mult = 1.0
        _subcat = None
        if len(_pc_parts) >= 3:
            _subcat = _pc_parts[2]
        if _subcat == "00":
            subcat_mult = 0.60
        final *= subcat_mult
        components["subcat_mult"] = round(subcat_mult, 4)

        # Scope
        scope_mult = 1.0
        if expected_scope:
            ref_scope = _extract_scope_letter(_pc)
            if ref_scope:
                if expected_scope in ("E", "F"):
                    if ref_scope == expected_scope: scope_mult = 1.25
                    elif ref_scope in ("E", "F"): scope_mult = 0.80
                else:
                    _scope_disc = _pc_parts[0].upper() if _pc_parts else ""
                    if _scope_disc == "C":
                        if ref_scope == expected_scope: scope_mult = 1.25
                        else: scope_mult = 0.85
        final *= scope_mult
        components["scope_mult"] = round(scope_mult, 4)
        components["expected_scope"] = expected_scope

        print(f"\n  [{label}: {clean_text(ref['price_code'])}]")
        print(f"    desc: {clean_text(ref['prefixed_description'])[:100]}")
        print(f"    concrete_elem: {ref.get('concrete_elem_csv','')}  mpa: {ref.get('mpa_csv','')}")
        print(f"    --- Score Breakdown ---")
        print(f"    lex_score:      {components['lex_score']:>10.4f}")
        print(f"    fuzzy_add:      {components['fuzzy_add']:>10.4f}")
        print(f"    bigram1_add:    {components['bigram1_add']:>10.4f}")
        print(f"    leaf_mult:      {components['leaf_mult']:>10.4f}  (leaf_overlap={components['leaf_overlap']}, leaf_ratio={components['leaf_ratio']})")
        print(f"    seg_mult:       {components['seg_mult']:>10.4f}  (seg_overlap={components.get('seg_overlap',[])})")
        print(f"    tok_overlap_add:{components['tok_overlap_add']:>10.4f}")
        print(f"    bigram2_add:    {components['bigram2_add']:>10.4f}")
        print(f"    spec_add:       {components['spec_add']:>10.4f}")
        print(f"    spec_mult:      {components['spec_mult']:>10.4f}")
        print(f"    disc_mult:      {components['disc_mult']:>10.4f}  (ref_disc={components['ref_disc']})")
        print(f"    sheet_mult:     {components['sheet_mult']:>10.4f}  (sheet={components['sheet_name']})")
        print(f"    unit_mult:      {components['unit_mult']:>10.4f}  (boq={components.get('boq_unit','')}, ref={components.get('ref_unit','')})")
        print(f"    subcat_mult:    {components['subcat_mult']:>10.4f}")
        print(f"    scope_mult:     {components['scope_mult']:>10.4f}  (expected={components['expected_scope']})")
        print(f"    num_pen:        {components['num_pen']:>10.4f}")
        print(f"    FINAL:          {round(final, 4):>10.4f}")

print("\n" + "=" * 80)
