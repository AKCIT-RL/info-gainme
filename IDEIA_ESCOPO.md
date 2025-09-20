## Ideia e Escopo do Projeto

### Ideia
Benchmark para avaliar a capacidade de modelos de linguagem (LLMs) em buscar informações de forma proativa (information gathering), reduzindo ambiguidade por meio de perguntas de esclarecimento. A avaliação usa Teoria da Informação (entropia e ganho de informação) como métrica objetiva.

### Problema
- Falta de estruturação explícita/hierárquica do conhecimento e da busca.
- Benchmarks open-ended dependem do conhecimento prévio da LLM; nosso universo é limitado e controlável.

### Solução (Framework)
- Grafo de conhecimento limitado ao domínio (universo controlado).
- LLM atua como um agente curioso que faz perguntas; respostas podam o espaço de busca.
- Métrica principal: ganho de informação por turno (Δ entropia).

### Domínio inicial
- Geográfico, usando o mesmo dataset/base de `world_graph_flat.ipynb`.
- Nós: `region` → `subregion` → `country` → `state` → `city` (arestas hierárquicas direcionadas).

### Agentes
- SeekerAgent: faz 1 pergunta/turno; pode operar com visibilidade variável.
- OracleAgent: conhece o nó objetivo (mora na cidade alvo); responde 1 vez/turno; nunca revela o alvo diretamente.
- PrunerAgent: decide podas com base em pergunta+resposta, reduzindo o conjunto de nós ativos.

### Observabilidade
- `ObservabilityMode`: `FULLY_OBSERVED`, `PARTIALLY_OBSERVED`, `AUTO`.
- No modo `AUTO`, a própria LLM decide (FO vs PO) conforme estratégia.

### Métricas
- Entropia de Shannon sobre o conjunto de nós ativos.
- Ganho de informação por turno: `infoGain = H(before) - H(after)`.
- Curvas de H(t) e acumulado de ganho; número de turnos até acerto/estouro.

### Loop do turno
1. Estado atual: grafo com n−p nós ativos (após podas anteriores).
2. Seeker faz uma pergunta ao Oracle (no máximo 1/turno).
3. Oracle responde sem revelar o alvo.
4. Pruner analisa pergunta+resposta e poda nós; atualizar métricas (H e ΔH).

### Escopo MVP
- Construir grafo geográfico amostrado (50–300 cidades) a partir de `data/world_flat.csv`.
- Implementar cálculo de entropia e ganho de informação.
- Implementar `LLMAdapter` para abstrair provedores.
- Implementar agentes: `SeekerAgent` (FO/PO/AUTO), `OracleAgent` (alvo conhecido), `PrunerAgent` (baseline determinístico por regras).
- Implementar `BenchmarkRunner` (loop, critérios de parada: acerto ou `maxTurns`).
- Persistir métricas, estados de turno e snapshots em `outputs/`.

### Critérios de sucesso (MVP)
- Reprodutibilidade: mesmos artefatos sob mesmas sementes/dataset (I/O relativa e env ativado).
- Métricas claras: H(t), ΔH por turno, tempo/turno, turnos até acerto.
- Simplicidade: APIs pequenas, tipadas, sem dependências desnecessárias.

### Extensões futuras
- Outros “language games”: Guess my City, Twenty Questions.
- Domínios adicionais (ex.: médico) mantendo a mesma métrica.
- Pruner semântico/LLM, políticas de pergunta mais sofisticadas, e comparação entre modelos.

### Execução e reprodutibilidade
- Ative o ambiente: `conda activate ./env || source env/bin/activate`.
- Use caminhos relativos; artefatos em `outputs/`.

