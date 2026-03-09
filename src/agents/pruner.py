"""PrunerAgent implementation for LLM-driven candidate pruning.

The PrunerAgent analyzes question-answer pairs and determines which candidates
should be eliminated from the CandidatePool.
"""

from __future__ import annotations

from ..data_types import Answer, PruningResult, Question, PrunerResponse
from ..candidates import Candidate, CandidatePool
from ..domain.types import DomainConfig, GEO_DOMAIN
from .llm_adapter import LLMAdapter
from ..prompts import get_pruner_system_prompt
from ..utils.utils import llm_final_content


class PrunerAgent:
    """Agent responsible for LLM-driven pruning of the candidate pool."""

    def __init__(
        self,
        llm_adapter: LLMAdapter,
        domain_config: DomainConfig | None = None,
    ) -> None:
        """Initialize the PrunerAgent.

        Args:
            llm_adapter: LLM adapter for AI-assisted pruning decisions.
            domain_config: Domain config for prompt customization. Defaults to GEO_DOMAIN.
        """
        self.llm_adapter = llm_adapter
        self.domain_config = domain_config or GEO_DOMAIN
        self.pruning_count = 0

        # Add system prompt to history for export (if save_history is enabled)
        if self.llm_adapter._save_history:
            system_prompt = get_pruner_system_prompt(
                target_noun=self.domain_config.target_noun,
            )
            self.llm_adapter.append_history("system", system_prompt)

    def analyze_and_prune(
        self,
        candidate_pool: CandidatePool,
        turn_index: int,
        question: Question,
        answer: Answer,
        *,
        target_label: str = None,
    ) -> PruningResult:
        """Delegate pruning decision to the LLM using candidate pool and turn context.

        The LLM must respond with a strict JSON object:
            {"rationale": "...", "pruned_labels": ["Label One", ...]}

        Args:
            candidate_pool: CandidatePool with current active candidates.
            turn_index: Current turn number (1-based).
            question: Seeker's question.
            answer: Oracle's answer.
            target_label: Label of the target candidate that must NEVER be pruned.

        Returns:
            PruningResult with pruned labels and rationale. Falls back to no
            pruning if parsing fails or the model returns an invalid response.

        Note:
            CRITICAL: The target will NEVER be included in pruned_labels.
        """
        system_prompt = get_pruner_system_prompt(
            target_noun=self.domain_config.target_noun,
        )

        candidates_text = candidate_pool.to_rich_text()

        user_prompt = (
            "CANDIDATES:\n" + candidates_text + "\n\n" +
            f"TURN: {turn_index}\n" +
            f"QUESTION: {question.text}\n" +
            f"ANSWER: {answer.text}\n\n"
        )

        # Build stateless messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Save request to history for export
        if self.llm_adapter._save_history:
            self.llm_adapter.append_history("user", user_prompt)

        # Make stateless call
        reply = self.llm_adapter.generate(
            messages=messages,
            stateless=True,
        )
        reply = llm_final_content(reply)

        try:
            pruning_response = PrunerResponse.model_validate_json(reply)
        except Exception as e:
            raise ValueError(f"Invalid LLM response (non-JSON): {e}. Response: {reply}")

        if pruning_response is None:
            return PruningResult(pruned_labels=set(), rationale="Invalid LLM response (non-JSON)")

        pruned_labels_list = pruning_response.pruned_labels
        rationale = pruning_response.rationale

        # Build active label set for validation
        active_labels = {c.label for c in candidate_pool.get_active()}

        # Validate: only keep labels that are actually active
        candidate_labels = {str(x) for x in pruned_labels_list if isinstance(x, str) and x}
        validated_labels = candidate_labels & active_labels
        invalid_labels = candidate_labels - active_labels
        if invalid_labels:
            rationale = f"Filtered out inactive candidates {invalid_labels}: {rationale}"

        # CRITICAL: Remove target from pruned labels
        if target_label and target_label in validated_labels:
            validated_labels.discard(target_label)

        self.pruning_count += len(validated_labels)
        return PruningResult(pruned_labels=validated_labels, rationale=rationale)
