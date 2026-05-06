# local/

Scripts wrappers para rodar pipelines de análise **na máquina local**, em screen,
usando o `.venv` do projeto. Equivalentes locais ao que `dgx/` faz via Singularity/SLURM.

| Script | O que faz | Saída |
|---|---|---|
| `classify_questions.sh` | `classify_questions.py` + `flatten_question_classifications.py` | `outputs/question_classifications.{jsonl,csv}` |
| `synthesize_traces.sh` | `synthesize_traces.py` + `analyze_traces.py` | `outputs/seeker_traces.jsonl` + `reasoning_traces_analysis.json` |

Todos:
- detectam se já estão dentro de um screen — se não, criam `screen -dmS <nome>` e re-executam dentro;
- são retomáveis (lêem o JSONL existente e pulam o que já foi feito);
- aceitam variáveis `BASE_URL`, `API_KEY`, `MODEL`, etc. para apontar para outro endpoint.

## Uso

```bash
# Classificação (744 conversas locais)
bash local/classify_questions.sh
bash local/classify_questions.sh --per-stratum 30   # amostra para testar
screen -r classify

# Síntese de traces (só CoT — pastas locais podem estar vazias, sincronizar antes)
bash local/synthesize_traces.sh
bash local/synthesize_traces.sh --runs outputs/models/.../runs.csv
screen -r traces
```

## Endpoint padrão

Ambos apontam para o vLLM externo `http://200.137.197.131:60002/v1` rodando `nvidia/Kimi-K2.5-NVFP4`. Para usar outro:

```bash
BASE_URL=http://localhost:9200/v1 MODEL=Qwen3-8B bash local/classify_questions.sh
```
