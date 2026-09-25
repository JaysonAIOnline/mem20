# API Keys to Gather

List of every API key used by the Jayson Model Bridge.  
You only need the ones you actually want to use — the rest can stay empty.

## Priority (best free tiers first)

| Priority | Provider              | Environment Variable          | Where to get the key                              | Notes |
|----------|-----------------------|-------------------------------|----------------------------------------------------|-------|
| 1        | Google AI Studio      | `GEMINI_API_KEY`              | https://aistudio.google.com/app/apikey             | Best overall free tier |
| 2        | Groq                  | `GROQ_API_KEY`                | https://console.groq.com/keys                      | Extremely fast |
| 3        | AnyAPI                | `ANYAPI_API_KEY`              | https://anyapi.ai or https://dash.anyapi.ai        | 300+ models through one key |
| 4        | OpenRouter            | `OPENROUTER_API_KEY`          | https://openrouter.ai/keys                         | Many free models |
| 5        | Cloudflare Workers AI | `CLOUDFLARE_API_KEY`          | https://dash.cloudflare.com → API Tokens           | Also needs Account ID |
|          |                       | `CLOUDFLARE_ACCOUNT_ID`       | Cloudflare dashboard → Overview                    | |
| 6        | Hugging Face          | `HF_TOKEN`                    | https://huggingface.co/settings/tokens             | Community models |
| 7        | DeepSeek              | `DEEPSEEK_API_KEY`            | https://platform.deepseek.com                      | Free credits |
| 8        | Mistral               | `MISTRAL_API_KEY`             | https://console.mistral.ai                         | Free tier |
| 9        | Qwen / Alibaba        | `DASHSCOPE_API_KEY`           | https://dashscope.console.aliyun.com               | Strong free quota |
| 10       | NVIDIA NIM            | `NVIDIA_API_KEY`              | https://build.nvidia.com                           | Free models |

## Additional free / low-cost providers

| Provider         | Environment Variable     | Where to get the key                          |
|------------------|--------------------------|-----------------------------------------------|
| Together         | `TOGETHER_API_KEY`       | https://api.together.xyz                      |
| Cohere           | `COHERE_API_KEY`         | https://dashboard.cohere.com                  |
| SiliconFlow      | `SILICONFLOW_API_KEY`    | https://siliconflow.cn                        |
| Moonshot / Kimi  | `MOONSHOT_API_KEY`       | https://platform.moonshot.cn                  |
| Zhipu / Z.ai     | `ZHIPU_API_KEY`          | https://open.bigmodel.cn                      |
| SambaNova        | `SAMBANOVA_API_KEY`      | https://cloud.sambanova.ai                    |
| Cerebras         | `CEREBRAS_API_KEY`       | https://cloud.cerebras.ai                     |
| Fireworks        | `FIREWORKS_API_KEY`      | https://fireworks.ai                          |
| Novita           | `NOVITA_API_KEY`         | https://novita.ai                             |
| Microsoft Foundry | `AZURE_API_KEY`          | https://ai.azure.com / Azure Portal           |
|                   | `AZURE_API_BASE`         | Your Foundry / Azure OpenAI endpoint URL      |

## Local (no key needed)

| Provider | Notes                    |
|----------|--------------------------|
| Ollama   | Runs fully local         |

## How to use the keys

Create a `.env` file next to `docker-compose.full.yml`:

```bash
GEMINI_API_KEY=
GROQ_API_KEY=
ANYAPI_API_KEY=
OPENROUTER_API_KEY=
CLOUDFLARE_API_KEY=
CLOUDFLARE_ACCOUNT_ID=
HF_TOKEN=
DEEPSEEK_API_KEY=
MISTRAL_API_KEY=
DASHSCOPE_API_KEY=
NVIDIA_API_KEY=
TOGETHER_API_KEY=
COHERE_API_KEY=
SILICONFLOW_API_KEY=
MOONSHOT_API_KEY=
ZHIPU_API_KEY=
SAMBANOVA_API_KEY=
CEREBRAS_API_KEY=
FIREWORKS_API_KEY=
NOVITA_API_KEY=
AZURE_API_KEY=
AZURE_API_BASE=
LUMA_API_KEY=
MESHY_API_KEY=
TRIPO_API_KEY=
ELEVENLABS_API_KEY=
```

Then start:

```bash
docker compose -f docker-compose.full.yml up -d
```

Only fill in the keys you have. Empty ones are simply ignored.

## Recommended minimum set

For a strong free setup, get at least these four:

1. `GEMINI_API_KEY`
2. `GROQ_API_KEY`
3. `ANYAPI_API_KEY` (or `OPENROUTER_API_KEY`)
4. `HF_TOKEN`

## Microsoft Foundry SDK (optional, for later)

The Model Bridge only needs the Azure OpenAI-compatible endpoint (`AZURE_API_KEY` + `AZURE_API_BASE`).

If you later want Foundry-native features (Agent Service, evaluations, project connections, skills), install the Foundry SDK:

```bash
pip install azure-ai-projects azure-identity openai
```

Docs: https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/develop/sdk-overview

### Creative generation keys (optional)

| Provider     | Env var            | Use |
|--------------|--------------------|-----|
| Luma         | `LUMA_API_KEY`     | Dream Machine video + 3D |
| Meshy        | `MESHY_API_KEY`    | Text/Image → 3D |
| Tripo        | `TRIPO_API_KEY`    | Fast 3D |
| ElevenLabs   | `ELEVENLABS_API_KEY` | Premium voices |
