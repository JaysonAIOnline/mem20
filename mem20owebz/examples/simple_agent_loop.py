"""
Minimal ReAct-style agent loop for use with Jayson / LiteLLM bridge.
"""
import json
from typing import Callable, Any


def run_agent(
    user_query: str,
    llm_call: Callable[[list], dict],
    tools: dict[str, Callable],
    max_steps: int = 8,
) -> str:
    """
    llm_call(messages) must return a dict like:
    {
      "content": "...",
      "tool_calls": [ {"id": "...", "function": {"name": "...", "arguments": "{...}"}} ]
    }
    """
    messages = [{"role": "user", "content": user_query}]

    for _ in range(max_steps):
        response = llm_call(messages)
        tool_calls = response.get("tool_calls") or []

        if not tool_calls:
            return response.get("content") or ""

        messages.append({
            "role": "assistant",
            "content": response.get("content"),
            "tool_calls": tool_calls,
        })

        for call in tool_calls:
            name = call["function"]["name"]
            raw_args = call["function"].get("arguments", "{}")
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            result = tools[name](**args) if name in tools else f"Unknown tool: {name}"
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", name),
                "content": str(result),
            })

    return "Reached max steps without a final answer."


# --- Example usage with the Jayson bridge ---
if __name__ == "__main__":
    from openai import OpenAI

    client = OpenAI(
        base_url="http://localhost:4000/v1",
        api_key="jayson-bridge-secret-change-me",
    )

    def llm_call(messages):
        resp = client.chat.completions.create(
            model="fast",
            messages=messages,
            tools=[{
                "type": "function",
                "function": {
                    "name": "add",
                    "description": "Add two numbers",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number"},
                            "b": {"type": "number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            }],
        )
        msg = resp.choices[0].message
        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        return {"content": msg.content, "tool_calls": tool_calls}

    tools = {
        "add": lambda a, b: a + b,
    }

    answer = run_agent("What is 17 + 25?", llm_call, tools)
    print(answer)
