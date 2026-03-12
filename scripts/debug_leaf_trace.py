#!/usr/bin/env python3
"""Deep diagnostic: trace why exact leaf codes are missed.

For a handful of representative BOQ rows, shows:
 1. What specs the search extracted (desc_specs, ctx_specs)
 2. The TF-IDF pool — is the ground-truth ref even in the pool?
 3. Pool ranking of the GT ref vs the winner
 4. Final reranked scores — GT ref vs top candidates
 5. Token overlap analysis: which tokens match/miss
"""
import sys, os, re, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.argv = [sys.argv[0], "civil"]

from collections import defaultdict
import asyncio
from local_pricecode_eval import download_db, load_matcher, parse_input, load_ground_truth

# ── Load everything ─────────────────────────────────────────────────────
download_db()
matcher = asyncio.run(load_matcher())
items, sheet_name, df, header_row_idx, columns = parse_input()
gt = load_ground_truth()

# Rows to investigate — representative of the big miss groups
# C 31 13: Row 457 (Suspended slabs → GT=NGA), Row 445 (Raft slab → GT=CGA), 
#          Row 433 (100mm blinding → GT=ABA)
# C 21 11: Row 577 (Raft slab → GT=CAC, gets C 31 13)
# C 11 13: Row 615 (water tank walls → GT=IAA, gets F 29 00)
TRACE_ROWS = [433, 435, 445, 449, 457, 577, 615]

from almabani.pricecode.lexical_search import tokenize, extract_specs

print("=" * 80)
print("DEEP LEAF-CODE DIAGNOSTIC TRACE")
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
    
    print(f"\n{'─'*80}")
    print(f"ROW {excel_row}: {desc[:70]}")
    print(f"  parent={parent[:60]}")
    print(f"  grandparent={grandparent[:60]}")
    print(f"  category_path={cat_path[:80]}")
    print(f"  unit={unit}  GT={gt_code}")
    print(f"{'─'*80}")
    
    # Build the item dict as the search sees it
    item_dict = {
        "description": desc,
        "parent": parent,
        "grandparent": grandparent,
        "unit": unit,
        "item_code": item.get('item_code'),
        "category_path": cat_path,
    }
    
    # Get weighted query info
    wq = matcher._weighted_query(item_dict)
    qweights, desc_specs, ctx_specs, guessed_disc, distinctive, alpha_dist, short = wq
    
    print(f"\n  [SPECS]")
    print(f"    desc_specs: {dict((k,v) for k,v in desc_specs.items() if v)}")
    print(f"    ctx_specs:  {dict((k,v) for k,v in ctx_specs.items() if v)}")
    print(f"    guessed_disc: {guessed_disc}")
    
    # Show top query tokens
    sorted_tokens = sorted(qweights.items(), key=lambda x: -x[1])[:20]
    print(f"    top tokens: {[(t,round(w,2)) for t,w in sorted_tokens[:15]]}")
    
    # ── TF-IDF pool ──────────────────────────────────────────────────
    # Access the TF-IDF scoring directly
    scored_pool = {}
    for tok, qw in qweights.items():
        postings = matcher._postings.get(tok, [])
        for rid in postings:
            if matcher._valid_ref_ids is not None and rid not in matcher._valid_ref_ids:
                continue
            scored_pool[rid] = scored_pool.get(rid, 0.0) + qw * matcher.idf.get(tok, 0.0)
    
    # Find GT ref IDs
    gt_rids = []
    gt_family_rids = []
    for rid, ref in matcher._refs.items():
        pc = ref.get('price_code', '')
        if pc == gt_code:
            gt_rids.append(rid)
        if pc.startswith(gt_family):
            gt_family_rids.append(rid)
    
    pool_sorted = sorted(scored_pool.items(), key=lambda x: -x[1])
    pool_size = len(pool_sorted)
    
    # Where is GT in the pool?
    gt_pool_ranks = []
    for i, (rid, score) in enumerate(pool_sorted):
        if rid in gt_rids:
            gt_pool_ranks.append((i+1, rid, score, matcher._refs[rid]['price_code']))
    
    print(f"\n  [TF-IDF POOL] size={pool_size}")
    print(f"    GT ref_ids: {gt_rids[:5]} (total {len(gt_rids)} refs with code {gt_code})")
    if gt_pool_ranks:
        for rank, rid, score, pc in gt_pool_ranks[:3]:
            print(f"    GT in pool: rank={rank}/{pool_size} score={score:.4f} code={pc}")
    else:
        print(f"    *** GT NOT IN POOL ***")
        # Check if any family member is in pool
        fam_in_pool = []
        for i, (rid, score) in enumerate(pool_sorted[:5000]):
            if rid in gt_family_rids:
                fam_in_pool.append((i+1, rid, score, matcher._refs[rid]['price_code']))
        if fam_in_pool:
            print(f"    But family refs in pool: {fam_in_pool[:3]}")
    
    # Show top 5 in pool
    print(f"    Top 5 pool:")
    for i, (rid, score) in enumerate(pool_sorted[:5]):
        ref = matcher._refs[rid]
        print(f"      #{i+1}: {ref['price_code']:15s} score={score:.4f}  {ref.get('norm_text','')[:80]}")
    
    # ── Now run actual search to see final rankings ──────────────────
    candidates = matcher.search_sync(item_dict)
    
    print(f"\n  [FINAL CANDIDATES] (top {len(candidates)})")
    gt_found = False
    for i, cand in enumerate(candidates[:10]):
        is_gt = "<<< GT" if cand.get('price_code') == gt_code else ""
        is_fam = "(fam)" if cand.get('price_code', '').startswith(gt_family) else ""
        print(f"    #{i+1}: {cand.get('price_code','???'):15s} score={cand.get('score',0):.4f}  "
              f"{is_gt}{is_fam}  {cand.get('description','')[:70]}")
        if cand.get('price_code') == gt_code:
            gt_found = True
    
    if not gt_found:
        print(f"    *** GT code {gt_code} NOT in final candidates ***")
    
    # ── Token overlap analysis ───────────────────────────────────────
    if gt_rids:
        gt_ref = matcher._refs[gt_rids[0]]
        gt_tokens = set(tokenize(gt_ref.get('norm_text', '')))
        query_tokens = set(qweights.keys())
        overlap = query_tokens & gt_tokens
        only_query = query_tokens - gt_tokens
        only_gt = gt_tokens - query_tokens
        print(f"\n  [TOKEN OVERLAP with GT ref]")
        print(f"    overlap ({len(overlap)}):    {sorted(overlap)[:20]}")
        print(f"    only in query ({len(only_query)}): {sorted(only_query)[:15]}")
        print(f"    only in GT ({len(only_gt)}):   {sorted(only_gt)[:15]}")
    
    # If the winner is wrong family, show token overlap with winner
    if candidates and candidates[0].get('price_code', '').startswith(gt_family) == False:
        winner_ref = None
        for rid, ref in matcher._refs.items():
            if ref.get('price_code') == candidates[0].get('price_code'):
                winner_ref = ref
                break
        if winner_ref:
            w_tokens = set(tokenize(winner_ref.get('norm_text', '')))
            print(f"\n  [TOKEN OVERLAP with WINNER ({candidates[0].get('price_code')})]")
            print(f"    overlap ({len(query_tokens & w_tokens)}): {sorted(query_tokens & w_tokens)[:20]}")

print("\n" + "=" * 80)
print("DONE")
