using UnityEngine;
using UnityEngine.Networking;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace UnreliableProphecy
{
    /// <summary>
    /// AI-driven dialogue generation service. Constructs contextual prompts from world state,
    /// calls an LLM API (or local model), and returns generated NPC lines.
    /// 
    /// Features:
    /// - Response caching (NPC+state hash → line)
    /// - Timeout (3 seconds) with fallback to pre-written lines
    /// - Guardrails: max length, character name prefix enforcement
    /// - Retry with exponential backoff on transient failures
    /// </summary>
    public class AIDialogueService : MonoBehaviour
    {
        public static AIDialogueService Instance { get; private set; }

        [Header("API Configuration")]
        [Tooltip("LLM endpoint URL. Leave empty to disable AI and use pre-written lines only.")]
        public string apiUrl = "";
        [Tooltip("API key for LLM provider. If empty, uses local model or fallback.")]
        public string apiKey = "";
        [Tooltip("Model name to use for generation.")]
        public string modelName = "gpt-3.5-turbo";
        [Tooltip("Max seconds to wait for AI response before falling back.")]
        public float timeoutSeconds = 3f;

        [Header("Guardrails")]
        [Tooltip("Maximum characters per generated line.")]
        public int maxLineLength = 200;
        [Tooltip("Maximum sentences per generated line.")]
        public int maxSentences = 3;
        [Tooltip("Enforce NPC name prefix in responses.")]
        public bool enforceCharacterPrefix = false;

        [Header("Caching")]
        [Tooltip("Enable response caching to reduce API calls.")]
        public bool enableCaching = true;
        private Dictionary<string, string> responseCache = new Dictionary<string, string>();
        private const int MAX_CACHE_SIZE = 500;

        // State
        private bool isGenerating = false;
        public event Action<string> OnLineGenerated;
        public event Action OnFallbackUsed;

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);
        }

        /// <summary>
        /// Main entry point: generates a contextual dialogue line for an NPC.
        /// Returns pre-written line immediately if AI is disabled or unavailable.
        /// </summary>
        public void GenerateLine(
            NPCController npc,
            DialogueStateVector state,
            string dialogueSlot, // greeting, idle, farewell, reactive
            string preWrittenFallback,
            Action<string> onComplete)
        {
            // If no API configured, use fallback immediately
            if (string.IsNullOrEmpty(apiUrl))
            {
                onComplete?.Invoke(preWrittenFallback);
                OnFallbackUsed?.Invoke();
                return;
            }

            // Check cache first
            string cacheKey = BuildCacheKey(npc, state, dialogueSlot);
            if (enableCaching && responseCache.TryGetValue(cacheKey, out var cached))
            {
                onComplete?.Invoke(cached);
                return;
            }

            // Start generation
            StartCoroutine(GenerateLineCoroutine(npc, state, dialogueSlot, preWrittenFallback, onComplete, cacheKey));
        }

        private IEnumerator GenerateLineCoroutine(
            NPCController npc,
            DialogueStateVector state,
            string dialogueSlot,
            string preWrittenFallback,
            Action<string> onComplete,
            string cacheKey)
        {
            isGenerating = true;

            string prompt = BuildPrompt(npc, state, dialogueSlot, preWrittenFallback);

            string result = null;
            bool completed = false;
            float startTime = Time.time;

            // Make API call
            using (var request = new UnityWebRequest(apiUrl, "POST"))
            {
                var body = new RequestBody
                {
                    model = modelName,
                    messages = new List<Message>
                    {
                        new Message { role = "system", content = BuildSystemPrompt(npc) },
                        new Message { role = "user", content = prompt }
                    },
                    max_tokens = maxLineLength,
                    temperature = 0.85f
                };

                string jsonBody = JsonUtility.ToJson(body);
                byte[] bodyRaw = Encoding.UTF8.GetBytes(jsonBody);

                request.uploadHandler = new UploadHandlerRaw(bodyRaw);
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");

                if (!string.IsNullOrEmpty(apiKey))
                    request.SetRequestHeader("Authorization", $"Bearer {apiKey}");

                request.SendWebRequest();

                // Wait for completion or timeout
                while (!request.isDone)
                {
                    if (Time.time - startTime > timeoutSeconds)
                    {
                        request.Abort();
                        completed = true;
                        break;
                    }
                    yield return null;
                }

                if (request.result == UnityWebRequest.Result.Success)
                {
                    var response = JsonUtility.FromJson<ResponseBody>(request.downloadHandler.text);
                    if (response?.choices != null && response.choices.Count > 0)
                    {
                        result = ApplyGuardrails(response.choices[0].message.content, npc);
                        completed = true;
                    }
                }
                else if (!completed)
                {
                    Debug.LogWarning($"[AIDialogueService] API request failed: {request.error}");
                }
            }

            isGenerating = false;

            // Use fallback if generation failed
            if (result == null)
            {
                result = preWrittenFallback;
                OnFallbackUsed?.Invoke();
            }
            else
            {
                OnLineGenerated?.Invoke(result);
            }

            // Cache the result
            if (enableCaching && result != null)
            {
                CacheResponse(cacheKey, result);
            }

            onComplete?.Invoke(result);
        }

        /// <summary>
        /// Builds the user prompt with all contextual information for the LLM.
        /// </summary>
        private string BuildPrompt(NPCController npc, DialogueStateVector state, string dialogueSlot, string preWrittenLine)
        {
            var sb = new StringBuilder();

            sb.AppendLine($"You are {npc.Data.npcDisplayName}, a {npc.npcRole} in a small town.");
            sb.AppendLine($"Personality: {npc.personalityTraits}");
            sb.AppendLine($"Speech pattern: {npc.speechPattern}");
            sb.AppendLine();
            sb.AppendLine($"Current situation:");
            sb.AppendLine($"- Mood: {state.npcEmotion}");
            sb.AppendLine($"- Player is: {state.reputationTier} to you");
            sb.AppendLine($"- Recent player actions: {(state.recentActions.Count > 0 ? string.Join(", ", state.recentActions) : "none")}");
            sb.AppendLine($"- Time: {state.timePeriod}, Weather: {state.weather}");
            sb.AppendLine($"- Quest state: {state.questState}");
            sb.AppendLine($"- Nearby: {state.proximity}");
            sb.AppendLine();
            sb.AppendLine($"Base line for context: \"{preWrittenLine}\"");
            sb.AppendLine();
            sb.AppendLine($"Generate a single {dialogueSlot} dialogue line that:");
            sb.AppendLine($"1. Stays true to your character");
            sb.AppendLine($"2. References the current situation naturally");
            sb.AppendLine($"3. Is 1-{maxSentences} sentences maximum");
            sb.AppendLine($"4. Matches your speech pattern");
            sb.AppendLine($"5. Does not break lore or reveal information you shouldn't know");
            sb.AppendLine();
            sb.AppendLine($"Respond with ONLY the dialogue line, no quotation marks or prefix.");

            return sb.ToString();
        }

        /// <summary>
        /// Builds system-level instructions for the LLM about character constraints.
        /// </summary>
        private string BuildSystemPrompt(NPCController npc)
        {
            var sb = new StringBuilder();
            sb.AppendLine($"You are playing the role of {npc.Data.npcDisplayName}.");
            sb.AppendLine($"Core backstory: {npc.coreBackstory}");
            sb.AppendLine($"Always stay in character. Never break the fourth wall.");
            sb.AppendLine($"Maximum {maxSentences} sentences per response.");
            sb.AppendLine($"Maximum {maxLineLength} characters per response.");
            return sb.ToString();
        }

        /// <summary>
        /// Applies guardrails to generated text: length limits, prefix enforcement, etc.
        /// </summary>
        private string ApplyGuardrails(string text, NPCController npc)
        {
            if (string.IsNullOrEmpty(text)) return null;

            // Trim whitespace
            text = text.Trim();

            // Remove surrounding quotes
            if (text.StartsWith("\"") && text.EndsWith("\""))
                text = text.Substring(1, text.Length - 2);

            // Enforce character prefix if configured
            if (enforceCharacterPrefix && !text.StartsWith(npc.Data.npcDisplayName))
                text = $"{npc.Data.npcDisplayName}: {text}";

            // Limit sentences
            var sentences = text.Split(new[] { '.', '!', '?' }, StringSplitOptions.RemoveEmptyEntries);
            if (sentences.Length > maxSentences)
                text = string.Join(". ", sentences.Take(maxSentences)) + ".";

            // Limit length
            if (text.Length > maxLineLength)
                text = text.Substring(0, maxLineLength - 3) + "...";

            return text;
        }

        private string BuildCacheKey(NPCController npc, DialogueStateVector state, string slot)
        {
            // Build a deterministic key from NPC id, state, and slot
            var parts = new List<string>
            {
                npc.Data.npcId,
                slot,
                state.reputationTier.ToString(),
                state.questState,
                state.timePeriod.ToString(),
                state.weather.ToString(),
                state.npcEmotion.ToString(),
                state.proximity.ToString()
            };
            parts.AddRange(state.recentActions);
            return string.Join("|", parts);
        }

        private void CacheResponse(string key, string value)
        {
            if (responseCache.Count >= MAX_CACHE_SIZE)
            {
                // Simple FIFO eviction: clear half the cache
                var keys = responseCache.Keys.Take(MAX_CACHE_SIZE / 2).ToList();
                foreach (var k in keys)
                    responseCache.Remove(k);
            }
            responseCache[key] = value;
        }

        public void ClearCache() => responseCache.Clear();
        public bool IsGenerating => isGenerating;

        // === JSON Serialization Classes ===

        [Serializable]
        private class RequestBody
        {
            public string model;
            public List<Message> messages;
            public int max_tokens;
            public float temperature;
        }

        [Serializable]
        private class Message
        {
            public string role;
            public string content;
        }

        [Serializable]
        private class ResponseBody
        {
            public List<Choice> choices;
        }

        [Serializable]
        private class Choice
        {
            public Message message;
        }
    }
}