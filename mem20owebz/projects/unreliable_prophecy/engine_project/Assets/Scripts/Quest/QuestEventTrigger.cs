using UnityEngine;
using System;
using System.Collections.Generic;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Quest Event Trigger system - region-based and event-based quest progression.
    /// Automatically fires sequences and quest actions when conditions are met.
    /// </summary>
    public class QuestEventTrigger : MonoBehaviour
    {
        public static QuestEventTrigger Instance { get; private set; }

        [Header("Settings")]
        public List<QuestEventEntry> events = new List<QuestEventEntry>();

        // Tracked state
        private HashSet<string> triggeredRegions = new HashSet<string>();
        private HashSet<string> triggeredEvents = new HashSet<string>();

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
            // Subscribe to game events
            var qm = QuestManager.Instance;
            if (qm != null)
            {
                qm.OnQuestCompleted += OnQuestCompleted;
                qm.OnQuestAccepted += OnQuestAccepted;
                qm.OnQuestTurnedIn += OnQuestTurnedIn;
            }

            var ss = StoryScriptEngine.Instance;
            if (ss != null)
            {
                ss.OnStoryFlagSet += OnStoryFlagSet;
            }
        }

        void OnDestroy()
        {
            var qm = QuestManager.Instance;
            if (qm != null)
            {
                qm.OnQuestCompleted -= OnQuestCompleted;
                qm.OnQuestAccepted -= OnQuestAccepted;
                qm.OnQuestTurnedIn -= OnQuestTurnedIn;
            }

            var ss = StoryScriptEngine.Instance;
            if (ss != null)
            {
                ss.OnStoryFlagSet -= OnStoryFlagSet;
            }
        }

        /// <summary>
        /// Called when a region is entered - fires any region-based triggers.
        /// </summary>
        public void OnRegionEntered(string regionId)
        {
            if (triggeredRegions.Contains(regionId)) return;
            triggeredRegions.Add(regionId);

            Debug.Log($"[QuestEventTrigger] Region entered: {regionId}");

            foreach (var evt in events)
            {
                if (evt.triggerType == QuestTriggerType.OnRegionEnter && evt.triggerData == regionId)
                {
                    FireEvent(evt);
                }
            }

            // Also notify StoryScriptEngine
            StoryScriptEngine.Instance?.CheckTrigger(SequenceTriggerType.OnRegionEnter, regionId);
        }

        /// <summary>
        /// Called when a region transition occurs.
        /// </summary>
        public void OnRegionTransition(string fromRegion, string toRegion)
        {
            string transitionId = $"{fromRegion}-GATE";

            Debug.Log($"[QuestEventTrigger] Region transition: {transitionId}");

            foreach (var evt in events)
            {
                if (evt.triggerType == QuestTriggerType.OnRegionTransition && evt.triggerData == transitionId)
                {
                    FireEvent(evt);
                }
            }

            StoryScriptEngine.Instance?.CheckTrigger(SequenceTriggerType.OnRegionTransition, transitionId);
        }

        private void OnQuestCompleted(Quest quest)
        {
            if (quest == null) return;

            foreach (var evt in events)
            {
                if (evt.triggerType == QuestTriggerType.OnQuestCompleted && evt.triggerData == quest.id)
                {
                    FireEvent(evt);
                }
            }

            StoryScriptEngine.Instance?.CheckTrigger(SequenceTriggerType.OnQuestCompleted, quest.id);
        }

        private void OnQuestAccepted(Quest quest)
        {
            if (quest == null) return;

            foreach (var evt in events)
            {
                if (evt.triggerType == QuestTriggerType.OnQuestAccepted && evt.triggerData == quest.id)
                {
                    FireEvent(evt);
                }
            }

            StoryScriptEngine.Instance?.CheckTrigger(SequenceTriggerType.OnQuestAccepted, quest.id);
        }

        private void OnQuestTurnedIn(Quest quest)
        {
            if (quest == null) return;

            foreach (var evt in events)
            {
                if (evt.triggerType == QuestTriggerType.OnQuestTurnedIn && evt.triggerData == quest.id)
                {
                    FireEvent(evt);
                }
            }
        }

        private void OnStoryFlagSet(string flag)
        {
            foreach (var evt in events)
            {
                if (evt.triggerType == QuestTriggerType.OnStoryFlagSet && evt.triggerData == flag)
                {
                    FireEvent(evt);
                }
            }

            StoryScriptEngine.Instance?.CheckTrigger(SequenceTriggerType.OnStoryFlagSet, flag);
        }

        /// <summary>
        /// Called when a waypoint is reached.
        /// </summary>
        public void OnWaypointReached(string waypointId)
        {
            foreach (var evt in events)
            {
                if (evt.triggerType == QuestTriggerType.OnWaypointReached && evt.triggerData == waypointId)
                {
                    FireEvent(evt);
                }
            }

            StoryScriptEngine.Instance?.CheckTrigger(SequenceTriggerType.OnWaypointReached, waypointId);
        }

        /// <summary>
        /// Called when an enemy is defeated.
        /// </summary>
        public void OnEnemyDefeated(string enemyId)
        {
            foreach (var evt in events)
            {
                if (evt.triggerType == QuestTriggerType.OnEnemyDefeated && evt.triggerData == enemyId)
                {
                    FireEvent(evt);
                }
            }

            StoryScriptEngine.Instance?.CheckTrigger(SequenceTriggerType.OnEnemyDefeated, enemyId);
        }

        /// <summary>
        /// Called when an item is collected.
        /// </summary>
        public void OnItemCollected(string itemId)
        {
            foreach (var evt in events)
            {
                if (evt.triggerType == QuestTriggerType.OnItemCollected && evt.triggerData == itemId)
                {
                    FireEvent(evt);
                }
            }

            StoryScriptEngine.Instance?.CheckTrigger(SequenceTriggerType.OnItemCollected, itemId);
        }

        private void FireEvent(QuestEventEntry evt)
        {
            if (triggeredEvents.Contains(evt.eventId)) return;
            triggeredEvents.Add(evt.eventId);

            Debug.Log($"[QuestEventTrigger] Firing event: {evt.eventId}");

            // Execute all quest actions
            foreach (var action in evt.actions)
            {
                ExecuteQuestAction(action);
            }

            // Execute sequence trigger if specified
            if (!string.IsNullOrEmpty(evt.sequenceId))
            {
                StoryScriptEngine.Instance?.TriggerSequence(evt.sequenceId);
            }

            // Execute cutscene if specified
            if (!string.IsNullOrEmpty(evt.cutsceneId))
            {
                CutsceneManager.Instance?.PlayCutscene(evt.cutsceneId);
            }
        }

        private void ExecuteQuestAction(QuestActionEntry action)
        {
            var qm = QuestManager.Instance;
            if (qm == null) return;

            switch (action.actionType)
            {
                case QuestActionType.AcceptQuest:
                    qm.AcceptQuest(action.targetId);
                    break;
                case QuestActionType.UpdateObjective:
                    qm.UpdateObjective(action.targetId, action.parameter);
                    break;
                case QuestActionType.CompleteQuest:
                    var quest = qm.GetQuest(action.targetId);
                    if (quest != null)
                    {
                        quest.status = QuestStatus.Completed;
                        qm.OnQuestCompleted?.Invoke(quest);
                    }
                    break;
                case QuestActionType.TurnInQuest:
                    qm.TurnInQuest(action.targetId);
                    break;
                case QuestActionType.GrantItem:
                    InventoryManager.Instance?.AddItem(action.targetId, action.quantity);
                    break;
                case QuestActionType.SetFlag:
                    StoryScriptEngine.Instance?.SetStoryFlag(action.targetId, true);
                    break;
                case QuestActionType.DisplayMessage:
                    Debug.Log($"[QuestMessage] {action.parameter}");
                    // TODO: Display in UI
                    break;
                case QuestActionType.PlayCutscene:
                    CutsceneManager.Instance?.PlayCutscene(action.targetId);
                    break;
                case QuestActionType.SpawnEnemy:
                    // TODO: Spawn enemy
                    Debug.Log($"[QuestEventTrigger] Spawn enemy: {action.targetId}");
                    break;
                case QuestActionType.ModifyReputation:
                    if (int.TryParse(action.parameter, out int rep))
                    {
                        WorldStateService.Instance?.ModifyReputation(rep);
                    }
                    break;
            }
        }

        /// <summary>
        /// Registers a quest event trigger at runtime.
        /// </summary>
        public void RegisterEvent(QuestEventEntry entry)
        {
            events.Add(entry);
        }

        /// <summary>
        /// Removes a quest event trigger at runtime.
        /// </summary>
        public void RemoveEvent(string eventId)
        {
            events.RemoveAll(e => e.eventId == eventId);
        }

        /// <summary>
        /// Resets all triggered state (e.g., on new game).
        /// </summary>
        public void ResetTriggers()
        {
            triggeredEvents.Clear();
            triggeredRegions.Clear();
        }
    }

    // === Data Structures ===

    [Serializable]
    public class QuestEventEntry
    {
        public string eventId;
        public string displayName;
        public QuestTriggerType triggerType;
        public string triggerData;
        public List<QuestActionEntry> actions = new List<QuestActionEntry>();
        public string sequenceId;
        public string cutsceneId;
        public bool fireOnce = true;
        public int priority;
    }

    public enum QuestTriggerType
    {
        OnRegionEnter,
        OnRegionTransition,
        OnQuestCompleted,
        OnQuestAccepted,
        OnQuestTurnedIn,
        OnWaypointReached,
        OnEnemyDefeated,
        OnItemCollected,
        OnStoryFlagSet,
        Manual
    }

    [Serializable]
    public class QuestActionEntry
    {
        public QuestActionType actionType;
        public string targetId;
        public string parameter;
        public int quantity;

        public QuestActionEntry() { }

        public QuestActionEntry(QuestActionType type, string target, string param = "", int qty = 1)
        {
            actionType = type;
            targetId = target;
            parameter = param;
            quantity = qty;
        }
    }

    public enum QuestActionType
    {
        AcceptQuest,
        UpdateObjective,
        CompleteQuest,
        TurnInQuest,
        GrantItem,
        SetFlag,
        DisplayMessage,
        PlayCutscene,
        SpawnEnemy,
        ModifyReputation
    }

    /// <summary>
    /// MonoBehaviour variant for placing quest events in scenes.
    /// </summary>
    public class QuestEventTriggerZone : MonoBehaviour
    {
        [Header("Trigger Settings")]
        public string eventId;
        public QuestTriggerType triggerType = QuestTriggerType.OnRegionEnter;
        public string triggerData;

        [Header("Quest Actions")]
        public List<QuestActionEntry> actions = new List<QuestActionEntry>();

        [Header("Options")]
        public bool autoFireOnStart = false;
        public bool requirePlayerTag = true;
        public string requiredQuestState;
        public string requiredFlag;

        private bool hasFired = false;

        void Start()
        {
            if (autoFireOnStart)
            {
                Fire();
            }
        }

        void OnTriggerEnter(Collider other)
        {
            if (requirePlayerTag && !other.CompareTag("Player")) return;
            Fire();
        }

        public void Fire()
        {
            if (hasFired) return;

            // Check required flag
            if (!string.IsNullOrEmpty(requiredFlag))
            {
                if (!StoryScriptEngine.Instance?.GetStoryFlag(requiredFlag) ?? true)
                {
                    return;
                }
            }

            // Check required quest state
            if (!string.IsNullOrEmpty(requiredQuestState))
            {
                var qm = QuestManager.Instance;
                if (qm != null)
                {
                    var quest = qm.GetQuest(requiredQuestState);
                    if (quest == null || quest.status != QuestStatus.Active)
                    {
                        return;
                    }
                }
            }

            hasFired = true;

            foreach (var action in actions)
            {
                ExecuteAction(action);
            }

            // Notify the global trigger system
            var qet = QuestEventTrigger.Instance;
            if (qet != null)
            {
                switch (triggerType)
                {
                    case QuestTriggerType.OnRegionEnter:
                        qet.OnRegionEntered(triggerData);
                        break;
                    case QuestTriggerType.OnWaypointReached:
                        qet.OnWaypointReached(triggerData);
                        break;
                    case QuestTriggerType.OnEnemyDefeated:
                        qet.OnEnemyDefeated(triggerData);
                        break;
                    case QuestTriggerType.OnItemCollected:
                        qet.OnItemCollected(triggerData);
                        break;
                }
            }
        }

        private void ExecuteAction(QuestActionEntry action)
        {
            var qm = QuestManager.Instance;

            switch (action.actionType)
            {
                case QuestActionType.AcceptQuest:
                    qm?.AcceptQuest(action.targetId);
                    break;
                case QuestActionType.UpdateObjective:
                    qm?.UpdateObjective(action.targetId, action.parameter);
                    break;
                case QuestActionType.GrantItem:
                    InventoryManager.Instance?.AddItem(action.targetId, action.quantity);
                    break;
                case QuestActionType.SetFlag:
                    StoryScriptEngine.Instance?.SetStoryFlag(action.targetId, true);
                    break;
                case QuestActionType.DisplayMessage:
                    Debug.Log($"[QuestMessage] {action.parameter}");
                    break;
            }
        }
    }
}
