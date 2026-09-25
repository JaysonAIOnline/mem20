using UnityEngine;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Attached to each NPC in the world. Handles proximity detection, trigger evaluation,
    /// and AI-driven dialogue generation. Integrates with DialogueManager for UI display.
    /// Uses distance-based proximity detection (works with CharacterController player).
    /// </summary>
    public class NPCController : MonoBehaviour
    {
        [Header("NPC Identity")]
        public string npcId;
        public string npcRole;
        [TextArea(2, 4)]
        public string personalityTraits;
        [TextArea(2, 4)]
        public string speechPattern;
        [TextArea(2, 4)]
        public string coreBackstory;

        [Header("Dialogue Data")]
        public DialogueData dialogueData;

        [Header("AI Settings")]
        [Tooltip("Enable AI generation for this NPC. If false, uses pre-written lines only.")]
        public bool useAIGeneration = true;
        [Tooltip("Quest ID associated with this NPC (for quest-givers).")]
        public string associatedQuestId;

        [Header("Trigger Settings")]
        public float interactionRadius = 3f;
        public float reTriggerCooldown = 30f; // prevent spam

        // State
        private bool playerInRange = false;
        private float lastInteractionTime = -999f;
        private List<string> recentLines = new List<string>(); // prevent repeats
        private const int MAX_RECENT_LINES = 3;
        private DialogueEvaluator evaluator;

        // Cached components
        private Collider triggerCollider;

        /// <summary>
        /// Gets the display name for this NPC.
        /// </summary>
        public string DisplayName => dialogueData != null ? dialogueData.npcDisplayName : npcId;

    /// <summary>
    /// Gets or sets the DialogueData object.
    /// </summary>
    public DialogueData Data { get => dialogueData; set => dialogueData = value; }

        void Awake()
        {
            evaluator = new DialogueEvaluator();
            triggerCollider = GetComponent<Collider>();
            if (triggerCollider != null)
                triggerCollider.isTrigger = true;

            // Load nodes from dialogue data
            LoadDialogueNodes();
        }

        /// <summary>
        /// Loads conditional dialogue nodes from the DialogueData asset.
        /// In a full implementation, this would load from JSON or a ScriptableObject.
        /// </summary>
        private void LoadDialogueNodes()
        {
            if (dialogueData == null) return;

            // Create base nodes from the dialogue data's line lists
            // In production, these would come from a JSON file or ScriptableObject
            var nodes = new List<DialogueNodeData>();

            // Greeting nodes
            for (int i = 0; i < dialogueData.greetings.Count; i++)
            {
                nodes.Add(new DialogueNodeData
                {
                    nodeId = $"{npcId}_greeting_{i}",
                    npcId = npcId,
                    slot = "greeting",
                    text = dialogueData.greetings[i],
                    priority = 0,
                    conditions = new DialogueCondition()
                });
            }

            // Idle nodes
            for (int i = 0; i < dialogueData.idleChatter.Count; i++)
            {
                nodes.Add(new DialogueNodeData
                {
                    nodeId = $"{npcId}_idle_{i}",
                    npcId = npcId,
                    slot = "idle",
                    text = dialogueData.idleChatter[i],
                    priority = 0,
                    conditions = new DialogueCondition()
                });
            }

            // Farewell nodes
            for (int i = 0; i < dialogueData.farewells.Count; i++)
            {
                nodes.Add(new DialogueNodeData
                {
                    nodeId = $"{npcId}_farewell_{i}",
                    npcId = npcId,
                    slot = "farewell",
                    text = dialogueData.farewells[i],
                    priority = 0,
                    conditions = new DialogueCondition()
                });
            }

            // Reactive nodes
            for (int i = 0; i < dialogueData.reactiveComments.Count; i++)
            {
                nodes.Add(new DialogueNodeData
                {
                    nodeId = $"{npcId}_reactive_{i}",
                    npcId = npcId,
                    slot = "reactive",
                    text = dialogueData.reactiveComments[i],
                    priority = 1, // higher priority for reactive
                    conditions = new DialogueCondition()
                });
            }

            evaluator.RegisterNodes(nodes);
        }

        void OnTriggerEnter(Collider other)
        {
            // Legacy: trigger-based proximity (doesn't work with CharacterController)
            // Distance-based detection in Update() handles all proximity now
        }

        void OnTriggerExit(Collider other)
        {
            // Legacy: trigger-based proximity (doesn't work with CharacterController)
            // Distance-based detection in Update() handles all proximity now
        }

        void Update()
        {
            // Distance-based proximity detection (works with CharacterController player)
            var player = GameObject.FindGameObjectWithTag("Player");
            if (player != null)
            {
                float dist = Vector3.Distance(transform.position, player.transform.position);
                bool inRange = dist <= interactionRadius;

                if (inRange && !playerInRange)
                {
                    playerInRange = true;
                    var ui = FindObjectOfType<DialogueUI>();
                    if (ui != null)
                        ui.ShowInteractionPrompt(DisplayName);
                }
                else if (!inRange && playerInRange)
                {
                    playerInRange = false;
                    var ui = FindObjectOfType<DialogueUI>();
                    if (ui != null)
                        ui.HideInteractionPrompt();
                }
            }

            if (!playerInRange) return;
            if (Time.time - lastInteractionTime < reTriggerCooldown) return;

            // Check for interaction input
            if (Input.GetKeyDown(KeyCode.E))
            {
                var dm = DialogueManager.Instance;
                if (dm != null && !dm.IsDialogueActive)
                {
                    dm.StartDialogue(this);
                    lastInteractionTime = Time.time;
                }
            }
        }

        /// <summary>
        /// Called by DialogueManager to get the dialogue lines for this interaction.
        /// Evaluates triggers and optionally uses AI to generate contextual lines.
        /// </summary>
        public List<string> GetDialogueLines()
        {
            var lines = new List<string>();
            var state = WorldStateService.Instance?.BuildStateVector(npcId, associatedQuestId)
                ?? new DialogueStateVector();

            // Evaluate each slot
            string greeting = EvaluateSlot("greeting", state);
            string idle = EvaluateSlot("idle", state);
            string farewell = EvaluateSlot("farewell", state);

            lines.Add(greeting);
            lines.Add(idle);
            lines.Add(farewell);

            return lines;
        }

        /// <summary>
        /// Evaluates a single dialogue slot, with optional AI enhancement.
        /// </summary>
        private string EvaluateSlot(string slot, DialogueStateVector state)
        {
            // Get the pre-written line from evaluator
            string preWritten = evaluator.Evaluate(npcId, slot, state, GetFallbackLine(slot));

            // If AI is disabled or unavailable, return pre-written
            if (!useAIGeneration || AIDialogueService.Instance == null)
                return preWritten;

            // For synchronous return (DialogueManager expects immediate results),
            // we return the pre-written line and optionally trigger async AI generation
            // to update the line for next time.
            if (AIDialogueService.Instance.IsGenerating)
                return preWritten;

            // Start async AI generation for next interaction
            AIDialogueService.Instance.GenerateLine(
                this,
                state,
                slot,
                preWritten,
                (result) => {
                    // Cache the result for next time
                    CacheAIGeneratedLine(slot, result);
                });

            return preWritten;
        }

        private string GetFallbackLine(string slot)
        {
            if (dialogueData == null) return "...";

            return slot switch
            {
                "greeting" => dialogueData.GetRandomLine(dialogueData.greetings),
                "idle" => dialogueData.GetRandomLine(dialogueData.idleChatter),
                "farewell" => dialogueData.GetRandomLine(dialogueData.farewells),
                "reactive" => dialogueData.GetRandomLine(dialogueData.reactiveComments),
                _ => "..."
            };
        }

        private Dictionary<string, string> aiCache = new Dictionary<string, string>();

        private void CacheAIGeneratedLine(string slot, string line)
        {
            aiCache[slot] = line;
        }

        /// <summary>
        /// Gets a cached AI-generated line for the slot, or falls back to pre-written.
        /// </summary>
        public string GetCachedLine(string slot, string fallback)
        {
            return aiCache.TryGetValue(slot, out var line) ? line : fallback;
        }

        /// <summary>
        /// Clears the AI-generated line cache (e.g., on world state change).
        /// </summary>
        public void ClearAICache()
        {
            aiCache.Clear();
        }

        /// <summary>
        /// Adds a conditional dialogue node at runtime (for quest-specific lines, etc).
        /// </summary>
        public void AddConditionalLine(DialogueNodeData node)
        {
            evaluator.RegisterNode(node);
        }

        /// <summary>
        /// Updates the NPC's emotional state in the world state service.
        /// </summary>
        public void SetEmotion(WorldStateService.Emotion emotion)
        {
            WorldStateService.Instance?.SetNpcEmotion(npcId, emotion);
        }

        /// <summary>
        /// Updates proximity state for this NPC.
        /// </summary>
        public void SetProximity(WorldStateService.Proximity proximity)
        {
            // This would be updated by a proximity manager in a full implementation
        }

        /// <summary>
        /// Gets the world position for interaction (for proximity prompts).
        /// </summary>
        public Vector3 GetInteractionPosition()
        {
            return transform.position;
        }
    }
}