"""OracleAgent implementation for answering questions about the target.

The OracleAgent knows the target node and answers questions truthfully
without revealing the target directly. It maintains compliance with
the game rules while providing helpful information.
"""

from __future__ import annotations

from typing import Set

from ..data_types import Answer, Question
from ..graph import Node
from ..prompts import get_oracle_system_prompt
from .llm_adapter import LLMAdapter


class OracleAgent:
    """Agent that answers questions about a known target node.
    
    The Oracle knows the target node and answers questions truthfully
    without revealing the target directly. It maintains compliance with
    the game rules while providing helpful information.
    """

    def __init__(
        self, 
        model: str, 
        llm_adapter: LLMAdapter, 
        target_node_id: str,
        *,
        target_node: Node = None
        ) -> None:
        """Initialize the OracleAgent.
        
        Args:
            model: Model identifier for the LLM.
            llm_adapter: LLMAdapter instance for generating answers.
            target_node_id: ID of the node the Oracle "knows" as the target.
            target_node: Optional target node object with full details.
            
        Raises:
            ValueError: If any parameter is invalid.
        """
        if not model:
            raise ValueError("Model identifier cannot be empty")
        if llm_adapter is None:
            raise ValueError("LLMAdapter cannot be None")
        if not target_node_id:
            raise ValueError("Target node ID cannot be empty")
            
        self._model = model
        self._llm_adapter = llm_adapter
        self._target_node_id = target_node_id
        self._answers_given = 0
        
        # Build system prompt with target information
        system_prompt = self._build_system_prompt_with_target(target_node)
        self._llm_adapter.append_history("system", system_prompt)

    @property
    def model(self) -> str:
        """Get the model identifier."""
        return self._model

    @property
    def target_node_id(self) -> str:
        """Get the target node ID."""
        return self._target_node_id
        
    @property
    def answers_given(self) -> int:
        """Get the number of answers given by this agent."""
        return self._answers_given

    def add_seeker_question(self, question: Question) -> None:
        """Add Seeker's question to conversation history.
        
        Args:
            question: The Seeker's question to add to history.
        """
        # Add only the Seeker's question as user message
        user_message = f"[Seeker] - {question.text}"
        self._llm_adapter.append_history("user", user_message)

    def answer_seeker(self) -> Answer:
        """Generate an answer to the Seeker's question.
        
        Returns:
            Answer object with response text and compliance flag.
            
        Note:
            The Oracle must answer truthfully but cannot reveal the target directly.
            It should respond with simple yes/no answers when possible.
        """
        # Generate answer
        answer_text = self._llm_adapter.generate(max_tokens=50, temperature=0.1)
        
        # Note: LLMAdapter.generate() automatically adds the response to history,
        # so we don't need to manually append it here
        
        # Check compliance (basic heuristic) - get last question from history
        last_question = self._get_last_seeker_question()
        is_compliant = self._check_compliance(last_question, answer_text)
        
        # Track usage
        self._answers_given += 1
        
        return Answer(text=answer_text.strip(), compliant=is_compliant)

    def _build_system_prompt_with_target(self, target_node: Node = None) -> str:
        """Build system prompt with target information included.
        
        Args:
            target_node: The target node object, if available.
            
        Returns:
            Complete system prompt with target details.
        """
        base_prompt = get_oracle_system_prompt()
        
        # Add target information to system prompt
        if target_node:
            attrs_str = ""
            if target_node.attrs:
                attrs_str = f", {', '.join(f'{k}={v}' for k, v in target_node.attrs.items())}"
            
            target_info = f"\n\n## Your Target\n\nID: {target_node.id}\nLabel: {target_node.label}{attrs_str}\n\nThis is the target you know about. Answer all questions truthfully based on this target's properties."
        else:
            target_info = f"\n\n## Your Target\n\nTarget ID: {self._target_node_id}\n\nThis is the target you know about. Answer all questions truthfully based on this target's properties."
        
        return base_prompt + target_info

    def _get_last_seeker_question(self) -> str:
        """Extract the last question from the conversation history.
        
        Returns:
            The text of the last question asked by the Seeker.
        """
        # Look through history for the most recent user message and extract question
        for message in reversed(self._llm_adapter.history):
            if message["role"] == "user" and "[Seeker] -" in message["content"]:
                # Extract just the question part
                content = message["content"]
                if "[Seeker] -" in content:
                    question_part = content.split("[Seeker] -")[1].strip()
                    return question_part
        return "Unknown question"


    def _check_compliance(self, question_text: str, answer_text: str) -> bool:
        """Check if the answer complies with Oracle rules.
        
        Args:
            question_text: The original question.
            answer_text: The generated answer.
            
        Returns:
            True if the answer appears compliant, False otherwise.
            
        Note:
            This is a basic heuristic check. A more sophisticated version
            could use additional LLM calls or rule-based validation.
        """
        answer_lower = answer_text.lower().strip()
        
        # Check for direct target revelation (basic heuristic)
        if self._target_node_id.lower() in answer_lower:
            return False
            
        # Check for common non-compliant patterns
        non_compliant_patterns = [
            "the target is",
            "it is called",
            "the answer is",
            "target:",
        ]
        
        for pattern in non_compliant_patterns:
            if pattern in answer_lower:
                return False
        
        # Simple compliance indicators
        compliant_patterns = [
            "yes", "no", "cannot", "please ask", "i don't", "unclear"
        ]
        
        for pattern in compliant_patterns:
            if pattern in answer_lower:
                return True
                
        # Default to compliant if no clear violations detected
        return True


if __name__ == "__main__":
    """Interactive test case - simulate a conversation between user-as-Seeker and Oracle."""
    
    from os import getenv
    from dotenv import load_dotenv
    
    load_dotenv()
    
    print("🎮 Geographic Guessing Game - Oracle Test")
    print("=" * 50)
    print("You are the Seeker! Ask yes/no questions to find the target.")
    print("The Oracle knows the secret target and will answer truthfully.")
    print("Type 'quit' to exit.\n")
    
    # Create a simple LLMAdapter config for testing
    from .llm_adapter import LLMConfig, LLMAdapter
    
    config = LLMConfig(
        model="gpt-4o-mini",
        api_key=getenv("OPENAI_API_KEY")
    )
    
    llm_adapter = LLMAdapter(config)
    
    # Create a target node for the Oracle
    target_node = Node(
        id="paris", 
        label="Paris",
        attrs={
            "continent": "europe",
            "country": "france", 
            "capital": "true",
            "population": "2161000",
            "coastal": "false"
        }
    )
    
    oracle = OracleAgent(
        model="gpt-4o-mini",
        llm_adapter=llm_adapter,
        target_node_id="paris",
        target_node=target_node
    )
    
    print(f"🎯 Secret target: {target_node.id} ({target_node.label})")
    print(f"📍 Properties: {dict(target_node.attrs)}")
    print("The Oracle knows this secret - try to discover it!\n")
    
    turn = 1
    max_turns = 15
    
    while turn <= max_turns:
        print(f"🤔 Turn {turn}: Ask a yes/no question")
        
        # Get user's question as Seeker
        try:
            user_question = input(f"You (Seeker): ").strip()
        except EOFError:
            print("🚪 Input ended, exiting test.")
            break
        
        if user_question.lower() == "quit":
            print("🚪 Game ended by user.")
            break
            
        if not user_question:
            print("⚠️  Please ask a question (or 'quit' to exit)")
            continue
        
        # Create Question object and add to Oracle's history
        question = Question(text=user_question)
        oracle.add_seeker_question(question)
        
        try:
            # Oracle generates answer
            answer = oracle.answer_seeker()
            
            print(f"🔮 Oracle: {answer.text}")
            print(f"✅ Turn {turn} completed. Compliant: {answer.compliant}")
            
            # Check if user found the target
            if "paris" in user_question.lower() and answer.text.lower().strip() == "yes":
                print("🎉 Congratulations! You found the target!")
                break
                
        except Exception as e:
            print(f"⚠️  Oracle response failed: {e}")
            print("    (This might be due to LLM API issues)")
            break
            
        turn += 1
        print()  # Add spacing between turns
        
    print(f"\n📊 Game Summary:")
    print(f"   - Turns played: {turn-1}")
    print(f"   - Oracle answers given: {oracle.answers_given}")
    print(f"   - Target was: {oracle.target_node_id}")
    print(f"   - Model: {oracle.model}")
    
    # Show conversation history
    print(f"\n💬 Oracle's Conversation History:")
    for i, msg in enumerate(oracle._llm_adapter.history):
        role_emoji = {"system": "⚙️", "user": "🤔", "assistant": "🔮"}
        emoji = role_emoji.get(msg["role"], "❓")
        content = msg["content"]
        if len(content) > 150:
            content = content[:150] + "..."
        print(f"   {emoji} {msg['role']}: {content}")
        
    print("\n🎯 Test completed!")