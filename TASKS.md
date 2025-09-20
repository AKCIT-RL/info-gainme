## Backlog de Desenvolvimento (atualizado)

- [concluído] KnowledgeGraph core: `KnowledgeGraph`, `Node`, `Edge` com `get_active_nodes()` e `apply_pruning(pruned_ids)`; estado dos nós podados.
- [concluído] Entropy module: `Entropy.compute(active)` e `Entropy.info_gain(h_before, h_after)` usando entropia de Shannon.
- [concluído] LLMAdapter: integração com OpenAI/vLLM-OpenAI; estado `history`, `append_history`, `reset_history`, `generate`.
- [concluído] SeekerAgent: classes normais (sem dataclass), `question_to_oracle(active, turn)`, `add_oracle_answer_and_pruning(...)`, histórico persistente; papéis: Seeker=assistant, Oracle=user.
- [concluído] OracleAgent: classes normais (sem dataclass), `add_seeker_question(q)`, `answer_seeker()`, alvo no system prompt; papéis: Oracle=assistant, Seeker=user.
- [pausado] PrunerAgent: poda determinística baseada em regras; retornar `PruningResult`.
- [pausado] BenchmarkRunner: loop de turnos, entropia/ganho, critérios de parada, trilha de `TurnState`.
- [pendente] Geo domain loader: carregar grafo geográfico de `data/world_flat.csv`.
- [pendente] Artifacts & metrics I/O: persistir métricas, estados e snapshots em `outputs/`.
- [pendente] Unit tests (básicos): `Entropy`, `KnowledgeGraph.apply_pruning`, `PrunerAgent` (regras), `BenchmarkRunner` (parada).
- [pendente] CLI e Docs: CLI mínima de benchmark e README com quickstart.

## Alterações de arquitetura relevantes
- Removido `AUTO` de `ObservabilityMode` (apenas `FULLY_OBSERVED` e `PARTIALLY_OBSERVED`).
- Cada agente mantém sua própria instância stateful de `LLMAdapter` (histórico persistente por agente).
- Papéis no histórico clarificados por perspectiva:
  - Seeker: `assistant`; Oracle: `user`.
  - Oracle: `assistant`; Seeker: `user`.
- Oracle recebe o target somente no `system` prompt.
- Formatos de mensagem padronizados:
  - Seeker recebe: `[Oracle] - <Yes/No>` e `[Computer] - <contexto>`.
  - Oracle recebe: `[Seeker] - <pergunta>`.

## Dependências e ordem sugerida (ajustada)
1) KnowledgeGraph core → 2) Entropy → 3) LLMAdapter → 4) Seeker/Oracle → (pausado) 5) Pruner → (pausado) 6) BenchmarkRunner → 7) I/O, testes e CLI.

## Critérios de aceite (geral)
- Simplicidade e modularidade; tipagem estática; sem efeitos colaterais em import.
- Reprodutibilidade: caminhos relativos e artefatos em `outputs/`.
- Linters sem novos avisos; docstrings Google style nas APIs públicas.
