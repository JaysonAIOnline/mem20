# Jayson Model Bridge — Full Free Provider Set

Expanded with providers from:
https://github.com/12britz/awesome-free-models

## Providers included

| Provider              | Env Variable              |
|-----------------------|---------------------------|
| AnyAPI                | `ANYAPI_API_KEY`          |
| Google AI Studio      | `GEMINI_API_KEY`          |
| Groq                  | `GROQ_API_KEY`            |
| Hugging Face          | `HF_TOKEN`                |
| Cloudflare            | `CLOUDFLARE_API_KEY` + `CLOUDFLARE_ACCOUNT_ID` |
| Qwen / Alibaba        | `DASHSCOPE_API_KEY`       |
| Mistral               | `MISTRAL_API_KEY`         |
| DeepSeek              | `DEEPSEEK_API_KEY`        |
| OpenRouter            | `OPENROUTER_API_KEY`      |
| NVIDIA NIM            | `NVIDIA_API_KEY`          |
| Together              | `TOGETHER_API_KEY`        |
| Cohere                | `COHERE_API_KEY`          |
| SiliconFlow           | `SILICONFLOW_API_KEY`     |
| Moonshot / Kimi       | `MOONSHOT_API_KEY`        |
| Zhipu / Z.ai          | `ZHIPU_API_KEY`           |
| SambaNova             | `SAMBANOVA_API_KEY`       |
| Cerebras              | `CEREBRAS_API_KEY`        |
| Fireworks             | `FIREWORKS_API_KEY`       |
| Novita                | `NOVITA_API_KEY`          |
| Microsoft Foundry     | `AZURE_API_KEY` + `AZURE_API_BASE` |
| Ollama (local)        | (none)                    |

## Router groups
- `fast` / `balanced` / `strong`

## Start
```bash
docker compose -f docker-compose.full.yml up -d
```

## Connect to Jayson
- Base URL: `http://host.docker.internal:4000/v1`
- Key: `jayson-bridge-secret-change-me`

Only the providers you give keys for will work. The rest stay available for when you add keys later.

## Microsoft Foundry SDK note

The bridge uses the OpenAI-compatible Azure/Foundry endpoint only.
For deeper Foundry features (agents, evaluations, projects) install later:

```bash
pip install azure-ai-projects azure-identity openai
```
