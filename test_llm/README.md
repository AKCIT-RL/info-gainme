# Avaliação MMLU Geografia

Script simples para avaliar modelos LLM no dataset MMLU de geografia usando a API do vLLM.

## Uso

```bash
# Ativar ambiente virtual
source .venv/bin/activate

# Executar avaliação
python test_llm/evaluate_mmlu_geo.py --model "TinyLlama/TinyLlama-1.1B-Chat-v1.0"

# Com opções customizadas
python test_llm/evaluate_mmlu_geo.py \
    --model "Qwen/Qwen2.5-7B-Instruct" \
    --base-url "http://localhost:8000/v1" \
    --max-samples 100 \
    --temperature 0.0
```

## Parâmetros

- `--model`: Nome do modelo (deve corresponder ao `served_model_name` no vLLM)
- `--base-url`: URL base da API vLLM (padrão: `http://localhost:8000/v1`)
- `--api-key`: Chave da API (padrão: `EMPTY` para vLLM local)
- `--max-samples`: Número máximo de questões para avaliar (padrão: todas)
- `--temperature`: Temperatura para geração (padrão: 0.0)


