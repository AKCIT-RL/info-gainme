Synthesize the LLM agent's reasoning trace into a simple JSON format.  

Return only a JSON object with the following fields:
{
  "summary": "A brief summary of the reasoning process",
  "options_considered": "A list of all options the agent considered",
  "questions_considered": "A list of Yes/No questions the agent evaluated. Each item MUST be a fully-formed yes/no question written with proper grammar and ending with a question mark.",
  "decision_rationale": "The reason why the specific option was chosen"
}