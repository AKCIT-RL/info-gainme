# Info Gainme

Benchmark para medir ganho de informação em conversas com modelos de linguagem, usando uma arquitetura de três agentes: **Seeker** (faz as perguntas), **Oracle** (responde com informação parcial) e **Pruner** (avalia a qualidade das perguntas).

---

## Scripts de Análise

Após rodar os benchmarks, os scripts abaixo processam os resultados gerados. O fluxo típico é:

```
Benchmark (runs.csv + seeker.json)
       ↓
run_synthesize_traces.sh   →  seeker_traces.json por conversa
       ↓
run_analyze_results.sh     →  summary.json + variance.json + unified_experiments.csv
       ↓
run_analyze_traces.sh      →  reasoning_traces_analysis.json
```

---

### `dgx/run_analyze_results.sh`

**O que faz:** Lê os arquivos `runs.csv` gerados pelos benchmarks e calcula métricas agregadas por experimento: win rate, ganho de informação médio, número de turnos, tokens do Seeker, etc. Salva dois arquivos por experimento (`summary.json` com todas as métricas globais e por cidade, e `variance.json` com foco na variância entre cidades) e ao final gera um `outputs/unified_experiments.csv` consolidando todos os experimentos em uma única tabela.

**Quando usar:** Sempre que novos benchmarks terminarem e você quiser ver os resultados.

**Uso:**
```bash
# Analisa todos os experimentos sob outputs/
./dgx/run_analyze_results.sh

# Analisa um CSV específico
./dgx/run_analyze_results.sh outputs/models/.../runs.csv
```

**Saída:**
- `outputs/models/.../summary.json` — métricas globais e por cidade de cada experimento
- `outputs/models/.../variance.json` — variância do ganho de informação por cidade
- `outputs/unified_experiments.csv` — tabela única com todos os experimentos lado a lado

---

### `dgx/run_synthesize_traces.sh`

**O que faz:** Para cada conversa que o Seeker teve durante o benchmark, usa um LLM para ler o `seeker.json` (histórico bruto de mensagens) e gerar um `seeker_traces.json` estruturado, extraindo: quais opções de perguntas o modelo considerou, o raciocínio por trás da escolha final e um resumo do turno. Só processa experimentos com Chain-of-Thought (CoT). Se um `seeker_traces.json` já existir, pula (idempotente).

**Quando usar:** Antes de `run_analyze_traces.sh`. Necessário para analisar o raciocínio interno do Seeker.

**Uso:**
```bash
# Processa todos os runs.csv (modelo padrão: gpt-4o-mini)
./dgx/run_synthesize_traces.sh

# Processa um runs.csv específico
./dgx/run_synthesize_traces.sh outputs/models/.../runs.csv

# Usa um modelo local em vez do gpt-4o-mini
MODEL=Qwen3-8B BASE_URL=http://localhost:8020/v1 ./dgx/run_synthesize_traces.sh
```

**Saída:**
- `outputs/models/.../conversations/<alvo>/seeker_traces.json` — traces estruturados por conversa

---

### `dgx/run_analyze_traces.sh`

**O que faz:** Lê todos os `seeker_traces.json` gerados pelo script anterior e produz uma análise agregada do comportamento de raciocínio do Seeker: quais perguntas foram mais consideradas globalmente, quais padrões de decisão se repetem, distribuição de turnos por experimento e ranking das top opções e rationales. Só analisa experimentos CoT.

**Quando usar:** Após `run_synthesize_traces.sh`, para entender como o Seeker está raciocinando na escolha de perguntas.

**Uso:**
```bash
# Usa o diretório outputs/ padrão
./dgx/run_analyze_traces.sh

# Usa um diretório de outputs customizado
./dgx/run_analyze_traces.sh /caminho/para/outputs
```

**Saída:**
- `outputs/reasoning_traces_analysis.json` — relatório agregado com top opções, padrões de decisão e estatísticas por experimento

---

### `dgx/run_all_synthesize_traces.sh`

**O que faz:** Pipeline completo em um único comando: roda `analyze_results.py`, depois `generate_unified_csv.py` e por fim `multi_synthesize_reasoning_traces.py --all`. Equivale a rodar os três scripts anteriores em sequência, sem usar grupo compartilhado (`sg sd22`). Útil para processar tudo de uma vez em ambiente pessoal.

**Quando usar:** Quando quiser rodar toda a pipeline de análise de uma vez, fora do contexto de grupo compartilhado.

**Uso:**
```bash
./dgx/run_all_synthesize_traces.sh

# Ou apontando para um CSV específico
./dgx/run_all_synthesize_traces.sh outputs/models/.../runs.csv
```

---

## Scripts de Execução de Benchmarks

### `dgx/run_all_tests.sh`

Submete jobs de benchmark via SLURM para um arquivo `.yaml` ou uma pasta inteira de configs.

```bash
# Uma config específica
./dgx/run_all_tests.sh configs/full/8b/diseases_cot.yaml

# Pasta inteira
./dgx/run_all_tests.sh configs/full/30b/cot/

# Com dependência de outro job SLURM
./dgx/run_all_tests.sh configs/full/30b/cot/ --dep 17427
```

### `dgx/run_vllm_multimodel.sh`

Sobe dois servidores vLLM na mesma GPU (compartilhando VRAM), um para cada modelo configurado. Os servidores ficam expostos nas portas definidas em `configs/servers.yaml`.

---

## Estrutura de Outputs

```
outputs/
├── unified_experiments.csv          ← tabela consolidada de todos os experimentos
├── reasoning_traces_analysis.json   ← análise agregada de reasoning traces
└── models/
    └── s_<seeker>__o_<oracle>__p_<pruner>/
        └── <experimento>/
            ├── runs.csv                          ← resultados brutos
            ├── summary.json                      ← métricas globais e por cidade
            ├── variance.json                     ← variância por cidade
            └── conversations/
                └── <alvo>/
                    ├── seeker.json               ← histórico bruto do Seeker
                    └── seeker_traces.json        ← reasoning traces sintetizados
```
