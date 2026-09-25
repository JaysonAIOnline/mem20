using UnityEngine;
using System;
using System.Collections.Generic;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Centralized world state tracker for dynamic dialogue evaluation.
    /// Tracks: time of day, weather, reputation, quest states, recent player actions,
    /// NPC emotional states, and proximity information.
    /// </summary>
    public class WorldStateService : MonoBehaviour
    {
        public static WorldStateService Instance { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureExists()
        {
            if (Instance == null)
            {
                var go = new GameObject(typeof(WorldStateService).Name);
                Instance = go.AddComponent<WorldStateService>();
            }
        }

        // === Time of Day ===
        public enum TimeOfDay { Dawn, Morning, Afternoon, Evening, Night }
        [SerializeField] private TimeOfDay currentTime = TimeOfDay.Morning;
        public TimeOfDay CurrentTime => currentTime;

        // === Weather ===
        public enum Weather { Clear, Rainy, Stormy, Foggy, Snow, Heatwave }
        [SerializeField] private Weather currentWeather = Weather.Clear;
        public Weather CurrentWeather => currentWeather;

        // === Reputation ===
        public enum ReputationTier { Unknown, Acquaintance, Friend, Hero, Feared, Villain }
        [SerializeField] private int reputationPoints = 0;
        public int ReputationPoints => reputationPoints;
        public ReputationTier CurrentReputation => reputationPoints <= -40 ? ReputationTier.Villain
            : reputationPoints >= 60 ? ReputationTier.Feared
            : reputationPoints >= 30 ? ReputationTier.Friend
            : reputationPoints >= 10 ? ReputationTier.Acquaintance
            : ReputationTier.Unknown;

        // === Recent Player Actions ===
        [Serializable]
        public class PlayerAction
        {
            public string category; // HELPED_TOWN, HARMED_TOWN, EXPLORED_DANGEROUS, GAINED_ITEM, SPENT_GOLD, SPREAD_RUMOR, BROKE_LAW
            public float timestamp;
            public float relevance; // decays over time
        }
        private List<PlayerAction> recentActions = new List<PlayerAction>();
        private const float ACTION_DECAY_HOURS = 24f;

        // === NPC Emotional States ===
        public enum Emotion { Ecstatic, Happy, Neutral, Concerned, Distressed, Angry }
        private Dictionary<string, Emotion> npcEmotions = new Dictionary<string, Emotion>();

        // === Proximity ===
        public enum Proximity { Alone, NearAlly, NearEnemy, NearAuthority, NearCrowd }

        // === Events ===
        public event Action OnWorldStateChanged;

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
            // Decay old actions
            float now = Time.time;
            recentActions.RemoveAll(a => (now - a.timestamp) > ACTION_DECAY_HOURS * 3600f);
        }

        // === Public API ===

        public void SetTimeOfDay(TimeOfDay time)
        {
            currentTime = time;
            OnWorldStateChanged?.Invoke();
        }

        public void SetWeather(Weather weather)
        {
            currentWeather = weather;
            OnWorldStateChanged?.Invoke();
        }

        public void ModifyReputation(int delta)
        {
            reputationPoints += delta;
            OnWorldStateChanged?.Invoke();
        }

        public void RecordAction(string category, float relevance = 1f)
        {
            recentActions.Add(new PlayerAction
            {
                category = category,
                timestamp = Time.time,
                relevance = relevance
            });
            OnWorldStateChanged?.Invoke();
        }

        public List<string> GetRecentActionCategories()
        {
            return recentActions.Select(a => a.category).Distinct().ToList();
        }

        public void SetNpcEmotion(string npcId, Emotion emotion)
        {
            npcEmotions[npcId] = emotion;
            OnWorldStateChanged?.Invoke();
        }

        public Emotion GetNpcEmotion(string npcId)
        {
            return npcEmotions.TryGetValue(npcId, out var e) ? e : Emotion.Neutral;
        }

        /// <summary>
        /// Builds a complete state vector for a given NPC interaction.
        /// </summary>
        public DialogueStateVector BuildStateVector(string npcId, string questId = null)
        {
            var qm = QuestManager.Instance;
            string questState = "QUEST_NOT_OFFERED";
            if (qm != null && !string.IsNullOrEmpty(questId))
            {
                var quest = qm.GetQuest(questId);
                if (quest != null)
                {
                    questState = quest.status switch
                    {
                        QuestStatus.NotStarted => "QUEST_NOT_OFFERED",
                        QuestStatus.Active => "QUEST_ACTIVE",
                        QuestStatus.Completed => "QUEST_COMPLETED",
                        QuestStatus.TurnedIn => "QUEST_COMPLETED",
                        QuestStatus.Failed => "QUEST_FAILED",
                        _ => "QUEST_NOT_OFFERED"
                    };
                }
            }

            return new DialogueStateVector
            {
                reputationTier = CurrentReputation,
                questState = questState,
                timePeriod = currentTime,
                weather = currentWeather,
                recentActions = GetRecentActionCategories(),
                npcEmotion = GetNpcEmotion(npcId),
                proximity = Proximity.Alone // default, can be updated per-NPC
            };
        }

        public void Reset()
        {
            currentTime = TimeOfDay.Morning;
            currentWeather = Weather.Clear;
            reputationPoints = 0;
            recentActions.Clear();
            npcEmotions.Clear();
        }
    }

    /// <summary>
    /// Immutable snapshot of world state at a moment in time for dialogue evaluation.
    /// </summary>
    [Serializable]
    public struct DialogueStateVector
    {
        public WorldStateService.ReputationTier reputationTier;
        public string questState;
        public WorldStateService.TimeOfDay timePeriod;
        public WorldStateService.Weather weather;
        public List<string> recentActions;
        public WorldStateService.Emotion npcEmotion;
        public WorldStateService.Proximity proximity;
    }
}