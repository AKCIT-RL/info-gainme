"""PrunerAgent implementation for LLM-driven candidate pruning.

The PrunerAgent analyzes question-answer pairs and determines which candidates
should be eliminated from the CandidatePool.

Strategy: the LLM returns `keep_labels` (survivors). Pruned = active - keep_labels.
This keeps the output small when many candidates are eliminated. Input uses to_text()
(compact labels only) to keep context usage low.
"""

from __future__ import annotations

import logging

from ..data_types import Answer, PruningResult, Question, PrunerResponse
from ..candidates import CandidatePool
from ..domain.types import DomainConfig, GEO_DOMAIN
from .llm_adapter import LLMAdapter
from ..prompts import get_pruner_system_prompt
from ..utils.utils import llm_final_content

from pydantic import ValidationError

logger = logging.getLogger(__name__)

_PRUNER_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "PrunerResponse",
        "schema": {
            "type": "object",
            "properties": {
                "rationale": {"type": "string"},
                "keep_labels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["keep_labels"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

_VALIDATION_RETRIES = 3


class PrunerAgent:
    """Agent responsible for LLM-driven pruning of the candidate pool."""

    def __init__(
        self,
        llm_adapter: LLMAdapter,
        domain_config: DomainConfig | None = None,
    ) -> None:
        self.llm_adapter = llm_adapter
        self.domain_config = domain_config or GEO_DOMAIN
        self.pruning_count = 0

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
        target_label: str | None = None,
    ) -> PruningResult:
        """Delegate pruning decision to the LLM.

        The LLM returns the smaller of keep/prune sets (mode field).
        Falls back to no pruning on any parse error to avoid crashing the game.

        Args:
            candidate_pool: CandidatePool with current active candidates.
            turn_index: Current turn number (1-based).
            question: Seeker's question.
            answer: Oracle's answer.
            target_label: Label that must NEVER be pruned.

        Returns:
            PruningResult with pruned_labels and rationale.
        """
        system_prompt = get_pruner_system_prompt(
            target_noun=self.domain_config.target_noun,
        )

        candidates_text = candidate_pool.to_text()

        user_prompt = (
            "CANDIDATES:\n" + candidates_text + "\n\n" +
            f"TURN: {turn_index}\n" +
            f"QUESTION: {question.text}\n" +
            f"ANSWER: {answer.text}\n\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        if self.llm_adapter._save_history:
            self.llm_adapter.append_history("user", user_prompt)

        reply = self.llm_adapter.generate(messages=messages, stateless=True,
                                             response_format=_PRUNER_RESPONSE_FORMAT)
        reply = llm_final_content(reply)

        # Parse with retries — model may occasionally produce invalid JSON despite response_format
        last_error: Exception | None = None
        pruning_response: PrunerResponse | None = None
        for attempt in range(_VALIDATION_RETRIES):
            try:
                pruning_response = PrunerResponse.model_validate_json(reply)
                break
            except Exception as e:
                last_error = e
                logger.warning(
                    "Pruner JSON parse error (turn %d, attempt %d/%d): %s | raw=%r",
                    turn_index, attempt + 1, _VALIDATION_RETRIES, e, reply[:300],
                )
                if attempt < _VALIDATION_RETRIES - 1:
                    # Retry: re-generate without appending to history
                    retry_messages = messages + [
                        {"role": "assistant", "content": reply},
                        {"role": "user", "content": 'Your response was not valid JSON. Reply with ONLY a JSON object: {"rationale": "...", "keep_labels": ["Label1", "Label2", ...]}'}
                    ]
                    reply = self.llm_adapter.generate(messages=retry_messages, stateless=True,
                                                       response_format=_PRUNER_RESPONSE_FORMAT)
                    reply = llm_final_content(reply)

        if pruning_response is None:
            logger.warning(
                "Pruner parse failed after %d attempts (turn %d) — skipping pruning: %s",
                _VALIDATION_RETRIES, turn_index, last_error,
            )
            return PruningResult(pruned_labels=set(), rationale=f"parse error after retries: {last_error}")

        keep_labels_raw = pruning_response.keep_labels
        rationale = pruning_response.rationale or ""

        active_labels = {c.label for c in candidate_pool.get_active()}

        # Case-insensitive matching: the LLM may return labels in different casing
        active_labels_lower = {lbl.lower(): lbl for lbl in active_labels}
        keep_labels: set[str] = set()
        unknown_labels: set[str] = set()
        for lbl in keep_labels_raw:
            if lbl in active_labels:
                keep_labels.add(lbl)
            elif lbl.lower() in active_labels_lower:
                keep_labels.add(active_labels_lower[lbl.lower()])
            else:
                unknown_labels.add(lbl)
        logger.info(
            "Pruner matching (turn %d): raw_count=%d, matched=%d, unknown=%d",
            turn_index, len(keep_labels_raw), len(keep_labels), len(unknown_labels),
        )
        if unknown_labels:
            logger.info("Pruner unknown labels (first 5): %s", list(unknown_labels)[:5])
            logger.info("Sample active labels (first 5): %s", list(active_labels)[:5])

        if not keep_labels:
            logger.warning(
                "Pruner returned empty keep_labels after matching (turn %d) — skipping pruning.",
                turn_index,
            )
            return PruningResult(pruned_labels=set(), rationale=f"empty keep_labels: {rationale}")

        pruned_labels = active_labels - keep_labels

        # CRITICAL: never prune the target
        if target_label:
            pruned_labels.discard(target_label)

        self.pruning_count += len(pruned_labels)
        return PruningResult(pruned_labels=pruned_labels, rationale=rationale)
