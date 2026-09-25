# AutoGen / AG2 + Jayson — Installation & Connection

## 1. Install
```bash
pip install autogen-agentchat autogen-ext
# or follow current official AG2 / AutoGen docs
```

## 2. Connect
Same pattern as mem20 crews and mem20 graph substrate:

- Build your multi-agent conversation / group chat
- Wrap it in a small OpenAI-compatible `/v1/chat/completions` server
- Add the endpoint in Jayson Admin → Connections

Alternatively turn it into an Open WebUI Pipe.

## Best for
Conversational multi-agent systems where agents talk to each other in natural language turns.
