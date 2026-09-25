using UnityEngine;
using System.Collections.Generic;
using System.Linq;
using TMPro;

namespace UnreliableProphecy
{
    /// <summary>
    /// Quest data structure matching the production package specs.
    /// </summary>
    [System.Serializable]
    public class Quest
    {
        public string id;
        public string name;
        public QuestType type;
        public QuestStatus status;
        public List<QuestObjective> objectives = new List<QuestObjective>();
        public List<string> rewards = new List<string>();
        public string region;
        public int priority; // 0 = main, 1 = side, etc.
    }

    public enum QuestType { Main, Side, Daily, Challenge, Personal }
    public enum QuestStatus { NotStarted, Active, Completed, Failed, TurnedIn }

    [System.Serializable]
    public class QuestObjective
    {
        public string description;
        public bool isCompleted;
        public int currentAmount;
        public int targetAmount;
        public ObjectiveType type;
    }

    public enum ObjectiveType { Kill, Collect, Talk, ReachLocation, UseItem, Deliver, Craft }

    /// <summary>
    /// Quest Manager - handles quest tracking, updates, and UI events.
    /// Matches production package: Quest Tracker live updates, acceptance, completion, turn-in.
    /// </summary>
    public class QuestManager : MonoBehaviour
    {
        public static QuestManager Instance { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureExists()
        {
            if (Instance == null)
            {
                var go = new GameObject(typeof(QuestManager).Name);
                Instance = go.AddComponent<QuestManager>();
            }
        }

        [Header("Quest Data")]
        public List<Quest> allQuests = new List<Quest>();
        public List<Quest> activeQuests = new List<Quest>();
        public List<Quest> completedQuests = new List<Quest>();

        [Header("Events")]
        public System.Action<Quest> OnQuestAccepted;
        public System.Action<Quest> OnQuestUpdated;
        public System.Action<Quest> OnQuestCompleted;
        public System.Action<Quest> OnQuestTurnedIn;
        public System.Action<QuestObjective> OnObjectiveUpdated;

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            InitializeQuests();
        }

        void InitializeQuests()
        {
            // Quietvale Tutorial Quests (10 steps)
            allQuests.Add(new Quest
            {
                id = "T01",
                name = "The First Filing",
                type = QuestType.Main,
                status = QuestStatus.NotStarted,
                region = "Quietvale",
                priority = 0,
                objectives = new List<QuestObjective>
                {
                    new QuestObjective { description = "Speak to the Old Wizard", type = ObjectiveType.Talk, targetAmount = 1 },
                    new QuestObjective { description = "Accept the Prophecy Binder", type = ObjectiveType.UseItem, targetAmount = 1 },
                    new QuestObjective { description = "File your first form (Form 1-A)", type = ObjectiveType.UseItem, targetAmount = 1 },
                    new QuestObjective { description = "Stamp the form", type = ObjectiveType.UseItem, targetAmount = 1 },
                    new QuestObjective { description = "Return to Wizard", type = ObjectiveType.Talk, targetAmount = 1 }
                },
                rewards = new List<string> { "Binder Access", "First Stamp" }
            });

            allQuests.Add(new Quest
            {
                id = "T02",
                name = "Ink & Parchment",
                type = QuestType.Main,
                status = QuestStatus.NotStarted,
                region = "Quietvale",
                priority = 0,
                objectives = new List<QuestObjective>
                {
                    new QuestObjective { description = "Collect 3 Ink Vials", type = ObjectiveType.Collect, targetAmount = 3 },
                    new QuestObjective { description = "Collect 5 Parchment Sheets", type = ObjectiveType.Collect, targetAmount = 5 },
                    new QuestObjective { description = "Deliver to Desk Clerk", type = ObjectiveType.Deliver, targetAmount = 1 }
                },
                rewards = new List<string> { "Ink Well", "Parchment Stack" }
            });

            // Bureaucracy Hills Main Quests
            allQuests.Add(new Quest
            {
                id = "M01",
                name = "Permit to Proceed",
                type = QuestType.Main,
                status = QuestStatus.NotStarted,
                region = "Bureaucracy Hills",
                priority = 0,
                objectives = new List<QuestObjective>
                {
                    new QuestObjective { description = "Find the Permit Office", type = ObjectiveType.ReachLocation, targetAmount = 1 },
                    new QuestObjective { description = "Submit Form 47-B", type = ObjectiveType.UseItem, targetAmount = 1 },
                    new QuestObjective { description = "Wait for Processing", type = ObjectiveType.Talk, targetAmount = 1 },
                    new QuestObjective { description = "Receive Permit", type = ObjectiveType.Collect, targetAmount = 1 }
                },
                rewards = new List<string> { "Travel Permit", "Hills Access" }
            });

            allQuests.Add(new Quest
            {
                id = "M02",
                name = "The Misplaced Amendment",
                type = QuestType.Main,
                status = QuestStatus.NotStarted,
                region = "Bureaucracy Hills",
                priority = 0,
                objectives = new List<QuestObjective>
                {
                    new QuestObjective { description = "Search Filing Cabinet 3", type = ObjectiveType.Collect, targetAmount = 1 },
                    new QuestObjective { description = "Decode the Amendment", type = ObjectiveType.UseItem, targetAmount = 1 },
                    new QuestObjective { description = "Present to Magistrate", type = ObjectiveType.Talk, targetAmount = 1 }
                },
                rewards = new List<string> { "Amendment #1", "Guidebook Entry" }
            });

            allQuests.Add(new Quest
            {
                id = "M03",
                name = "Final Stamp",
                type = QuestType.Main,
                status = QuestStatus.NotStarted,
                region = "Bureaucracy Hills",
                priority = 0,
                objectives = new List<QuestObjective>
                {
                    new QuestObjective { description = "Complete Final Form", type = ObjectiveType.UseItem, targetAmount = 1 },
                    new QuestObjective { description = "Receive Grand Stamp", type = ObjectiveType.Collect, targetAmount = 1 },
                    new QuestObjective { description = "Exit the Hills", type = ObjectiveType.ReachLocation, targetAmount = 1 }
                },
                rewards = new List<string> { "Grand Stamp", "Game Complete" }
            });

            // Side Quest
            allQuests.Add(new Quest
            {
                id = "S01",
                name = "Lost Ledger",
                type = QuestType.Side,
                status = QuestStatus.NotStarted,
                region = "Bureaucracy Hills",
                priority = 1,
                objectives = new List<QuestObjective>
                {
                    new QuestObjective { description = "Find 3 Ledger Pages", type = ObjectiveType.Collect, targetAmount = 3 },
                    new QuestObjective { description = "Return to Archivist", type = ObjectiveType.Talk, targetAmount = 1 }
                },
                rewards = new List<string> { "Ledger Page", "Bonus Stamp" }
            });

            // Amendment Quest
            allQuests.Add(new Quest
            {
                id = "AMD01",
                name = "The First Amendment",
                type = QuestType.Main,
                status = QuestStatus.NotStarted,
                region = "Bureaucracy Hills",
                priority = 0,
                objectives = new List<QuestObjective>
                {
                    new QuestObjective { description = "Obtain Amendment Form", type = ObjectiveType.Collect, targetAmount = 1 },
                    new QuestObjective { description = "Fill Amendment", type = ObjectiveType.UseItem, targetAmount = 1 },
                    new QuestObjective { description = "Stamp Amendment", type = ObjectiveType.UseItem, targetAmount = 1 }
                },
                rewards = new List<string> { "Amendment #1", "Guidebook Entry", "Banter Unlock" }
            });
        }

        public Quest GetQuest(string id)
        {
            return allQuests.FirstOrDefault(q => q.id == id);
        }

        public void AcceptQuest(string questId)
        {
            var quest = GetQuest(questId);
            if (quest == null || quest.status != QuestStatus.NotStarted) return;

            quest.status = QuestStatus.Active;
            activeQuests.Add(quest);
            OnQuestAccepted?.Invoke(quest);
            Debug.Log($"Quest accepted: {quest.name}");
        }

        public void UpdateObjective(string questId, string objectiveDescription, int amount = 1)
        {
            var quest = GetQuest(questId);
            if (quest == null) return;

            var obj = quest.objectives.FirstOrDefault(o => o.description == objectiveDescription);
            if (obj == null || obj.isCompleted) return;

            obj.currentAmount = Mathf.Min(obj.currentAmount + amount, obj.targetAmount);
            if (obj.currentAmount >= obj.targetAmount)
            {
                obj.isCompleted = true;
            }

            OnObjectiveUpdated?.Invoke(obj);
            CheckQuestCompletion(quest);
        }

        void CheckQuestCompletion(Quest quest)
        {
            if (quest.objectives.All(o => o.isCompleted))
            {
                quest.status = QuestStatus.Completed;
                activeQuests.Remove(quest);
                completedQuests.Add(quest);
                OnQuestCompleted?.Invoke(quest);
                Debug.Log($"Quest completed: {quest.name}");
            }
        }

        public void TurnInQuest(string questId)
        {
            var quest = completedQuests.FirstOrDefault(q => q.id == questId);
            if (quest == null) return;

            quest.status = QuestStatus.TurnedIn;
            completedQuests.Remove(quest);
            OnQuestTurnedIn?.Invoke(quest);

            // Grant rewards
            foreach (var reward in quest.rewards)
            {
                Debug.Log($"Reward granted: {reward}");
                // TODO: Integrate with Inventory/Guidebook systems
            }

            // Auto-accept next main quest if applicable
            if (quest.id == "M01") AcceptQuest("M02");
            else if (quest.id == "M02") AcceptQuest("M03");
            else if (quest.id == "M03") AcceptQuest("AMD01");
        }

        public List<Quest> GetActiveQuests() => activeQuests;
        public List<Quest> GetQuestsByRegion(string region) => allQuests.Where(q => q.region == region).ToList();
        public List<Quest> GetMainQuests() => activeQuests.Where(q => q.type == QuestType.Main).ToList();
        public List<Quest> GetSideQuests() => activeQuests.Where(q => q.type == QuestType.Side).ToList();

        public void RefreshQuestLists()
        {
            // Called after loading save data to ensure lists are properly synchronized
        }

        public void Reset()
        {
            allQuests.Clear();
            activeQuests.Clear();
            completedQuests.Clear();
            InitializeQuests();
        }
    }

    /// <summary>
    /// Quest Tracker UI - parchment-styled tracker matching production package UI specs.
    /// </summary>
    [RequireComponent(typeof(Canvas))]
    public class QuestTrackerUI : MonoBehaviour
    {
        [Header("UI References")]
        public Transform questListContainer;
        public GameObject questEntryPrefab;
        public GameObject objectiveEntryPrefab;

        [Header("Styling")]
        public Font parchmentFont;
        public Color mainQuestColor = new Color(0.9f, 0.85f, 0.7f);
        public Color sideQuestColor = new Color(0.75f, 0.7f, 0.6f);
        public Color completedColor = new Color(0.5f, 0.7f, 0.5f);
        public Color amendmentColor = new Color(0.9f, 0.3f, 0.2f);

        private Canvas canvas;

        void Start()
        {
            canvas = GetComponent<Canvas>();
            QuestManager.Instance.OnQuestAccepted += _ => RefreshUI();
            QuestManager.Instance.OnQuestUpdated += _ => RefreshUI();
            QuestManager.Instance.OnQuestCompleted += _ => RefreshUI();
            QuestManager.Instance.OnQuestTurnedIn += _ => RefreshUI();
            QuestManager.Instance.OnObjectiveUpdated += _ => RefreshUI();

            RefreshUI();
        }

        void OnDestroy()
        {
            if (QuestManager.Instance != null)
            {
                QuestManager.Instance.OnQuestAccepted -= _ => RefreshUI();
                QuestManager.Instance.OnQuestUpdated -= _ => RefreshUI();
                QuestManager.Instance.OnQuestCompleted -= _ => RefreshUI();
                QuestManager.Instance.OnQuestTurnedIn -= _ => RefreshUI();
                QuestManager.Instance.OnObjectiveUpdated -= _ => RefreshUI();
            }
        }

        void RefreshUI()
        {
            // Clear existing entries
            foreach (Transform child in questListContainer)
                Destroy(child.gameObject);

            // Main quests first (bold)
            var mainQuests = QuestManager.Instance.GetMainQuests();
            foreach (var quest in mainQuests)
            {
                CreateQuestEntry(quest, true);
            }

            // Side quests below
            var sideQuests = QuestManager.Instance.GetSideQuests();
            foreach (var quest in sideQuests)
            {
                CreateQuestEntry(quest, false);
            }
        }

        void CreateQuestEntry(Quest quest, bool isMain)
        {
            var entry = Instantiate(questEntryPrefab, questListContainer);
            var texts = entry.GetComponentsInChildren<TextMeshProUGUI>();
            if (texts.Length > 0)
            {
                texts[0].text = quest.name;
                texts[0].color = isMain ? mainQuestColor : sideQuestColor;
                if (quest.status == QuestStatus.Completed || quest.status == QuestStatus.TurnedIn)
                    texts[0].color = completedColor;
                if (quest.id.StartsWith("AMD"))
                    texts[0].color = amendmentColor;
            }

            // Add objectives
            foreach (var obj in quest.objectives)
            {
                var objEntry = Instantiate(objectiveEntryPrefab, entry.transform);
                var objTexts = objEntry.GetComponentsInChildren<TextMeshProUGUI>();
                if (objTexts.Length > 0)
                {
                    objTexts[0].text = $"  - {obj.description} ({obj.currentAmount}/{obj.targetAmount})";
                    objTexts[0].color = obj.isCompleted ? completedColor : (isMain ? mainQuestColor : sideQuestColor);
                }
            }
        }
    }
}