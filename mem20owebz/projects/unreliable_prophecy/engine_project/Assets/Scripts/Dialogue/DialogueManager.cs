using UnityEngine;
using System.Collections.Generic;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Enhanced DialogueManager that integrates AI-driven dynamic dialogue generation.
    /// Routes lines from NPCs through the AIDialogueService when available,
    /// falling back to pre-written lines when AI is unavailable.
    /// </summary>
    public class DialogueManager : MonoBehaviour
    {
        public static DialogueManager Instance { get; private set; }

        [Header("UI Reference")]
        public DialogueUI dialogueUI;

        [Header("AI Settings")]
        [Tooltip("Enable AI-driven dialogue generation globally.")]
        public bool enableAIGeneration = true;
        [Tooltip("Show AI-generated indicator in UI.")]
        public bool showAIGeneratedIndicator = true;

        [Header("Settings")]
        public float facePlayerSpeed = 5f;
        public float interactionRadius = 3f;

        // State
        private NPCController currentNPC;
        private bool isDialogueActive = false;
        private List<string> currentLines = new List<string>();
        private int currentLineIndex = 0;
        private bool usingAIGenerated = false;

        // Events
        public System.Action<NPCController> OnDialogueStarted;
        public System.Action OnDialogueEnded;
        public System.Action<bool> OnAILineUsed; // true if AI-generated, false if fallback

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

        void Update()
        {
            if (!isDialogueActive) return;

            if (Input.GetKeyDown(KeyCode.E))
            {
                // If typewriter is active, skip it instead of advancing
                if (dialogueUI != null && dialogueUI.IsTypewriterActive)
                {
                    dialogueUI.SkipTypewriter();
                }
                else
                {
                    AdvanceDialogue();
                }
            }
            if (Input.GetKeyDown(KeyCode.Q))
            {
                EndDialogue();
            }
        }

        /// <summary>
        /// Called by NPCController when player enters proximity and presses E.
        /// Initiates AI-driven dialogue generation if enabled.
        /// </summary>
        public void StartDialogue(NPCController npc)
        {
            if (isDialogueActive) return;
            currentNPC = npc;
            isDialogueActive = true;
            currentLineIndex = 0;

            // Build the line queue from this NPC's data (pre-written fallback)
            currentLines = npc.GetDialogueLines();

            // Show UI
            if (dialogueUI != null)
            {
                dialogueUI.Show(npc.Data.npcDisplayName);
            }

            // Show history panel and proximity prompt
            var history = FindObjectOfType<DialogueHistoryUI>();
            if (history != null)
            {
                history.Clear();
                history.Show();
                history.AddSystemMessage($"Started conversation with {npc.Data.npcDisplayName}");
            }

            // Play audio cues
            var audio = DialogueAudio.Instance;
            if (audio != null)
            {
                audio.PlayDialogueOpen();
                audio.PlayNpcGreeting();
            }

            // If AI is enabled, generate enhanced lines asynchronously
            if (enableAIGeneration && AIDialogueService.Instance != null)
            {
                StartCoroutine(GenerateAIDialogue(npc));
            }
            else
            {
                DisplayCurrentLine();
            }

            // Freeze player
            var player = GameObject.FindGameObjectWithTag("Player");
            if (player != null)
            {
                var pc = player.GetComponent<PlayerController>();
                if (pc != null) pc.enabled = false;
            }

            OnDialogueStarted?.Invoke(npc);
        }

        /// <summary>
        /// Generates AI-enhanced dialogue lines asynchronously while showing pre-written lines.
        /// When generation completes, swaps in the AI lines for a more contextual experience.
        /// </summary>
        private System.Collections.IEnumerator GenerateAIDialogue(NPCController npc)
        {
            var ai = AIDialogueService.Instance;
            if (ai == null) yield break;

            var state = WorldStateService.Instance?.BuildStateVector(npc.Data.npcId, npc.associatedQuestId)
                ?? new DialogueStateVector();

            // Generate greeting, idle, and farewell in parallel
            string greeting = currentLines.Count > 0 ? currentLines[0] : "...";
            string idle = currentLines.Count > 1 ? currentLines[1] : "...";
            string farewell = currentLines.Count > 2 ? currentLines[2] : "...";

            bool greetingDone = false;
            bool idleDone = false;
            bool farewellDone = false;

            ai.GenerateLine(npc, state, "greeting", greeting, (result) => {
                if (result != greeting) usingAIGenerated = true;
                if (currentLines.Count > 0) currentLines[0] = result;
                greetingDone = true;
            });

            ai.GenerateLine(npc, state, "idle", idle, (result) => {
                if (result != idle) usingAIGenerated = true;
                if (currentLines.Count > 1) currentLines[1] = result;
                idleDone = true;
            });

            ai.GenerateLine(npc, state, "farewell", farewell, (result) => {
                if (result != farewell) usingAIGenerated = true;
                if (currentLines.Count > 2) currentLines[2] = result;
                farewellDone = true;
            });

            // Wait for all generations to complete (or timeout)
            float startTime = Time.time;
            while (!greetingDone || !idleDone || !farewellDone)
            {
                if (Time.time - startTime > 5f) break; // safety timeout
                yield return null;
            }

            // Display the (potentially AI-enhanced) first line
            DisplayCurrentLine();

            OnAILineUsed?.Invoke(usingAIGenerated);
        }

        void DisplayCurrentLine()
        {
            if (currentLineIndex >= currentLines.Count)
            {
                EndDialogue();
                return;
            }

            string line = currentLines[currentLineIndex];
            if (dialogueUI != null)
            {
                dialogueUI.SetDialogueText(line);
                dialogueUI.SetAdvancePrompt(currentLineIndex < currentLines.Count - 1 ? "Press E to continue..." : "Press E to finish...");

                // Show AI indicator
                if (showAIGeneratedIndicator && usingAIGenerated)
                {
                    // Could add a small indicator icon here
                }
            }

            // Add to history
            var history = FindObjectOfType<DialogueHistoryUI>();
            if (history != null && currentNPC != null)
            {
                history.AddLine(currentNPC.Data.npcDisplayName, line, false);
            }

            // Play advance sound
            if (currentLineIndex > 0)
            {
                var audio = DialogueAudio.Instance;
                if (audio != null) audio.PlayDialogueAdvance();
            }
        }

        void AdvanceDialogue()
        {
            currentLineIndex++;
            if (currentLineIndex >= currentLines.Count)
            {
                EndDialogue();
            }
            else
            {
                DisplayCurrentLine();
            }
        }

        void EndDialogue()
        {
            isDialogueActive = false;
            usingAIGenerated = false;

            // Play farewell audio
            var audio = DialogueAudio.Instance;
            if (audio != null)
            {
                audio.PlayNpcFarewell();
                audio.PlayDialogueClose();
            }

            // Add to history
            var history = FindObjectOfType<DialogueHistoryUI>();
            if (history != null)
            {
                history.AddSystemMessage("Conversation ended.");
                history.Hide();
            }

            if (dialogueUI != null)
                dialogueUI.Hide();

            // Re-enable player
            var player = GameObject.FindGameObjectWithTag("Player");
            if (player != null)
            {
                var pc = player.GetComponent<PlayerController>();
                if (pc != null) pc.enabled = true;
            }

            currentNPC = null;
            OnDialogueEnded?.Invoke();
        }

        public bool IsDialogueActive => isDialogueActive;
        public NPCController CurrentNPC => currentNPC;
    }
}