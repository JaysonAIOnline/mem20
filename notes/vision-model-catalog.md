# mem20 Vision Model Catalog (verified 2026-09-08)

## Working — FREE vision model
- Endpoint: `https://integrate.api.nvidia.com/v1` (OpenAI-compatible, same key as text)
- Model: `meta/llama-3.2-11b-vision-instruct`
- Cost: free (integrate tier)
- Format: OpenAI multimodal content blocks
  ```json
  {"role":"user","content":[
    {"type":"text","text":"What do you see?"},
    {"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}
  ]}
  ```
- Verified: correctly identified the mem20 dashboard screenshot (title "MEM20 AGENT", menu items).
- mem20 usage: `llm.chat(messages, images=["/path/to.png"])` or `await llm.achat(...)` — the client
  auto-selects the vision model when `images` is passed.
- Env override: `MEM20_LLM_VISION_MODEL`

## Kept — text reasoning default (unchanged)
- Model: `nvidia/nemotron-3-ultra-550b-a55b`
- Default for all text chat; vision model is only used when an image is supplied.
- Env override: `MEM20_LLM_MODEL`

## Available on endpoint but NOT usable (free tier)
- `meta/llama-3.2-90b-vision-instruct` — request errors on this account
- `google/gemma-3-12b-it` — 404 "Not found for account"
- `google/diffusiongemma-26b-a4b-it` (image GEN) — only emits `dalle.text2im` action;
  `/v1/images/generations` → 404, so no real image output

## Reuse elsewhere
The 11b vision model is reusable anywhere that needs image → text: mem20 pipelines,
QA screenshot assertions, game asset inspection, OCR-adjacent vision tasks, design review.
Same key, same endpoint, standard OpenAI images format.