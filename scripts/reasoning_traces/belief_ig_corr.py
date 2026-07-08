#!/usr/bin/env python3
"""Correlação belief-fidelity (Jaccard) vs IG, em várias granularidades.

Jaccard segue exatamente o padrão de analyze_belief_states.py:
    kept = match_to_pool(kept_candidates, pool_index);  omega = set(omega_labels)
    jaccard = |kept & omega| / |kept | omega|   (definido só quando kept != {})
pool_index = { _norm(label) : label } de Omega_0 (omega_labels do turno 0).

Uso:
    python3 scripts/reasoning_traces/belief_ig_corr.py [caminho/belief_states.jsonl]
    (default: ./outputs/belief_states.jsonl)
"""
import json, re, sys, math
from collections import defaultdict

JSONL = sys.argv[1] if len(sys.argv) > 1 else "./outputs/belief_states.jsonl"

# --- replicado de src/analysis/belief_state_extraction.py (idêntico) ---
def _norm(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().lower())

def match_to_pool(names, pool_index):
    matched = set()
    for name in names:
        canonical = pool_index.get(_norm(name))
        if canonical is not None:
            matched.add(canonical)
    return matched

def jac_turn(belief, omega_labels, pool_index):
    omega = set(omega_labels)
    kept = match_to_pool(belief.get("kept_candidates", []), pool_index)
    if kept:
        inter = len(kept & omega); union = len(kept | omega)
        return inter / union if union else 1.0
    elif not omega:
        return 1.0
    return None  # nomeou nada com Omega_t não-vazio -> "não enumerou", ignora

MODELMAP = {"30b": "Qwen3-30B-A3B-Thinking", "4b_thinking": "Qwen3-4B-Thinking",
            "8b": "Qwen3-8B", "gemma4_31b": "Gemma-4-31B-IT",
            "gemma4_e4b": "Gemma-4-E4B-IT", "nemotron8b": "Nemotron-Cascade-8B"}
ORDER = ["Qwen3-4B-Thinking", "Qwen3-8B", "Qwen3-30B-A3B-Thinking",
         "Gemma-4-E4B-IT", "Gemma-4-31B-IT", "Nemotron-Cascade-8B"]

# --- estatística (Pearson/Spearman, sem scipy) ---
def pearson(xs, ys):
    n = len(xs)
    if n < 3: return None
    mx = sum(xs)/n; my = sum(ys)/n
    sxy = sum((xs[i]-mx)*(ys[i]-my) for i in range(n))
    sx = math.sqrt(sum((x-mx)**2 for x in xs)); sy = math.sqrt(sum((y-my)**2 for y in ys))
    return sxy/(sx*sy) if sx > 0 and sy > 0 else None
def _rank(xs):
    idx = sorted(range(len(xs)), key=lambda i: xs[i]); r = [0.0]*len(xs); i = 0
    while i < len(xs):
        j = i
        while j+1 < len(xs) and xs[idx[j+1]] == xs[idx[i]]: j += 1
        a = sum(range(i, j+1))/(j-i+1)
        for k in range(i, j+1): r[idx[k]] = a
        i = j+1
    return r
def spearman(xs, ys):
    if len(xs) < 3: return None
    return pearson(_rank(xs), _rank(ys))

# --- coleta ---
turns = defaultdict(list)     # (model,mode,scope) -> [(jac, ig, turn_idx)]
conv_jac = defaultdict(list)  # (model,mode,scope) -> [conv-mean jac]
conv_ig = defaultdict(list)   # (model,mode,scope) -> [conv IG/turno]

with open(JSONL) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        r = json.loads(line)
        ed = r["experiment_dir"].rstrip("/").split("/")[-1]
        m = re.match(r"([a-z]+)_\d+_(.+?)_(fo|io|po)_", ed)
        if not m: continue
        dom, tok, mode = m.group(1), m.group(2), m.group(3).upper()
        if tok not in MODELMAP: continue
        model = MODELMAP[tok]; isgeo = dom.startswith("geo")
        tk = r.get("turns", [])
        if not tk: continue
        pool_index = {_norm(l): l for l in (tk[0].get("omega_labels") or [])}
        cjac = []; igs = []
        for i, t in enumerate(tk):
            ig = t.get("info_gain")
            j = jac_turn(t.get("belief", {}), t.get("omega_labels") or [], pool_index)
            if isinstance(ig, (int, float)): igs.append(ig)
            if j is not None and isinstance(ig, (int, float)):
                for scope in (["ALL"] + (["GEO"] if isgeo else [])):
                    turns[(model, mode, scope)].append((j, ig, i))
                cjac.append(j)
        igpt = sum(igs)/len(igs) if igs else None
        for scope in (["ALL"] + (["GEO"] if isgeo else [])):
            if cjac and igpt is not None:
                conv_jac[(model, mode, scope)].append(sum(cjac)/len(cjac))
                conv_ig[(model, mode, scope)].append(igpt)

# --- 1) médias por (model,mode): ALL-domínios vs GEO-only ---
print("=== mean belief_jaccard e IG/turno por (model,mode): ALL vs GEO ===")
print(f'{"model":24s} {"mode":4s} {"J_ALL":>7s} {"J_GEO":>7s} {"IG_ALL":>7s} {"IG_GEO":>7s} {"nGEOt":>6s}')
meanJ = {}; meanIG = {}
for model in ORDER:
    for mode in ["FO", "IO", "PO"]:
        a = turns[(model, mode, "ALL")]; g = turns[(model, mode, "GEO")]
        jA = sum(x[0] for x in a)/len(a) if a else float("nan")
        jG = sum(x[0] for x in g)/len(g) if g else float("nan")
        iA = sum(x[1] for x in a)/len(a) if a else float("nan")
        iG = sum(x[1] for x in g)/len(g) if g else float("nan")
        meanJ[(model, mode, "ALL")] = jA; meanJ[(model, mode, "GEO")] = jG
        meanIG[(model, mode, "ALL")] = iA; meanIG[(model, mode, "GEO")] = iG
        print(f"{model:24s} {mode:4s} {jA:7.3f} {jG:7.3f} {iA:7.3f} {iG:7.3f} {len(g):6d}")

# --- 2) between-model Spearman (n=6), o que está no paper ---
for scope in ["ALL", "GEO"]:
    print(f"\n=== [n=6 between-model] Spearman(meanJ, meanIG)  scope={scope} ===")
    for mode in ["FO", "IO", "PO"]:
        J = [meanJ[(m, mode, scope)] for m in ORDER]
        IG = [meanIG[(m, mode, scope)] for m in ORDER]
        print(f"  {mode}: rho={spearman(J, IG):.3f}")

# --- 3) pooled por-CONVERSA (todos os 6 modelos), robusto ---
for scope in ["ALL", "GEO"]:
    print(f"\n=== [per-conversa pooled] corr(convJac, convIG)  scope={scope} ===")
    for mode in ["FO", "IO", "PO"]:
        xs = []; ys = []
        for m in ORDER:
            xs += conv_jac[(m, mode, scope)]; ys += conv_ig[(m, mode, scope)]
        print(f"  {mode}: Pearson={pearson(xs, ys):.3f} Spearman={spearman(xs, ys):.3f} n={len(xs)}")

# --- 4) pooled TURN-level (todos os turnos) + check de confound turn_index ---
for scope in ["ALL", "GEO"]:
    print(f"\n=== [turn-level pooled] corr(turnJac, turn info_gain)  scope={scope} ===")
    for mode in ["FO", "IO", "PO"]:
        allt = []
        for m in ORDER: allt += turns[(m, mode, scope)]
        js = [x[0] for x in allt]; igs = [x[1] for x in allt]; tp = [x[2] for x in allt]
        print(f"  {mode}: Pearson={pearson(js, igs):.3f} Spearman={spearman(js, igs):.3f} "
              f"n={len(js)} | confound corr(turn_idx,J)={pearson(tp, js):.2f} "
              f"corr(turn_idx,IG)={pearson(tp, igs):.2f}")
