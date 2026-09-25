using UnityEngine;
using System;
using System.Collections.Generic;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Branching dialogue tree system with dead-end prevention.
    /// Each dialogue tree has nodes (lines) and edges (choices).
    /// Dead-end nodes always include at least one option that advances the conversation.
    /// </summary>
    public class DialogueTree : ScriptableObject
    {
        public string treeId;
        public string displayName;
        [TextArea(2, 4)]
        public string description;
        public List<DialogueTreeNode> nodes = new List<DialogueTreeNode>();
        public string startNodeId;

        /// <summary>
        /// Validates the tree has no dead ends (every leaf node has a back-edge or advances state).
        /// </summary>
        public bool Validate(out List<string> errors)
        {
            errors = new List<string>();
            var nodeDict = nodes.ToDictionary(n => n.nodeId);

            foreach (var node in nodes)
            {
                // If a node has no children, it must have a quest/conversation advancement action
                if (node.options.Count == 0)
                {
                    if (node.onEnterActions.Count == 0 && node.onExitActions.Count == 0)
                    {
                        errors.Add($"Node '{node.nodeId}' is a dead end with no exit actions.");
                    }
                }

                // Check for broken references
                foreach (var option in node.options)
                {
                    if (!string.IsNullOrEmpty(option.targetNodeId) && !nodeDict.ContainsKey(option.targetNodeId))
                    {
                        errors.Add($"Node '{node.nodeId}' option references missing node '{option.targetNodeId}'.");
                    }
                }
            }

            // Check start node exists
            if (!string.IsNullOrEmpty(startNodeId) && !nodeDict.ContainsKey(startNodeId))
            {
                errors.Add($"Start node '{startNodeId}' does not exist.");
            }

            return errors.Count == 0;
        }

        /// <summary>
        /// Prevents dead ends by ensuring every node without children has a "return to menu" option.
        /// Called at edit time or runtime before starting a conversation.
        /// </summary>
        public void EnsureNoDeadEnds()
        {
            foreach (var node in nodes)
            {
                if (node.options.Count == 0 && node.onEnterActions.Count == 0)
                {
                    // Add a default exit option
                    node.options.Add(new DialogueOption
                    {
                        optionId = $"{node.nodeId}_exit",
                        text = "[Continue]",
                        targetNodeId = "", // Empty = end conversation
                        isExitOption = true
                    });
                }
            }
        }

        public DialogueTreeNode GetNode(string nodeId)
        {
            return nodes.FirstOrDefault(n => n.nodeId == nodeId);
        }

        public DialogueTreeNode StartNode => GetNode(startNodeId);
    }

    [Serializable]
    public class DialogueTreeNode
    {
        public string nodeId;
        public string npcText;
        [TextArea(2, 4)]
        public string playerResponse; // Optional: what the player "says" to trigger this line
        public List<DialogueOption> options = new List<DialogueOption>();
        public List<DialogueAction> onEnterActions = new List<DialogueAction>();
        public List<DialogueAction> onExitActions = new List<DialogueAction>();
        public float pauseBefore = 0f;
        public float pauseAfter = 0f;
        public string audioClip;
        public string animationTrigger;
    }

    [Serializable]
    public class DialogueOption
    {
        public string optionId;
        public string text;
        public string targetNodeId; // Empty = end conversation
        public bool isExitOption = false;
        public bool advancesQuest = false;
        public string questId; // Quest to advance
        public string questAction; // accept, complete, update
        public string questObjective; // For update actions
        public string requiredFlag; // Story flag required to show this option
        public string setsFlag; // Flag set when this option is chosen
        public string grantsItem; // Item granted when chosen
        public int reputationChange;
        public string emotionChange; // Change NPC emotion
        public List<DialogueAction> onSelectActions = new List<DialogueAction>();
    }

    [Serializable]
    public class DialogueAction
    {
        public DialogueActionType actionType;
        public string parameter;
        public string secondaryParameter;

        public DialogueAction() { }
        public DialogueAction(DialogueActionType type, string param, string secondary = "")
        {
            actionType = type;
            parameter = param;
            secondaryParameter = secondary;
        }
    }

    public enum DialogueActionType
    {
        AcceptQuest,
        CompleteQuest,
        UpdateQuest,
        SetFlag,
        ClearFlag,
        GrantItem,
        RemoveItem,
        ChangeReputation,
        ChangeEmotion,
        Teleport,
        PlayCutscene,
        EndConversation,
        SetStoryFlag,
        PlayAudio,
        ChangeWeather,
        ChangeTime
    }

    /// <summary>
    /// Component that manages an active branching dialogue session.
    /// Drives the UI and executes actions when options are selected.
    /// </summary>
    public class DialogueTreeRunner : MonoBehaviour
    {
        public static DialogueTreeRunner Instance { get; private set; }

        [Header("UI References")]
        public DialogueUI dialogueUI;
        public Transform responseContainer;
        public GameObject responseButtonPrefab;

        [Header("Settings")]
        public float defaultPauseBetweenLines = 0.3f;

        private DialogueTree activeTree;
        private DialogueTreeNode currentNode;
        private bool isInDialogue = false;
        private Action onDialogueComplete;

        // Events
        public event Action<DialogueTreeNode> OnNodeDisplayed;
        public event Action<DialogueOption, int> OnOptionSelected;
        public event Action<DialogueTree> OnDialogueStarted;
        public event Action<DialogueTree> OnDialogueEnded;

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
        }

        /// <summary>
        /// Starts a dialogue tree with a specific NPC.
        /// </summary>
        public void StartDialogue(DialogueTree tree, Action onComplete = null)
        {
            if (isInDialogue || tree == null) return;

            activeTree = tree;
            onDialogueComplete = onComplete;

            // Ensure no dead ends
            activeTree.EnsureNoDeadEnds();

            // Show the start node
            isInDialogue = true;
            OnDialogueStarted?.Invoke(activeTree);

            // Start with the first node or specified start node
            var start = activeTree.StartNode ?? activeTree.nodes[0];
            if (start != null)
            {
                DisplayNode(start);
            }
            else
            {
                EndDialogue();
            }
        }

        /// <summary>
        /// Displays a dialogue node with its options.
        /// </summary>
        public void DisplayNode(DialogueTreeNode node)
        {
            currentNode = node;

            // Execute enter actions
            ExecuteActions(node.onEnterActions);

            // Show the NPC text
            if (dialogueUI != null)
            {
                dialogueUI.Show("NPC"); // Name would be passed in
                dialogueUI.SetDialogueText(node.npcText);
            }

            // Display options
            OnNodeDisplayed?.Invoke(node);
            DisplayOptions(node.options);
        }

        private void DisplayOptions(List<DialogueOption> options)
        {
            // Clear existing options
            if (responseContainer != null)
            {
                foreach (Transform child in responseContainer)
                {
                    Destroy(child.gameObject);
                }
            }

            int index = 0;
            foreach (var option in options)
            {
                // Check if option requires a flag
                if (!string.IsNullOrEmpty(option.requiredFlag))
                {
                    if (!StoryScriptEngine.Instance?.GetStoryFlag(option.requiredFlag) ?? true)
                    {
                        continue;
                    }
                }

                int capturedIndex = index;

                // Create button
                if (responseContainer != null && responseButtonPrefab != null)
                {
                    var btn = Instantiate(responseButtonPrefab, responseContainer);
                    var tmp = btn.GetComponentInChildren<TMPro.TextMeshProUGUI>();
                    if (tmp != null) tmp.text = option.text;

                    var button = btn.GetComponent<UnityEngine.UI.Button>();
                    if (button != null)
                    {
                        button.onClick.AddListener(() => SelectOption(capturedIndex));
                    }
                }

                index++;
            }

            // Always ensure at least one exit option
            if (index == 0)
            {
                // Add fallback exit
                if (responseContainer != null && responseButtonPrefab != null)
                {
                    var btn = Instantiate(responseButtonPrefab, responseContainer);
                    var tmp = btn.GetComponentInChildren<TMPro.TextMeshProUGUI>();
                    if (tmp != null) tmp.text = "[Continue]";

                    var button = btn.GetComponent<UnityEngine.UI.Button>();
                    if (button != null)
                    {
                        button.onClick.AddListener(() => EndDialogue());
                    }
                }
            }
        }

        /// <summary>
        /// Called when the player selects an option.
        /// </summary>
        public void SelectOption(int optionIndex)
        {
            if (currentNode == null || optionIndex >= currentNode.options.Count) return;

            var option = currentNode.options[optionIndex];

            // Execute select actions
            ExecuteActions(option.onSelectActions);

            // Execute quest actions
            if (option.advancesQuest && !string.IsNullOrEmpty(option.questId))
            {
                AdvanceQuest(option);
            }

            // Execute flag changes
            if (!string.IsNullOrEmpty(option.setsFlag))
            {
                StoryScriptEngine.Instance?.SetStoryFlag(option.setsFlag, true);
            }

            // Execute item grants
            if (!string.IsNullOrEmpty(option.grantsItem))
            {
                InventoryManager.Instance?.AddItem(option.grantsItem, 1);
            }

            // Execute reputation changes
            if (option.reputationChange != 0)
            {
                WorldStateService.Instance?.ModifyReputation(option.reputationChange);
            }

            // Execute emotion changes
            if (!string.IsNullOrEmpty(option.emotionChange))
            {
                // TODO: Set NPC emotion
            }

            OnOptionSelected?.Invoke(option, optionIndex);

            // Execute exit actions
            ExecuteActions(currentNode.onExitActions);

            // Move to next node or end
            if (option.isExitOption || string.IsNullOrEmpty(option.targetNodeId))
            {
                EndDialogue();
            }
            else
            {
                var nextNode = activeTree.GetNode(option.targetNodeId);
                if (nextNode != null)
                {
                    DisplayNode(nextNode);
                }
                else
                {
                    // Node not found - end dialogue
                    EndDialogue();
                }
            }
        }

        private void AdvanceQuest(DialogueOption option)
        {
            var qm = QuestManager.Instance;
            if (qm == null) return;

            switch (option.questAction)
            {
                case "accept":
                    qm.AcceptQuest(option.questId);
                    break;
                case "complete":
                    var quest = qm.GetQuest(option.questId);
                    if (quest != null)
                    {
                        quest.status = QuestStatus.Completed;
                        qm.OnQuestCompleted?.Invoke(quest);
                    }
                    break;
                case "update":
                    if (!string.IsNullOrEmpty(option.questObjective))
                    {
                        qm.UpdateObjective(option.questId, option.questObjective);
                    }
                    break;
            }
        }

        private void ExecuteActions(List<DialogueAction> actions)
        {
            foreach (var action in actions)
            {
                ExecuteAction(action);
            }
        }

        private void ExecuteAction(DialogueAction action)
        {
            switch (action.actionType)
            {
                case DialogueActionType.AcceptQuest:
                    QuestManager.Instance?.AcceptQuest(action.parameter);
                    break;
                case DialogueActionType.CompleteQuest:
                    var q = QuestManager.Instance?.GetQuest(action.parameter);
                    if (q != null)
                    {
                        q.status = QuestStatus.Completed;
                    }
                    break;
                case DialogueActionType.UpdateQuest:
                    var parts = action.parameter.Split('|');
                    if (parts.Length == 2)
                    {
                        QuestManager.Instance?.UpdateObjective(parts[0], parts[1]);
                    }
                    break;
                case DialogueActionType.SetFlag:
                    StoryScriptEngine.Instance?.SetStoryFlag(action.parameter, true);
                    break;
                case DialogueActionType.ClearFlag:
                    StoryScriptEngine.Instance?.SetStoryFlag(action.parameter, false);
                    break;
                case DialogueActionType.GrantItem:
                    InventoryManager.Instance?.AddItem(action.parameter, 1);
                    break;
                case DialogueActionType.RemoveItem:
                    // TODO: Remove item
                    break;
                case DialogueActionType.ChangeReputation:
                    if (int.TryParse(action.parameter, out int rep))
                    {
                        WorldStateService.Instance?.ModifyReputation(rep);
                    }
                    break;
                case DialogueActionType.ChangeEmotion:
                    // TODO: Set emotion
                    break;
                case DialogueActionType.Teleport:
                    var player = GameObject.FindGameObjectWithTag("Player");
                    if (player != null)
                    {
                        var target = GameObject.Find(action.parameter);
                        if (target != null)
                        {
                            player.transform.position = target.transform.position;
                        }
                    }
                    break;
                case DialogueActionType.PlayCutscene:
                    CutsceneManager.Instance?.PlayCutscene(action.parameter);
                    break;
                case DialogueActionType.EndConversation:
                    EndDialogue();
                    break;
                case DialogueActionType.SetStoryFlag:
                    if (!string.IsNullOrEmpty(action.secondaryParameter))
                    {
                        StoryScriptEngine.Instance?.SetStoryFlag(action.parameter, action.secondaryParameter == "true");
                    }
                    break;
                case DialogueActionType.PlayAudio:
                    // TODO: Play audio
                    break;
                case DialogueActionType.ChangeWeather:
                    if (Enum.TryParse<WorldStateService.Weather>(action.parameter, out var weather))
                    {
                        WorldStateService.Instance?.SetWeather(weather);
                    }
                    break;
                case DialogueActionType.ChangeTime:
                    if (Enum.TryParse<WorldStateService.TimeOfDay>(action.parameter, out var time))
                    {
                        WorldStateService.Instance?.SetTimeOfDay(time);
                    }
                    break;
                default:
                    Debug.LogWarning($"[DialogueTreeRunner] Unknown action type: {action.actionType}");
                    break;
            }
        }

        public void EndDialogue()
        {
            isInDialogue = false;
            activeTree = null;
            currentNode = null;

            // Clear UI
            if (dialogueUI != null) dialogueUI.Hide();
            if (responseContainer != null)
            {
                foreach (Transform child = responseContainer)
                {
                    Destroy(child.gameObject);
                }
            }

            OnDialogueEnded?.Invoke(activeTree);
            onDialogueComplete?.Invoke();
            onDialogueComplete = null;
        }

        public bool IsInDialogue => isInDialogue;
        public DialogueTree ActiveTree => activeTree;
        public DialogueTreeNode CurrentNode => currentNode;
    }

    /// <summary>
    /// Registry of all dialogue tree assets by ID.
    /// </summary>
    public class DialogueTreeRegistry : MonoBehaviour
    {
        public static DialogueTreeRegistry Instance { get; private set; }

        public List<DialogueTree> allTrees = new List<DialogueTree>();

        private Dictionary<string, DialogueTree> lookup = new Dictionary<string, DialogueTree>();

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);
            RebuildLookup();
        }

        public void RebuildLookup()
        {
            lookup.Clear();
            foreach (var tree in allTrees)
            {
                if (tree != null && !string.IsNullOrEmpty(tree.treeId))
                {
                    lookup[tree.treeId] = tree;
                }
            }
        }

        public DialogueTree GetTree(string id)
        {
            return lookup.TryGetValue(id, out var tree) ? tree : null;
        }
    }
}
