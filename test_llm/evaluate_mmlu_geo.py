"""Avaliação de LLM no dataset MMLU de Geografia usando LLMAdapter."""

import sys
from pathlib import Path
from typing import Optional
from datasets import load_dataset, concatenate_datasets
from tqdm import tqdm

# Adiciona o diretório raiz ao path para importar módulos do projeto
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agents.llm_adapter import LLMAdapter
from src.agents.llm_config import LLMConfig


def format_question(question: dict) -> str:
    """Formata a questão do MMLU como prompt para o LLM."""
    prompt = f"{question['question']}\n\n"
    prompt += "Opções:\n"
    for i, choice in enumerate(question['choices']):
        prompt += f"{chr(97 + i)}. {choice}\n"
    prompt += "\nResponda apenas com a letra da opção correta (a, b, c ou d)."
    return prompt


def extract_answer(response: str) -> int:
    """Extrai a resposta do LLM (índice 0-3) a partir da resposta em texto."""
    response = response.strip().lower()
    
    # Procura por letras a, b, c, d
    for i, letter in enumerate(['a', 'b', 'c', 'd']):
        if response.startswith(letter) or f" {letter} " in response or response.endswith(letter):
            return i
    
    # Procura por números 0, 1, 2, 3
    for i in range(4):
        if str(i) in response:
            return i
    
    # Se não encontrou, retorna -1 (erro)
    return -1


def evaluate_model(
    model_name: str,
    base_url: str = "http://localhost:8000/v1",
    api_key: str = "EMPTY",
    max_samples: Optional[int] = None,
    # temperature: float = 0.0,
) -> dict:
    """Avalia um modelo no dataset MMLU de geografia.
    
    Args:
        model_name: Nome do modelo (deve corresponder ao served_model_name no vLLM).
        base_url: URL base da API do vLLM.
        api_key: Chave da API (pode ser "EMPTY" para vLLM local).
        max_samples: Número máximo de amostras para avaliar (None = todas).
        temperature: Temperatura para geração.
    
    Returns:
        Dicionário com métricas de avaliação.
    """
    # Carrega o dataset
    print("Carregando dataset MMLU de geografia...")
    mmlu_geo = load_dataset("cais/mmlu", "high_school_geography")
    datasets_list = [
        mmlu_geo["test"],
        mmlu_geo["validation"],
        mmlu_geo["dev"]
    ]
    mmlu_geo_complete = concatenate_datasets(datasets_list)  # type: ignore
    
    if max_samples:
        mmlu_geo_complete = mmlu_geo_complete.select(range(min(max_samples, len(mmlu_geo_complete))))
    
    print(f"Avaliando {len(mmlu_geo_complete)} questões...")
    
    # Configura o LLM
    config = LLMConfig(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        # temperature=temperature,
        max_tokens=1000,  # Resposta curta (apenas letra)
    )
    
    adapter = LLMAdapter(config, save_history=False)
    
    # Avalia cada questão
    correct = 0
    total = 0
    errors = 0
    
    for item in tqdm(mmlu_geo_complete, desc="Avaliando"):
        question = format_question(item)
        correct_answer = item['answer']
        
        try:
            # Usa stateless mode para não precisar de history
            messages = [
                {"role": "system", "content": "Você é um assistente que responde questões de geografia. Responda apenas com a letra da opção correta."},
                {"role": "user", "content": question}
            ]
            
            response = adapter.generate(messages=messages, stateless=True)
            predicted_answer = extract_answer(response)
            
            if predicted_answer == -1:
                errors += 1
            elif predicted_answer == correct_answer:
                correct += 1
            
            total += 1
            
        except Exception as e:
            print(f"\nErro ao processar questão: {e}")
            errors += 1
            total += 1
    
    accuracy = (correct / total) * 100 if total > 0 else 0.0
    
    results = {
        "total": total,
        "correct": correct,
        "errors": errors,
        "accuracy": accuracy,
    }
    
    return results


def main():
    """Função principal."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Avalia LLM no MMLU de geografia")
    parser.add_argument("--model", type=str, required=True, help="Nome do modelo")
    parser.add_argument("--port", type=int, default=8000, help="Porta do vLLM")
    parser.add_argument("--api-key", type=str, default="EMPTY", help="Chave da API")
    parser.add_argument("--max-samples", type=int, default=None, help="Número máximo de amostras")
    # parser.add_argument("--temperature", type=float, default=0.0, help="Temperatura para geração")
    
    args = parser.parse_args()
    
    results = evaluate_model(
        model_name=args.model,
        base_url=f"http://localhost:{args.port}/v1",
        api_key=args.api_key,
        max_samples=args.max_samples,
        # temperature=args.temperature,
    )
    
    print("\n" + "="*50)
    print("RESULTADOS")
    print("="*50)
    print(f"Total de questões: {results['total']}")
    print(f"Corretas: {results['correct']}")
    print(f"Erros/Inválidas: {results['errors']}")
    print(f"Acurácia: {results['accuracy']:.2f}%")
    print("="*50)


if __name__ == "__main__":
    main()

