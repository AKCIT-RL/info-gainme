classDiagram
    direction LR

    class BenchmarkRunner {
      - KnowledgeGraph graph
      - SeekerAgent seeker
      - OracleAgent oracle
      - PrunerAgent pruner
      - Entropy entropy
      - int max_turns
      - int current_turn
      - float h_threshold
      - List~TurnState~ turns
      + run(): void
    }

    class KnowledgeGraph {
      - Set~Node~ nodes
      - Set~Edge~ edges
      - Set~string~ pruned_ids
      + get_active_nodes(): Set~Node~
      + apply_pruning(pruned: Set~string~): void
    }

    class Node {
      + id: string
      + label: string
      + attrs: Map~string,any~
    }

    class Edge {
      + source_id: string
      + target_id: string
      + relation: string
    }

    class SeekerAgent {
      - string model
      - LLMAdapter llm_adapter
      - ObservabilityMode observability_mode
      + choose_observability(): ObservabilityMode
      + question_to_oracle(active: Set~Node~, turn: int): Question
      + add_oracle_answer_and_pruning(answer: Answer, active: Set~Node~, turn: int): void
    }

    class OracleAgent {
      - string model
      - LLMAdapter llm_adapter
      - string target_node_id
      + add_seeker_question(q: Question): void
      + answer_seeker(): Answer
      }

    class PrunerAgent {
      - LLMAdapter llm
      + prune(active: Set~Node~, q: Question, a: Answer): PruningResult
    }

    class LLMAdapter {
      - List~Message~ history
      + append_history(role: string, text: string): void
      + reset_history(): void
      + generate(...): string
    }

    class PruningResult {
      + pruned_ids: Set~string~
      + rationale: string
    }

    class Entropy {
      + compute(active: Set~Node~): float
      + info_gain(h_before: float, h_after: float): float
    }

    class TurnState {
      + turn_index: int
      + h_before: float
      + h_after: float
      + info_gain: float
      + pruned_count: int
      + question: Question
      + answer: Answer
    }

    class Question {
      + text: string
    }

    class Answer {
      + text: string
      + compliant: bool
    }

    class ObservabilityMode {
      <<enumeration>>
      FULLY_OBSERVED
      PARTIALLY_OBSERVED
    }

    BenchmarkRunner --> KnowledgeGraph
    BenchmarkRunner --> SeekerAgent
    BenchmarkRunner --> OracleAgent
    BenchmarkRunner --> PrunerAgent
    BenchmarkRunner --> Entropy
    BenchmarkRunner --> TurnState

    KnowledgeGraph "1" o-- "*" Node
    KnowledgeGraph "1" o-- "*" Edge

    PrunerAgent --> PruningResult
    PrunerAgent --> LLMAdapter
    SeekerAgent --> LLMAdapter
    OracleAgent --> LLMAdapter
    SeekerAgent --> ObservabilityMode