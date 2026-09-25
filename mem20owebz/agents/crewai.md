# mem20 crews + Jayson — Installation & Connection

mem20 crews is excellent for role-based multi-agent teams (researcher + writer + reviewer, etc.).

## 1. Install mem20 crews

```bash
pip install mem20 crews mem20 crews-tools
```

Create your agents and crew as usual.

## 2. Connect to Jayson

### Easiest method – OpenAI-compatible wrapper

1. Write a small server that receives a chat message
2. Runs your mem20 crews crew with that message as the task
3. Returns the final result in OpenAI chat completions format

Then add it in Jayson:

- Admin → Connections
- API Base URL: `http://host.docker.internal:PORT/v1`
- API Key: whatever you choose

### Alternative
Turn the crew into an Open WebUI Pipe so it shows up as a model.

## 3. Best for
- Fast multi-agent prototypes
- Clear division of labor between agents
- Collaborative task solving
