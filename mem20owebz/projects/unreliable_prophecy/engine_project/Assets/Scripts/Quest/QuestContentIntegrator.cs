using UnityEngine;
using System;
using System.Collections.Generic;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Master integrator for all story content and quest systems.
    /// Place this in the Boot scene to wire everything together.
    /// Connects: CutsceneManager, StoryScriptEngine, QuestEventTrigger,
    /// DialogueRouter, DialogueTreeRunner, BranchingDialogueTree
    /// with: QuestManager, DialogueManager, NPCController, SaveManager.
    /// </summary>
    public class QuestContentIntegrator : MonoBehaviour
    {
        [Header("Configuration")]
        public bool initializeOnStart = true;
        public bool logInitialization = true;

        [Header("Scene References")]
        public DialogueUI dialogueUI;
        public Transform responseContainer;
        public GameObject responseButtonPrefab;

        // System references
        private QuestManager questManager;
        private DialogueManager dialogueManager;
        private CutsceneManager cutsceneManager;
        private StoryScriptEngine storyEngine;
        private QuestEventTrigger questEventTrigger;
        private DialogueRouter dialogueRouter;
        private DialogueTreeRunner dialogueTreeRunner;
        private StoryContentLoader contentLoader;

        void Start()
        {
            if (initializeOnStart)
            {
                Initialize();
            }
        }

        public void Initialize()
        {
            if (logInitialization) Debug.Log("[QuestContentIntegrator] Initializing story content and quest systems...");

            // Get existing systems
            questManager = QuestManager.Instance;
            dialogueManager = DialogueManager.Instance;

            // Ensure new systems exist
            EnsureSystems();

            // Wire events
            WireEvents();

            // Initialize content
            contentLoader.LoadAllContent();

            if (logInitialization) Debug.Log("[QuestContentIntegrator] Initialization complete.");
        }

        private void EnsureSystems()
        {
            // CutsceneManager
            cutsceneManager = CutsceneManager.Instance;
            if (cutsceneManager == null)
            {
                var go = new GameObject("CutsceneManager");
                cutsceneManager = go.AddComponent<CutsceneManager>();
            }

            // StoryScriptEngine
            storyEngine = StoryScriptEngine.Instance;
            if (storyEngine == null)
            {
                var go = new GameObject("StoryScriptEngine");
                storyEngine = go.AddComponent<StoryScriptEngine>();
            }

            // QuestEventTrigger
            questEventTrigger = QuestEventTrigger.Instance;
            if (questEventTrigger == null)
            {
                var go = new GameObject("QuestEventTrigger");
                questEventTrigger = go.AddComponent<QuestEventTrigger>();
            }

            // DialogueRouter
            dialogueRouter = DialogueRouter.Instance;
            if (dialogueRouter == null)
            {
                var go = new GameObject("DialogueRouter");
                dialogueRouter = go.AddComponent<DialogueRouter>();
            }

            // DialogueTreeRunner
            dialogueTreeRunner = DialogueTreeRunner.Instance;
            if (dialogueTreeRunner == null)
            {
                var go = new GameObject("DialogueTreeRunner");
                dialogueTreeRunner = go.AddComponent<DialogueTreeRunner>();
            }

            // StoryContentLoader
            contentLoader = StoryContentLoader.Instance;
            if (contentLoader == null)
            {
                var go = new GameObject("StoryContentLoader");
                contentLoader = go.AddComponent<StoryContentLoader>();
            }

            // CutsceneRegistry
            var cutsceneRegistry = FindObjectOfType<CutsceneRegistry>();
            if (cutsceneRegistry == null)
            {
                var go = new GameObject("CutsceneRegistry");
                go.AddComponent<CutsceneRegistry>();
            }

            // DialogueTreeRegistry
            var treeRegistry = FindObjectOfType<DialogueTreeRegistry>();
            if (treeRegistry == null)
            {
                var go = new GameObject("DialogueTreeRegistry");
                go.AddComponent<DialogueTreeRegistry>();
            }
        }

        private void WireEvents()
        {
            // QuestManager events -> QuestEventTrigger
            if (questManager != null)
            {
                questManager.OnQuestCompleted += (quest) =>
                {
                    questEventTrigger?.OnQuestCompleted(quest);
                };
                questManager.OnQuestAccepted += (quest) =>
                {
                    questEventTrigger?.OnQuestAccepted(quest);
                };
                questManager.OnQuestTurnedIn += (quest) =>
                {
                    questEventTrigger?.OnQuestTurnedIn(quest);
                };
            }

            // StoryScriptEngine events -> QuestEventTrigger
            if (storyEngine != null)
            {
                storyEngine.OnStoryFlagSet += (flag) =>
                {
                    questEventTrigger?.OnStoryFlagSet(flag);
                };
            }

            // CutsceneManager events -> StoryScriptEngine
            if (cutsceneManager != null)
            {
                cutsceneManager.OnCutsceneCompleted += (cutscene) =>
                {
                    // After cutscene, check for sequence triggers
                    if (storyEngine != null && cutscene != null)
                    {
                        // Auto-start next quest if specified
                        if (!string.IsNullOrEmpty(cutscene.nextQuestId))
                        {
                            questManager?.AcceptQuest(cutscene.nextQuestId);
                        }
                    }
                };
            }

            // DialogueTreeRunner events -> QuestManager
            if (dialogueTreeRunner != null)
            {
                dialogueTreeRunner.OnOptionSelected += (option, index) =>
                {
                    if (option.advances_quest && !string.IsNullOrEmpty(option.questId))
                    {
                        switch (option.questAction)
                        {
                            case "accept":
                                questManager?.AcceptQuest(option.questId);
                                break;
                            case "complete":
                                var quest = questManager?.GetQuest(option.questId);
                                if (quest != null)
                                {
                                    quest.status = QuestStatus.Completed;
                                    questManager.OnQuestCompleted?.Invoke(quest);
                                }
                                break;
                        }
                    }
                };
            }
        }

        /// <summary>
        /// Triggers a region entry event across all systems.
        /// Call this when the player enters a new region.
        /// </summary>
        public void OnRegionEntered(string regionId)
        {
            questEventTrigger?.OnRegionEntered(regionId);
        }

        /// <summary>
        /// Triggers a region transition event across all systems.
        /// </summary>
        public void OnRegionTransition(string fromRegion, string toRegion)
        {
            questEventTrigger?.OnRegionTransition(fromRegion, toRegion);
        }

        /// <summary>
        /// Triggers a waypoint reached event.
        /// </summary>
        public void OnWaypointReached(string waypointId)
        {
            questEventTrigger?.OnWaypointReached(waypointId);
        }

        /// <summary>
        /// Triggers an enemy defeated event.
        /// </summary>
        public void OnEnemyDefeated(string enemyId)
        {
            questEventTrigger?.OnEnemyDefeated(enemyId);
        }

        /// <summary>
        /// Triggers an item collected event.
        /// </summary>
        public void OnItemCollected(string itemId)
        {
            questEventTrigger?.OnItemCollected(itemId);
        }

        /// <summary>
        /// Plays a cutscene by ID.
        /// </summary>
        public void PlayCutscene(string cutsceneId)
        {
            cutsceneManager?.PlayCutscene(cutsceneId);
        }

        /// <summary>
        /// Starts a dialogue tree with an NPC.
        /// </summary>
        public void StartDialogue(string treeId, Action onComplete = null)
        {
            var registry = FindObjectOfType<DialogueTreeRegistry>();
            var tree = registry?.GetTree(treeId);
            if (tree != null)
            {
                dialogueTreeRunner?.StartDialogue(tree, onComplete);
            }
        }

        /// <summary>
        /// Sets a story flag.
        /// </summary>
        public void SetStoryFlag(string flag, bool value = true)
        {
            storyEngine?.SetStoryFlag(flag, value);
        }

        /// <summary>
        /// Gets a story flag.
        /// </summary>
        public bool GetStoryFlag(string flag)
        {
            return storyEngine?.GetStoryFlag(flag) ?? false;
        }

        /// <summary>
        /// Starts a specific story sequence.
        /// </summary>
        public void TriggerSequence(string sequenceId)
        {
            storyEngine?.TriggerSequence(sequenceId);
        }

        /// <summary>
        /// Gets the active chapter.
        /// </summary>
        public StoryChapter GetActiveChapter()
        {
            return storyEngine?.GetActiveChapter();
        }

        /// <summary>
        /// Resets all story state (for New Game).
        /// </summary>
        public void ResetAll()
        {
            questManager?.Reset();
            storyEngine?.SetStoryFlag("new_game", true);
            questEventTrigger?.ResetTriggers();
            contentLoader?.ResetContent();
        }
    }
}
