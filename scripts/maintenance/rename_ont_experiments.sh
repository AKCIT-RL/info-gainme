#!/bin/bash
# Rename experiment directories where the Qwen3-8B oracle ran without thinking.
#
# Background:
#   When vLLM is started without --reasoning-parser qwen3 AND the oracle
#   request uses response_format={"type":"json_schema","strict":true},
#   constrained decoding forces the first generated token to be `{` — leaving
#   no room for a <think> block. The oracle answers without reasoning, while
#   the pruner (no response_format) still thinks. This affected 39 experiments
#   silently. Audit confirmed the first-turn assistant message has no <think>
#   in those 39 cases (check via reasoning_history of any conversation).
#
# This script renames each affected experiment directory by appending
# "_ont" so:
#   - the existing data is preserved next to its peers (audit trail);
#   - re-running the benchmark with the parser-fix in dgx/run_full_benchmark.sh
#     creates a fresh directory under the original (canonical) name.
#
# Usage:
#   bash scripts/maintenance/rename_ont_experiments.sh           # dry-run
#   bash scripts/maintenance/rename_ont_experiments.sh apply     # rename
#
# After applying, regenerate any aggregate CSVs that index by experiment name:
#   python3 scripts/analysis/generate_unified_csv.py
#   python3 scripts/judge_eval/aggregate_judge_results.py

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUTPUTS_DIR="${OUTPUTS_DIR:-${PROJECT_ROOT}/outputs/models}"
SUFFIX="${SUFFIX:-_ont}"
APPLY="${1:-dry}"

PATHS=(
    # Gemma seeker (6) — no_cot variants
    "s_Gemma-3-12B-IT__o_Qwen3-8B__p_Qwen3-8B/diseases_160_gemma12b_fo_no_cot"
    "s_Gemma-3-12B-IT__o_Qwen3-8B__p_Qwen3-8B/diseases_160_gemma12b_po_no_cot"
    "s_Gemma-3-12B-IT__o_Qwen3-8B__p_Qwen3-8B/geo_160_gemma12b_fo_no_cot"
    "s_Gemma-3-12B-IT__o_Qwen3-8B__p_Qwen3-8B/geo_160_gemma12b_po_no_cot"
    "s_Gemma-3-12B-IT__o_Qwen3-8B__p_Qwen3-8B/objects_158_gemma12b_fo_no_cot"
    "s_Gemma-3-12B-IT__o_Qwen3-8B__p_Qwen3-8B/objects_158_gemma12b_po_no_cot"
    # Llama-1B (5)
    "s_Llama-3.2-1B-Instruct__o_Qwen3-8B__p_Qwen3-8B/diseases_160_llama1b_po_no_cot"
    "s_Llama-3.2-1B-Instruct__o_Qwen3-8B__p_Qwen3-8B/geo_160_llama1b_fo_no_cot"
    "s_Llama-3.2-1B-Instruct__o_Qwen3-8B__p_Qwen3-8B/geo_160_llama1b_po_no_cot"
    "s_Llama-3.2-1B-Instruct__o_Qwen3-8B__p_Qwen3-8B/objects_158_llama1b_fo_no_cot"
    "s_Llama-3.2-1B-Instruct__o_Qwen3-8B__p_Qwen3-8B/objects_158_llama1b_po_no_cot"
    # Llama-3B (3)
    "s_Llama-3.2-3B-Instruct__o_Qwen3-8B__p_Qwen3-8B/diseases_160_llama3b_fo_no_cot"
    "s_Llama-3.2-3B-Instruct__o_Qwen3-8B__p_Qwen3-8B/diseases_160_llama3b_po_no_cot"
    "s_Llama-3.2-3B-Instruct__o_Qwen3-8B__p_Qwen3-8B/geo_160_llama3b_fo_no_cot"
    # Nemotron-Cascade-8B-Thinking seeker (1)
    "s_Nemotron-Cascade-8B-Thinking__o_Qwen3-8B__p_Qwen3-8B/geo_160_nemotron8b_po_cot_with_kickoff"
    # Nemotron-Cascade-8B seeker (6) — _with_kickoff variants
    "s_Nemotron-Cascade-8B__o_Qwen3-8B__p_Qwen3-8B/diseases_160_nemotron8b_po_cot_with_kickoff"
    "s_Nemotron-Cascade-8B__o_Qwen3-8B__p_Qwen3-8B/diseases_160_nemotron8b_po_no_cot_with_kickoff"
    "s_Nemotron-Cascade-8B__o_Qwen3-8B__p_Qwen3-8B/geo_160_nemotron8b_po_cot_with_kickoff"
    "s_Nemotron-Cascade-8B__o_Qwen3-8B__p_Qwen3-8B/geo_160_nemotron8b_po_no_cot_with_kickoff"
    "s_Nemotron-Cascade-8B__o_Qwen3-8B__p_Qwen3-8B/objects_158_nemotron8b_po_cot_with_kickoff"
    "s_Nemotron-Cascade-8B__o_Qwen3-8B__p_Qwen3-8B/objects_158_nemotron8b_po_no_cot_with_kickoff"
    # Olmo-Instruct (6)
    "s_Olmo-3.1-32B-Instruct__o_Qwen3-8B__p_Qwen3-8B/diseases_160_olmo3_32b_instruct_fo_no_cot"
    "s_Olmo-3.1-32B-Instruct__o_Qwen3-8B__p_Qwen3-8B/diseases_160_olmo3_32b_instruct_po_no_cot"
    "s_Olmo-3.1-32B-Instruct__o_Qwen3-8B__p_Qwen3-8B/geo_160_olmo3_32b_instruct_fo_no_cot"
    "s_Olmo-3.1-32B-Instruct__o_Qwen3-8B__p_Qwen3-8B/geo_160_olmo3_32b_instruct_po_no_cot"
    "s_Olmo-3.1-32B-Instruct__o_Qwen3-8B__p_Qwen3-8B/objects_158_olmo3_32b_instruct_fo_no_cot"
    "s_Olmo-3.1-32B-Instruct__o_Qwen3-8B__p_Qwen3-8B/objects_158_olmo3_32b_instruct_po_no_cot"
    # Olmo-Think (6)
    "s_Olmo-3.1-32B-Think__o_Qwen3-8B__p_Qwen3-8B/diseases_160_olmo3_32b_think_fo_cot"
    "s_Olmo-3.1-32B-Think__o_Qwen3-8B__p_Qwen3-8B/diseases_160_olmo3_32b_think_po_cot"
    "s_Olmo-3.1-32B-Think__o_Qwen3-8B__p_Qwen3-8B/geo_160_olmo3_32b_think_fo_cot"
    "s_Olmo-3.1-32B-Think__o_Qwen3-8B__p_Qwen3-8B/geo_160_olmo3_32b_think_po_cot"
    "s_Olmo-3.1-32B-Think__o_Qwen3-8B__p_Qwen3-8B/objects_158_olmo3_32b_think_fo_cot"
    "s_Olmo-3.1-32B-Think__o_Qwen3-8B__p_Qwen3-8B/objects_158_olmo3_32b_think_po_cot"
    # Qwen3-0.6B with_kickoff (6)
    "s_Qwen3-0.6B__o_Qwen3-8B__p_Qwen3-8B/diseases_160_0.6b_po_cot_with_kickoff"
    "s_Qwen3-0.6B__o_Qwen3-8B__p_Qwen3-8B/diseases_160_0.6b_po_no_cot_with_kickoff"
    "s_Qwen3-0.6B__o_Qwen3-8B__p_Qwen3-8B/geo_160_0.6b_po_cot_with_kickoff"
    "s_Qwen3-0.6B__o_Qwen3-8B__p_Qwen3-8B/geo_160_0.6b_po_no_cot_with_kickoff"
    "s_Qwen3-0.6B__o_Qwen3-8B__p_Qwen3-8B/objects_158_0.6b_po_cot_with_kickoff"
    "s_Qwen3-0.6B__o_Qwen3-8B__p_Qwen3-8B/objects_158_0.6b_po_no_cot_with_kickoff"
)

cd "${OUTPUTS_DIR}"

echo "Outputs dir: ${OUTPUTS_DIR}"
echo "Suffix:      ${SUFFIX}"
echo "Mode:        ${APPLY}"
echo "Total:       ${#PATHS[@]} experiments"
echo "---"

# Rewrite the experiment_name field embedded in runs.csv / metadata.json /
# summary.json so downstream aggregators (e.g. generate_unified_csv.py) reflect
# the rename. Without this, the CSV "Experimento" column would still show the
# old name even though the directory has the new suffix.
rewrite_experiment_name() {
    local exp_dir=$1 old_name=$2 new_name=$3

    # runs.csv — replace exact-match cell value in the experiment_name column.
    local runs="${exp_dir}/runs.csv"
    if [ -f "${runs}" ]; then
        python3 - "$runs" "$old_name" "$new_name" <<'PYEOF'
import csv, sys
from pathlib import Path
runs, old, new = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
rows = list(csv.DictReader(runs.open()))
if not rows or "experiment_name" not in rows[0]:
    sys.exit(0)
changed = 0
for r in rows:
    if r["experiment_name"] == old:
        r["experiment_name"] = new
        changed += 1
with runs.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
print(f"  runs.csv: {changed} rows updated")
PYEOF
    fi

    # Per-conversation metadata.json + judge_eval.json, and per-experiment
    # summary.json. metadata/summary use "experiment_name"; oracle/pruner judge
    # eval JSONs use "experiment" (no _name).
    python3 - "$exp_dir" "$old_name" "$new_name" <<'PYEOF'
import json, sys
from pathlib import Path
exp_dir, old, new = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
patterns = [
    "conversations/*/metadata.json",
    "conversations/*/oracle_judge_eval.json",
    "conversations/*/pruner_judge_eval.json",
]
files = []
for pat in patterns:
    files.extend(exp_dir.glob(pat))
files.append(exp_dir / "summary.json")

n = 0
for path in files:
    if not path.exists():
        continue
    try:
        d = json.loads(path.read_text())
    except Exception:
        continue
    changed = False
    cfg = d.get("config", {})
    if isinstance(cfg, dict) and cfg.get("experiment_name") == old:
        cfg["experiment_name"] = new; changed = True
    if d.get("experiment_name") == old:
        d["experiment_name"] = new; changed = True
    if d.get("experiment") == old:
        d["experiment"] = new; changed = True
    if changed:
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2))
        n += 1
print(f"  metadata/summary/judge: {n} files updated")
PYEOF
}

ok=0; missing=0; collision=0
for path in "${PATHS[@]}"; do
    new="${path}${SUFFIX}"
    old_name="$(basename "${path}")"
    new_name="${old_name}${SUFFIX}"
    if [ ! -d "${path}" ]; then
        echo "MISSING:    ${path}"
        missing=$((missing + 1))
        continue
    fi
    if [ -e "${new}" ]; then
        echo "COLLISION:  ${new} already exists — skipping"
        collision=$((collision + 1))
        continue
    fi
    if [ "${APPLY}" = "apply" ]; then
        mv "${path}" "${new}"
        echo "RENAMED:    ${path} -> ${new}"
        rewrite_experiment_name "${new}" "${old_name}" "${new_name}"
    else
        echo "WOULD MV:   ${path} -> ${new}"
        echo "  + would rewrite experiment_name '${old_name}' -> '${new_name}'"
        echo "    in runs.csv, conversations/*/metadata.json, summary.json"
    fi
    ok=$((ok + 1))
done

echo "---"
echo "OK: ${ok}  MISSING: ${missing}  COLLISIONS: ${collision}"
[ "${APPLY}" != "apply" ] && echo "(dry-run; rerun with 'apply' to execute)"
