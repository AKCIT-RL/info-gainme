# Configs afetados por erros de validação do Oracle

Gerado a partir de `outputs/oracle_validation.csv` — saída do script
`scripts/validate_oracle_answers.py` rodado no h100n2.

**99 configs únicos afetados** | **68 experimentos** | **11789 erros totais** (contagem agregada; ablações que compartilham saída somam o mesmo erro)

Erros detectados: `invalid_json`, `no_yes_no_prefix`, `target_leak`. Warnings: `yes_no_with_extra_text`.

## Resumo por grupo

| Grupo | Configs | Erros |
|---|---:|---:|
| `0.6b` | 12 | 9475 |
| `235b` | 1 | 1 |
| `30b` | 5 | 21 |
| `4b` | 10 | 122 |
| `8b` | 14 | 241 |
| `ablation_pruner_oracle/gemma_12b/4b_instruct` | 5 | 13 |
| `ablation_pruner_oracle/gemma_12b/4b_thinking` | 5 | 109 |
| `ablation_pruner_oracle/gemma_12b/8b` | 12 | 236 |
| `ablation_pruner_oracle/nemotron_8b/4b_instruct` | 5 | 13 |
| `ablation_pruner_oracle/nemotron_8b/4b_thinking` | 5 | 109 |
| `ablation_pruner_oracle/nemotron_8b/8b` | 12 | 236 |
| `nemotron-8b` | 1 | 5 |
| `olmo3-7b` | 12 | 1912 |

## Lista completa por grupo

### 0.6b

| Erros | Warnings | Config |
|---:|---:|---|
| 1698 | 185 | `configs/full/0.6b/diseases_160_0.6b_po_cot.yaml` |
| 1689 | 119 | `configs/full/0.6b/diseases_160_0.6b_fo_cot.yaml` |
| 1141 | 258 | `configs/full/0.6b/diseases_160_0.6b_fo_no_cot.yaml` |
| 845 | 162 | `configs/full/0.6b/diseases_160_0.6b_po_no_cot.yaml` |
| 819 | 279 | `configs/full/0.6b/objects_158_0.6b_po_no_cot.yaml` |
| 700 | 177 | `configs/full/0.6b/objects_158_0.6b_fo_no_cot.yaml` |
| 676 | 29 | `configs/full/0.6b/geo_160_0.6b_po_cot.yaml` |
| 589 | 200 | `configs/full/0.6b/geo_160_0.6b_po_no_cot.yaml` |
| 463 | 27 | `configs/full/0.6b/geo_160_0.6b_fo_cot.yaml` |
| 351 | 114 | `configs/full/0.6b/geo_160_0.6b_fo_no_cot.yaml` |
| 306 | 30 | `configs/full/0.6b/objects_158_0.6b_po_cot.yaml` |
| 198 | 43 | `configs/full/0.6b/objects_158_0.6b_fo_cot.yaml` |

### 235b

| Erros | Warnings | Config |
|---:|---:|---|
| 1 | 0 | `configs/full/235b/no_cot/objects_158_235b_po_no_cot.yaml` |

### 30b

| Erros | Warnings | Config |
|---:|---:|---|
| 8 | 0 | `configs/full/30b/no_cot/objects_158_30b_po_no_cot.yaml` |
| 5 | 0 | `configs/full/30b/cot/objects_158_30b_po_cot.yaml` |
| 5 | 0 | `configs/full/30b/with_prior/no_cot/geo_160_30b_fo_no_cot_with_prior.yaml` |
| 2 | 0 | `configs/full/30b/with_prior/cot/geo_160_30b_fo_cot_with_prior.yaml` |
| 1 | 0 | `configs/full/30b/no_cot/geo_160_30b_fo_no_cot.yaml` |

### 4b

| Erros | Warnings | Config |
|---:|---:|---|
| 53 | 7 | `configs/full/4b/cot/diseases_160_4b_thinking_po_cot.yaml` |
| 42 | 1 | `configs/full/4b/cot/objects_158_4b_thinking_po_cot.yaml` |
| 8 | 0 | `configs/full/4b/cot/diseases_160_4b_thinking_fo_cot.yaml` |
| 8 | 2 | `configs/full/4b/no_cot/objects_158_4b_instruct_po_no_cot.yaml` |
| 4 | 0 | `configs/full/4b/cot/geo_160_4b_thinking_fo_cot.yaml` |
| 2 | 0 | `configs/full/4b/cot/geo_160_4b_thinking_po_cot.yaml` |
| 2 | 3 | `configs/full/4b/no_cot/geo_160_4b_instruct_po_no_cot.yaml` |
| 1 | 0 | `configs/full/4b/no_cot/diseases_160_4b_instruct_fo_no_cot.yaml` |
| 1 | 0 | `configs/full/4b/no_cot/diseases_160_4b_instruct_po_no_cot.yaml` |
| 1 | 0 | `configs/full/4b/no_cot/geo_160_4b_instruct_fo_no_cot.yaml` |

### 8b

| Erros | Warnings | Config |
|---:|---:|---|
| 87 | 11 | `configs/full/8b/objects_158_8b_po_no_cot.yaml` |
| 37 | 26 | `configs/full/8b/diseases_160_8b_po_cot.yaml` |
| 35 | 4 | `configs/full/8b/objects_158_8b_po_cot.yaml` |
| 31 | 8 | `configs/full/8b/diseases_160_8b_po_no_cot.yaml` |
| 14 | 3 | `configs/full/8b/geo_160_8b_po_no_cot.yaml` |
| 10 | 3 | `configs/full/8b/geo_160_8b_po_cot.yaml` |
| 5 | 0 | `configs/full/8b/diseases_160_8b_fo_cot.yaml` |
| 5 | 1 | `configs/full/8b/diseases_160_8b_fo_no_cot.yaml` |
| 5 | 0 | `configs/full/8b/geo_160_8b_fo_cot.yaml` |
| 4 | 0 | `configs/full/8b/objects_158_8b_fo_cot.yaml` |
| 3 | 1 | `configs/full/8b/with_prior/geo_160_8b_po_cot_with_prior.yaml` |
| 2 | 0 | `configs/full/8b/objects_158_8b_fo_no_cot.yaml` |
| 2 | 0 | `configs/full/8b/with_prior/geo_160_8b_fo_cot_with_prior.yaml` |
| 1 | 0 | `configs/full/8b/geo_160_8b_fo_no_cot.yaml` |

### ablation_pruner_oracle/gemma_12b/4b_instruct

| Erros | Warnings | Config |
|---:|---:|---|
| 8 | 2 | `configs/full/ablation_pruner_oracle/gemma_12b/4b_instruct/objects_158_4b_instruct_po_no_cot.yaml` |
| 2 | 3 | `configs/full/ablation_pruner_oracle/gemma_12b/4b_instruct/geo_160_4b_instruct_po_no_cot.yaml` |
| 1 | 0 | `configs/full/ablation_pruner_oracle/gemma_12b/4b_instruct/diseases_160_4b_instruct_fo_no_cot.yaml` |
| 1 | 0 | `configs/full/ablation_pruner_oracle/gemma_12b/4b_instruct/diseases_160_4b_instruct_po_no_cot.yaml` |
| 1 | 0 | `configs/full/ablation_pruner_oracle/gemma_12b/4b_instruct/geo_160_4b_instruct_fo_no_cot.yaml` |

### ablation_pruner_oracle/gemma_12b/4b_thinking

| Erros | Warnings | Config |
|---:|---:|---|
| 53 | 7 | `configs/full/ablation_pruner_oracle/gemma_12b/4b_thinking/diseases_160_4b_thinking_po_cot.yaml` |
| 42 | 1 | `configs/full/ablation_pruner_oracle/gemma_12b/4b_thinking/objects_158_4b_thinking_po_cot.yaml` |
| 8 | 0 | `configs/full/ablation_pruner_oracle/gemma_12b/4b_thinking/diseases_160_4b_thinking_fo_cot.yaml` |
| 4 | 0 | `configs/full/ablation_pruner_oracle/gemma_12b/4b_thinking/geo_160_4b_thinking_fo_cot.yaml` |
| 2 | 0 | `configs/full/ablation_pruner_oracle/gemma_12b/4b_thinking/geo_160_4b_thinking_po_cot.yaml` |

### ablation_pruner_oracle/gemma_12b/8b

| Erros | Warnings | Config |
|---:|---:|---|
| 87 | 11 | `configs/full/ablation_pruner_oracle/gemma_12b/8b/objects_158_8b_po_no_cot.yaml` |
| 37 | 26 | `configs/full/ablation_pruner_oracle/gemma_12b/8b/diseases_160_8b_po_cot.yaml` |
| 35 | 4 | `configs/full/ablation_pruner_oracle/gemma_12b/8b/objects_158_8b_po_cot.yaml` |
| 31 | 8 | `configs/full/ablation_pruner_oracle/gemma_12b/8b/diseases_160_8b_po_no_cot.yaml` |
| 14 | 3 | `configs/full/ablation_pruner_oracle/gemma_12b/8b/geo_160_8b_po_no_cot.yaml` |
| 10 | 3 | `configs/full/ablation_pruner_oracle/gemma_12b/8b/geo_160_8b_po_cot.yaml` |
| 5 | 0 | `configs/full/ablation_pruner_oracle/gemma_12b/8b/diseases_160_8b_fo_cot.yaml` |
| 5 | 1 | `configs/full/ablation_pruner_oracle/gemma_12b/8b/diseases_160_8b_fo_no_cot.yaml` |
| 5 | 0 | `configs/full/ablation_pruner_oracle/gemma_12b/8b/geo_160_8b_fo_cot.yaml` |
| 4 | 0 | `configs/full/ablation_pruner_oracle/gemma_12b/8b/objects_158_8b_fo_cot.yaml` |
| 2 | 0 | `configs/full/ablation_pruner_oracle/gemma_12b/8b/objects_158_8b_fo_no_cot.yaml` |
| 1 | 0 | `configs/full/ablation_pruner_oracle/gemma_12b/8b/geo_160_8b_fo_no_cot.yaml` |

### ablation_pruner_oracle/nemotron_8b/4b_instruct

| Erros | Warnings | Config |
|---:|---:|---|
| 8 | 2 | `configs/full/ablation_pruner_oracle/nemotron_8b/4b_instruct/objects_158_4b_instruct_po_no_cot.yaml` |
| 2 | 3 | `configs/full/ablation_pruner_oracle/nemotron_8b/4b_instruct/geo_160_4b_instruct_po_no_cot.yaml` |
| 1 | 0 | `configs/full/ablation_pruner_oracle/nemotron_8b/4b_instruct/diseases_160_4b_instruct_fo_no_cot.yaml` |
| 1 | 0 | `configs/full/ablation_pruner_oracle/nemotron_8b/4b_instruct/diseases_160_4b_instruct_po_no_cot.yaml` |
| 1 | 0 | `configs/full/ablation_pruner_oracle/nemotron_8b/4b_instruct/geo_160_4b_instruct_fo_no_cot.yaml` |

### ablation_pruner_oracle/nemotron_8b/4b_thinking

| Erros | Warnings | Config |
|---:|---:|---|
| 53 | 7 | `configs/full/ablation_pruner_oracle/nemotron_8b/4b_thinking/diseases_160_4b_thinking_po_cot.yaml` |
| 42 | 1 | `configs/full/ablation_pruner_oracle/nemotron_8b/4b_thinking/objects_158_4b_thinking_po_cot.yaml` |
| 8 | 0 | `configs/full/ablation_pruner_oracle/nemotron_8b/4b_thinking/diseases_160_4b_thinking_fo_cot.yaml` |
| 4 | 0 | `configs/full/ablation_pruner_oracle/nemotron_8b/4b_thinking/geo_160_4b_thinking_fo_cot.yaml` |
| 2 | 0 | `configs/full/ablation_pruner_oracle/nemotron_8b/4b_thinking/geo_160_4b_thinking_po_cot.yaml` |

### ablation_pruner_oracle/nemotron_8b/8b

| Erros | Warnings | Config |
|---:|---:|---|
| 87 | 11 | `configs/full/ablation_pruner_oracle/nemotron_8b/8b/objects_158_8b_po_no_cot.yaml` |
| 37 | 26 | `configs/full/ablation_pruner_oracle/nemotron_8b/8b/diseases_160_8b_po_cot.yaml` |
| 35 | 4 | `configs/full/ablation_pruner_oracle/nemotron_8b/8b/objects_158_8b_po_cot.yaml` |
| 31 | 8 | `configs/full/ablation_pruner_oracle/nemotron_8b/8b/diseases_160_8b_po_no_cot.yaml` |
| 14 | 3 | `configs/full/ablation_pruner_oracle/nemotron_8b/8b/geo_160_8b_po_no_cot.yaml` |
| 10 | 3 | `configs/full/ablation_pruner_oracle/nemotron_8b/8b/geo_160_8b_po_cot.yaml` |
| 5 | 0 | `configs/full/ablation_pruner_oracle/nemotron_8b/8b/diseases_160_8b_fo_cot.yaml` |
| 5 | 1 | `configs/full/ablation_pruner_oracle/nemotron_8b/8b/diseases_160_8b_fo_no_cot.yaml` |
| 5 | 0 | `configs/full/ablation_pruner_oracle/nemotron_8b/8b/geo_160_8b_fo_cot.yaml` |
| 4 | 0 | `configs/full/ablation_pruner_oracle/nemotron_8b/8b/objects_158_8b_fo_cot.yaml` |
| 2 | 0 | `configs/full/ablation_pruner_oracle/nemotron_8b/8b/objects_158_8b_fo_no_cot.yaml` |
| 1 | 0 | `configs/full/ablation_pruner_oracle/nemotron_8b/8b/geo_160_8b_fo_no_cot.yaml` |

### nemotron-8b

| Erros | Warnings | Config |
|---:|---:|---|
| 5 | 0 | `configs/full/nemotron-8b/no_cot/diseases_160_nemotron8b_fo_no_cot.yaml` |

### olmo3-7b

| Erros | Warnings | Config |
|---:|---:|---|
| 568 | 62 | `configs/full/olmo3-7b/no_cot/diseases_160_olmo3_7b_instruct_po_no_cot.yaml` |
| 447 | 32 | `configs/full/olmo3-7b/no_cot/geo_160_olmo3_7b_instruct_po_no_cot.yaml` |
| 283 | 33 | `configs/full/olmo3-7b/no_cot/objects_158_olmo3_7b_instruct_po_no_cot.yaml` |
| 151 | 22 | `configs/full/olmo3-7b/no_cot/diseases_160_olmo3_7b_instruct_fo_no_cot.yaml` |
| 117 | 1 | `configs/full/olmo3-7b/cot/geo_160_olmo3_7b_think_po_cot.yaml` |
| 87 | 1 | `configs/full/olmo3-7b/cot/diseases_160_olmo3_7b_think_fo_cot.yaml` |
| 73 | 1 | `configs/full/olmo3-7b/cot/objects_158_olmo3_7b_think_fo_cot.yaml` |
| 64 | 1 | `configs/full/olmo3-7b/cot/objects_158_olmo3_7b_think_po_cot.yaml` |
| 57 | 23 | `configs/full/olmo3-7b/cot/diseases_160_olmo3_7b_think_po_cot.yaml` |
| 46 | 0 | `configs/full/olmo3-7b/cot/geo_160_olmo3_7b_think_fo_cot.yaml` |
| 13 | 2 | `configs/full/olmo3-7b/no_cot/geo_160_olmo3_7b_instruct_fo_no_cot.yaml` |
| 6 | 1 | `configs/full/olmo3-7b/no_cot/objects_158_olmo3_7b_instruct_fo_no_cot.yaml` |

## Experimentos sem config yaml correspondente

| Erros | Experimento |
|---:|---|
| 12 | `outputs/models/s_Qwen3-4B-Thinking-2507__o_Gemma-3-12B-IT__p_Gemma-3-12B-IT/diseases_160_4b_thinking_fo_no_cot` |
