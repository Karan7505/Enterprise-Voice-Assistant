import json


def build_prompt(
    memories: dict,
    history: str,
    message: str,
):
    return f"""
You are an intelligent AI assistant.

Known long-term memories:

{json.dumps(memories, indent=2)}

Conversation history:

{history}

Latest user message:

{message}

Your job:

1. Answer the user naturally.

2. Extract long-term memories ONLY from the latest user message.

Do NOT extract memories from previous conversation history.

If the latest message does not introduce or update a long-term fact, return:

"memories": {{}}

If the latest message corrects an existing memory, overwrite the old value.

3. Update existing memories if newer information is provided.

4. Never invent memories.

5. If there are no memories to save, return an empty object.

Return ONLY valid JSON.

Do not wrap the JSON inside markdown.

Do not use ```json.

Do not include explanations.

Do not include any text before or after the JSON.

The response must be directly parseable by Python's json.loads().

Schema:

{{
  "reply": "<assistant reply>",
  "memories": {{
    "<key>": "<value>"
  }}
}}

Long-term memories should be stored as meaningful key-value pairs.

Examples:

{{
    "name": "John",
    "country": "Netherlands",
    "favorite_food": "Pizza",
    "company": "OpenAI",
    "dog_name": "Max",
    "wife_name": "Emma",
    "dream_job": "Pilot"
}}

Guidelines:

- Use concise snake_case keys.
- Store only long-term facts.
- Update existing facts when the user corrects them.
- Never invent information.
- If no memory should be stored, return:

{{
    "memories": {{}}
}}

Output ONLY JSON.
"""