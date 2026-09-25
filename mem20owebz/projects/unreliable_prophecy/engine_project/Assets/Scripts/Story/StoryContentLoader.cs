using UnityEngine;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Loads story content from JSON files and integrates with all game systems.
    /// Connects CutsceneManager, StoryScriptEngine, QuestEventTrigger, DialogueRouter,
    /// BranchingDialogueTree, and DialogueTreeRunner with existing QuestManager,
    /// DialogueManager, NPCController, and SaveManager.
    /// </summary>
    public class StoryContentLoader : MonoBehaviour
    {
        public static StoryContentLoader Instance { get; private set; }

        [Header("Configuration")]
        public bool loadOnStart = true;
        public bool logLoading = true;

        [Header("Runtime State")]
        public bool isLoaded = false;

        // Loaded content
        private MainStorylineData mainStoryline;
        private SideContentData sideContent;

        // Systems references
        private CutsceneManager cutsceneManager;
        private StoryScriptEngine storyEngine;
        private QuestEventTrigger questEventTrigger;
        private DialogueRouter dialogueRouter;
        private DialogueTreeRunner dialogueTreeRunner;

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

        void Start()
        {
            if (loadOnStart)
            {
                LoadAllContent();
            }
        }

        /// <summary>
        /// Loads all story content from Resources/Story/.
        /// </summary>
        public void LoadAllContent()
        {
            if (logLoading) Debug.Log("[StoryContentLoader] Loading story content...");

            // Ensure all systems exist
            EnsureSystems();

            // Load JSON content
            LoadMainStoryline();
            LoadSideContent();
            LoadDialogueTrees();

            // Integrate with existing systems
            IntegrateWithQuestManager();
            IntegrateWithDialogueManager();
            IntegrateWithNPCController();

            isLoaded = true;
            if (logLoading) Debug.Log("[StoryContentLoader] Story content loaded successfully.");
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
        }

        private void LoadMainStoryline()
        {
            var jsonFile = Resources.Load<TextAsset>("Story/main_storyline");
            if (jsonFile == null)
            {
                Debug.LogWarning("[StoryContentLoader] main_storyline.json not found");
                return;
            }

            try
            {
                mainStoryline = JsonUtility.FromJson<MainStorylineData>(jsonFile.text);
                if (logLoading) Debug.Log($"[StoryContentLoader] Loaded storyline: {mainStoryline.title} ({mainStoryline.chapters.Count} chapters)");
            }
            catch (Exception ex)
            {
                Debug.LogError($"[StoryContentLoader] Error parsing main_storyline.json: {ex.Message}");
            }
        }

        private void LoadSideContent()
        {
            var jsonFile = Resources.Load<TextAsset>("Story/side_content");
            if (jsonFile == null)
            {
                Debug.LogWarning("[StoryContentLoader] side_content.json not found");
                return;
            }

            try
            {
                sideContent = JsonUtility.FromJson<SideContentData>(jsonFile.text);
                if (logLoading) Debug.Log($"[StoryContentLoader] Loaded side content ({sideContent.side_quests.Count} side quests, {sideContent.guidebook_entries.Count} guidebook entries)");
            }
            catch (Exception ex)
            {
                Debug.LogError($"[StoryContentLoader] Error parsing side_content.json: {ex.Message}");
            }
        }

        private void LoadDialogueTrees()
        {
            var jsonFiles = Resources.LoadAll<TextAsset>("DialogueTrees");
            if (jsonFiles == null || jsonFiles.Length == 0)
            {
                Debug.LogWarning("[StoryContentLoader] No dialogue tree JSON files found in Resources/DialogueTrees/");
                return;
            }

            foreach (var file in jsonFiles)
            {
                try
                {
                    var tree = JsonUtility.FromJson<DialogueTreeData>(file.text);
                    if (tree != null && !string.IsNullOrEmpty(tree.dialogue_tree_id))
                    {
                        RegisterDialogueTree(tree);
                        if (logLoading) Debug.Log($"[StoryContentLoader] Loaded dialogue tree: {tree.dialogue_tree_id}");
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[StoryContentLoader] Error parsing {file.name}: {ex.Message}");
                }
            }
        }

        private void RegisterDialogueTree(DialogueTreeData treeData)
        {
            // Create a DialogueTree ScriptableObject at runtime
            var tree = ScriptableObject.CreateInstance<DialogueTree>();
            tree.treeId = treeData.dialogue_tree_id;
            tree.displayName = treeData.display_name;
            tree.description = treeData.description;
            tree.startNodeId = treeData.start_node;
            tree.nodes = treeData.nodes.Select(n => new DialogueTreeNode
            {
                nodeId = n.node_id,
                npcText = n.npc_text,
                playerResponse = n.player_response,
                pauseBefore = n.pause_before,
                pauseAfter = n.pause_after,
                audioClip = n.audio_clip,
                animationTrigger = n.animation_trigger
            }).ToList();

            // Register with DialogueTreeRegistry
            var registry = FindObjectOfType<DialogueTreeRegistry>();
            if (registry == null)
            {
                var regObj = new GameObject("DialogueTreeRegistry");
                registry = regObj.AddComponent<DialogueTreeRegistry>();
            }

            registry.allTrees.Add(tree);
            registry.RebuildLookup();
        }

        private void IntegrateWithQuestManager()
        {
            var qm = QuestManager.Instance;
            if (qm == null)
            {
                Debug.LogWarning("[StoryContentLoader] QuestManager not found for integration");
                return;
            }

            // Add additional quests from side content
            if (sideContent != null && sideContent.side_quests != null)
            {
                foreach (var sideQuest in sideContent.side_quests)
                {
                    // Check if quest already exists
                    if (qm.GetQuest(sideQuest.quest_id) != null) continue;

                    var quest = new Quest
                    {
                        id = sideQuest.quest_id,
                        name = sideQuest.name,
                        type = QuestType.Side,
                        status = QuestStatus.NotStarted,
                        region = sideQuest.region,
                        priority = 1,
                        objectives = sideQuest.objectives.Select(o => new QuestObjective
                        {
                            description = o.description,
                            type = ParseObjectiveType(o.type),
                            targetAmount = o.type == "collect" ? 1 : 1
                        }).ToList(),
                        rewards = sideQuest.rewards?.Count > 0 ? sideQuest.rewards : new List<string> { "Bonus Stamp" }
                    };

                    qm.allQuests.Add(quest);
                    if (logLoading) Debug.Log($"[StoryContentLoader] Added side quest: {quest.name} ({quest.id})");
                }
            }

            // Add main quests from main storyline
            if (mainStoryline?.quest_chains?.main_path != null)
            {
                foreach (var questId in mainStoryline.quest_chains.main_path)
                {
                    if (qm.GetQuest(questId) == null)
                    {
                        // Quest doesn't exist yet - create a placeholder
                        var quest = new Quest
                        {
                            id = questId,
                            name = $"Quest {questId}",
                            type = QuestType.Main,
                            status = QuestStatus.NotStarted,
                            priority = 0
                        };
                        qm.allQuests.Add(quest);
                        if (logLoading) Debug.Log($"[StoryContentLoader] Added main quest placeholder: {questId}");
                    }
                }
            }
        }

        private ObjectiveType ParseObjectiveType(string type)
        {
            return type?.ToLower() switch
            {
                "kill" => ObjectiveType.Kill,
                "collect" => ObjectiveType.Collect,
                "talk" => ObjectiveType.Talk,
                "reach" or "reachlocation" => ObjectiveType.ReachLocation,
                "use" or "useitem" => ObjectiveType.UseItem,
                "deliver" => ObjectiveType.Deliver,
                "craft" => ObjectiveType.Craft,
                _ => ObjectiveType.Talk
            };
        }

        private void IntegrateWithDialogueManager()
        {
            var dm = DialogueManager.Instance;
            if (dm == null)
            {
                Debug.LogWarning("[StoryContentLoader] DialogueManager not found for integration");
                return;
            }

            // Set up the dialogue tree runner UI references
            if (dialogueTreeRunner != null)
            {
                // The runner will use the same DialogueUI as the DialogueManager
                dialogueTreeRunner.dialogueUI = dm.dialogueUI;

                // Create response container if needed
                if (dialogueTreeRunner.responseContainer == null)
                {
                    var containerObj = new GameObject("DialogueResponseContainer");
                    var canvas = dm.dialogueUI?.GetComponentInParent<UnityEngine.Canvas>();
                    if (canvas != null)
                    {
                        containerObj.transform.SetParent(canvas.transform, false);
                        var rect = containerObj.AddComponent<UnityEngine.RectTransform>();
                        rect.anchorMin = new Vector2(0.05f, 0.05f);
                        rect.anchorMax = new Vector2(0.95f, 0.25f);
                        rect.pivot = new Vector2(0.5f, 0.5f);
                        rect.offsetMin = Vector2.zero;
                        rect.offsetMax = Vector2.zero;
                        containerObj.AddComponent<UnityEngine.UI.VerticalLayoutGroup>();
                    }
                    dialogueTreeRunner.responseContainer = containerObj.transform;
                }
            }
        }

        private void IntegrateWithNPCController()
        {
            // NPCController already routes through DialogueManager
            // which integrates with DialogueTreeRunner and DialogueRouter
            // The routing happens dynamically when player interacts with NPCs
            if (logLoading) Debug.Log("[StoryContentLoader] NPCController integration complete (dynamic routing enabled)");
        }

        /// <summary>
        /// Gets a chapter by ID from the loaded storyline.
        /// </summary>
        public ChapterData GetChapter(string chapterId)
        {
            return mainStoryline?.chapters?.FirstOrDefault(c => c.chapter_id == chapterId);
        }

        /// <summary>
        /// Gets a cutscene by ID from the loaded storyline.
        /// </summary>
        public CutsceneDataEntry GetCutscene(string cutsceneId)
        {
            return mainStoryline?.cutscenes?.FirstOrDefault(c => c.Key == cutsceneId).Value;
        }

        /// <summary>
        /// Gets side quest data by ID.
        /// </summary>
        public SideQuestData GetSideQuest(string questId)
        {
            return sideContent?.side_quests?.FirstOrDefault(q => q.quest_id == questId);
        }

        /// <summary>
        /// Gets ambient dialogue for an NPC.
        /// </summary>
        public List<string> GetAmbientDialogue(string npcId)
        {
            if (sideContent?.ambient_npc_dialogue == null) return null;
            return sideContent.ambient_npc_dialogue.ContainsKey(npcId) ? sideContent.ambient_npc_dialogue[npcId] : null;
        }

        /// <summary>
        /// Gets guidebook entries.
        /// </summary>
        public List<GuidebookEntry> GetGuidebookEntries()
        {
            return sideContent?.guidebook_entries ?? new List<GuidebookEntry>();
        }

        /// <summary>
        /// Gets companion banter for a location.
        /// </summary>
        public CompanionBanter GetBanterForLocation(string location)
        {
            return sideContent?.companion_banter?.banter_triggers?.FirstOrDefault(b => b.location == location);
        }

        /// <summary>
        /// Resets all loaded content (for New Game).
        /// </summary>
        public void ResetContent()
        {
            isLoaded = false;
            mainStoryline = null;
            sideContent = null;

            // Reset systems
            QuestManager.Instance?.Reset();
            StoryScriptEngine.Instance?.SetStoryFlag("new_game", true);
            QuestEventTrigger.Instance?.ResetTriggers();
        }
    }

    // === JSON Data Structures ===

    [Serializable]
    public class MainStorylineData
    {
        public string storyline_id;
        public string title;
        public string version;
        public List<ChapterData> chapters;
        public Dictionary<string, CutsceneDataEntry> cutscenes;
        public QuestChainData quest_chains;
    }

    [Serializable]
    public class ChapterData
    {
        public string chapter_id;
        public string name;
        public string region;
        public string region_id;
        public ChapterNarrative narrative;
        public List<SequenceData> sequences;
        public List<KeyNpcData> key_npcs;
    }

    [Serializable]
    public class ChapterNarrative
    {
        public string opening;
        public string closing;
    }

    [Serializable]
    public class SequenceData
    {
        public string id;
        public string name;
        public string trigger;
        public string narration;
        public string cutscene;
    }

    [Serializable]
    public class KeyNpcData
    {
        public string npc_id;
        public string role;
        public Dictionary<string, List<string>> dialogue_routes;
    }

    [Serializable]
    public class CutsceneDataEntry
    {
        public string id;
        public string name;
        public float duration;
        public List<CameraKeyframeData> camera_track;
        public List<CutsceneEventDataEntry> events;
    }

    [Serializable]
    public class CameraKeyframeData
    {
        public float time;
        public float[] position;
        public float[] rotation;
        public float fov;
    }

    [Serializable]
    public class CutsceneEventDataEntry
    {
        public float time;
        public string type;
        public string target;
        public string parameter;
        public string animation;
        public string prefab;
        public string quest;
        public string action;
        public string duration;
        public string chapter;
        public string flag;
    }

    [Serializable]
    public class QuestChainData
    {
        public List<string> main_path;
        public List<string> side_quests;
        public List<string> amendment_quests;
    }

    [Serializable]
    public class SideContentData
    {
        public string storyline_id;
        public string title;
        public string version;
        public List<SideQuestData> side_quests;
        public CompanionBanter companion_banter;
        public List<GuidebookEntry> guidebook_entries;
        public BureaucratDialogue bureaucrat_dialogue;
        public Dictionary<string, List<string>> ambient_npc_dialogue;
    }

    [Serializable]
    public class SideQuestData
    {
        public string quest_id;
        public string name;
        public string region;
        public string giver;
        public string description;
        public List<SideQuestObjective> objectives;
        public List<string> rewards;
    }

    [Serializable]
    public class SideQuestObjective
    {
        public string id;
        public string description;
        public string type;
        public string target;
    }

    [Serializable]
    public class CompanionBanter
    {
        public List<BanterTrigger> banter_triggers;
    }

    [Serializable]
    public class BanterTrigger
    {
        public string id;
        public string location;
        public List<string> companions;
        public string line;
    }

    [Serializable]
    public class GuidebookEntry
    {
        public string id;
        public string title;
        public string text;
    }

    [Serializable]
    public class BureaucratDialogue
    {
        public List<string> idle_lines;
        public List<string> amendment_delivery;
        public List<string> post_amendment;
    }

    [Serializable]
    public class DialogueTreeData
    {
        public string dialogue_tree_id;
        public string display_name;
        public string description;
        public string start_node;
        public List<DialogueTreeNodeData> nodes;
    }

    [Serializable]
    public class DialogueTreeNodeData
    {
        public string node_id;
        public string npc_text;
        public string player_response;
        public float pause_before;
        public float pause_after;
        public string audio_clip;
        public string animation_trigger;
        public List<DialogueOptionData> options;
    }

    [Serializable]
    public class DialogueOptionData
    {
        public string option_id;
        public string text;
        public string target_node;
        public bool is_exit_option;
        public bool advances_quest;
        public string quest_id;
        public string quest_action;
        public string required_flag;
        public string sets_flag;
        public string grants_item;
        public int reputation_change;
        public string emotion_change;
    }
}
