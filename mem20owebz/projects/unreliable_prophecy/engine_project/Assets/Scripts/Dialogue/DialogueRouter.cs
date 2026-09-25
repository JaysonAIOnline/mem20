using UnityEngine;
using System;
using System.Collections.Generic;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Quest-gated NPC dialogue routing system.
    /// Selects appropriate dialogue lines, trees, or quests based on the player's
    /// current quest state, story flags, chapter, and region.
    /// </summary>
    public class DialogueRouter : MonoBehaviour
    {
        public static DialogueRouter Instance { get; private set; }

        [Header("Routing")]
        public List<DialogueRoute> routes = new List<DialogueRoute>();

        [Header("Default Settings")]
        public bool logRoutingDecisions = false;

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
        /// Gets the appropriate dialogue for an NPC based on world state.
        /// Returns the most specific matching route, or a fallback.
        /// </summary>
        public DialogueResult GetDialogue(string npcId, string npcRole, string questId, Dictionary<string, bool> activeFlags)
        {
            var context = new DialogueContext
            {
                npcId = npcId,
                npcRole = npcRole,
                questId = questId,
                chapter = StoryScriptEngine.Instance?.GetActiveChapter()?.chapterId,
                region = GetCurrentRegion(),
                questState = GetQuestState(questId),
                storyFlags = activeFlags ?? new Dictionary<string, bool>()
            };

            // Score all matching routes
            var matchingRoutes = new List<DialogueRoute>();
            foreach (var route in routes)
            {
                if (route.Matches(context))
                {
                    matchingRoutes.Add(route);
                }
            }

            // Sort by priority (highest first)
            matchingRoutes.Sort((a, b) => b.priority.CompareTo(a.priority));

            if (matchingRoutes.Count > 0)
            {
                var best = matchingRoutes[0];

                if (logRoutingDecisions)
                    Debug.Log($"[DialogueRouter] NPC={npcId} Quest={questId} -> Route={best.routeId} (priority {best.priority})");

                return new DialogueResult
                {
                    routeId = best.routeId,
                    lines = best.lines,
                    questToOffer = best.questToOffer,
                    questAction = best.questAction,
                    questTarget = best.questTarget,
                    flagToSet = best.flagToSet,
                    priority = best.priority
                };
            }

            // No match - return default
            return new DialogueResult
            {
                routeId = "default",
                lines = GetDefaultLines(npcId),
                priority = 0
            };
        }

        /// <summary>
        /// Gets the current region the player is in.
        /// </summary>
        private string GetCurrentRegion()
        {
            var active = UnityEngine.SceneManagement.SceneManager.GetActiveScene().name;
            var id = SceneRegistry.GetIdentifierByName(active);
            if (!id.HasValue) return null;
            return SceneRegistry.GetRegionId(id.Value);
        }

        /// <summary>
        /// Gets the state of a quest as a string.
        /// </summary>
        private string GetQuestState(string questId)
        {
            var qm = QuestManager.Instance;
            if (qm == null || string.IsNullOrEmpty(questId)) return "NO_QUEST";

            var quest = qm.GetQuest(questId);
            if (quest == null) return "NOT_FOUND";

            return quest.status switch
            {
                QuestStatus.NotStarted => "NOT_STARTED",
                QuestStatus.Active => "ACTIVE",
                QuestStatus.Completed => "COMPLETED",
                QuestStatus.TurnedIn => "TURNED_IN",
                QuestStatus.Failed => "FAILED",
                _ => "UNKNOWN"
            };
        }

        /// <summary>
        /// Gets default lines for an NPC when no route matches.
        /// </summary>
        private List<string> GetDefaultLines(string npcId)
        {
            return new List<string> { "..." };
        }

        /// <summary>
        /// Registers a dialogue route at runtime.
        /// </summary>
        public void AddRoute(DialogueRoute route)
        {
            routes.Add(route);
        }

        /// <summary>
        /// Removes a route by ID.
        /// </summary>
        public void RemoveRoute(string routeId)
        {
            routes.RemoveAll(r => r.routeId == routeId);
        }

        /// <summary>
        /// Bulk-registers routes from a list.
        /// </summary>
        public void AddRoutes(IEnumerable<DialogueRoute> newRoutes)
        {
            routes.AddRange(newRoutes);
        }
    }

    /// <summary>
    /// Context for dialogue routing decisions.
    /// </summary>
    public class DialogueContext
    {
        public string npcId;
        public string npcRole;
        public string questId;
        public string chapter;
        public string region;
        public string questState;
        public Dictionary<string, bool> storyFlags;
    }

    /// <summary>
    /// Result of a dialogue routing decision.
    /// </summary>
    public class DialogueResult
    {
        public string routeId;
        public List<string> lines;
        public string questToOffer;
        public string questAction; // accept, update, complete
        public string questTarget; // quest ID or objective description
        public string flagToSet;
        public int priority;
    }

    /// <summary>
    /// A dialogue route - matches specific game state and returns appropriate dialogue.
    /// </summary>
    [Serializable]
    public class DialogueRoute
    {
        public string routeId;
        public int priority = 0;

        [Header("Conditions (ALL must match)")]
        public string requiredNpcId;
        public string requiredNpcRole; // quest_giver, companion, side_quest, etc.
        public string requiredChapter;
        public string requiredRegion;
        public string requiredQuestId;
        public string requiredQuestState; // NOT_STARTED, ACTIVE, COMPLETED, etc.
        public List<string> requiredFlags; // Story flags that must be set
        public List<string> excludedFlags; // Story flags that must NOT be set

        [Header("Output")]
        public List<string> lines = new List<string>();
        public string questToOffer;
        public string questAction; // accept, update, complete
        public string questTarget;
        public string flagToSet; // Flag set after this dialogue

        public bool Matches(DialogueContext context)
        {
            // Check NPC ID
            if (!string.IsNullOrEmpty(requiredNpcId) && context.npcId != requiredNpcId)
                return false;

            // Check NPC role
            if (!string.IsNullOrEmpty(requiredNpcRole) && context.npcRole != requiredNpcRole)
                return false;

            // Check chapter
            if (!string.IsNullOrEmpty(requiredChapter) && context.chapter != requiredChapter)
                return false;

            // Check region
            if (!string.IsNullOrEmpty(requiredRegion) && context.region != requiredRegion)
                return false;

            // Check quest state
            if (!string.IsNullOrEmpty(requiredQuestState))
            {
                if (!string.IsNullOrEmpty(requiredQuestId))
                {
                    // Check specific quest state
                    var questState = GetSpecificQuestState(requiredQuestId);
                    if (questState != requiredQuestState)
                        return false;
                }
                else
                {
                    // Check provided quest state
                    if (context.questState != requiredQuestState)
                        return false;
                }
            }

            // Check required flags
            if (requiredFlags != null)
            {
                foreach (var flag in requiredFlags)
                {
                    if (!context.storyFlags.TryGetValue(flag, out bool val) || !val)
                        return false;
                }
            }

            // Check excluded flags
            if (excludedFlags != null)
            {
                foreach (var flag in excludedFlags)
                {
                    if (context.storyFlags.TryGetValue(flag, out bool val) && val)
                        return false;
                }
            }

            return true;
        }

        private string GetSpecificQuestState(string questId)
        {
            var qm = QuestManager.Instance;
            if (qm == null) return "NOT_FOUND";
            var quest = qm.GetQuest(questId);
            if (quest == null) return "NOT_FOUND";
            return quest.status switch
            {
                QuestStatus.NotStarted => "NOT_STARTED",
                QuestStatus.Active => "ACTIVE",
                QuestStatus.Completed => "COMPLETED",
                QuestStatus.TurnedIn => "TURNED_IN",
                QuestStatus.Failed => "FAILED",
                _ => "UNKNOWN"
            };
        }
    }

    /// <summary>
    /// Quest-gated NPC dialogue routing with pre-built routes for common scenarios.
    /// </summary>
    public static class DialogueRouteFactory
    {
        /// <summary>
        /// Creates a route for an NPC who offers a quest.
        /// </summary>
        public static DialogueRoute CreateQuestGiverRoute(
            string routeId,
            string npcId,
            string questId,
            List<string> preQuestLines,
            List<string> activeQuestLines,
            List<string> postQuestLines,
            int priority = 0)
        {
            var route = new DialogueRoute
            {
                routeId = routeId,
                requiredNpcId = npcId,
                requiredNpcRole = "quest_giver",
                priority = priority,
                questToOffer = questId
            };

            // Pre-quest: not started or turned in
            if (preQuestLines != null)
            {
                route.lines = preQuestLines;
                route.questAction = "accept";
                route.questTarget = questId;
            }

            return route;
        }

        /// <summary>
        /// Creates a route that checks quest state and returns appropriate lines.
        /// </summary>
        public static List<DialogueRoute> CreateQuestStateRoutes(
            string npcId,
            string questId,
            List<string> preQuestLines,
            List<string> activeQuestLines,
            List<string> postQuestLines)
        {
            var routes = new List<DialogueRoute>();

            // Pre-quest route
            if (preQuestLines != null)
            {
                routes.Add(new DialogueRoute
                {
                    routeId = $"{npcId}_{questId}_pre",
                    requiredNpcId = npcId,
                    requiredQuestId = questId,
                    requiredQuestState = "NOT_STARTED",
                    lines = preQuestLines,
                    questToOffer = questId,
                    questAction = "accept",
                    questTarget = questId,
                    priority = 10
                });
            }

            // Active quest route
            if (activeQuestLines != null)
            {
                routes.Add(new DialogueRoute
                {
                    routeId = $"{npcId}_{questId}_active",
                    requiredNpcId = npcId,
                    requiredQuestId = questId,
                    requiredQuestState = "ACTIVE",
                    lines = activeQuestLines,
                    priority = 10
                });
            }

            // Post-quest route
            if (postQuestLines != null)
            {
                routes.Add(new DialogueRoute
                {
                    routeId = $"{npcId}_{questId}_post",
                    requiredNpcId = npcId,
                    requiredQuestId = questId,
                    requiredQuestState = "COMPLETED",
                    lines = postQuestLines,
                    priority = 10
                });
            }

            return routes;
        }

        /// <summary>
        /// Creates a route for an NPC that only appears when a story flag is set.
        /// </summary>
        public static DialogueRoute CreateFlagGatedRoute(
            string routeId,
            string npcId,
            string requiredFlag,
            List<string> lines,
            int priority = 5)
        {
            return new DialogueRoute
            {
                routeId = routeId,
                requiredNpcId = npcId,
                requiredFlags = new List<string> { requiredFlag },
                lines = lines,
                priority = priority
            };
        }

        /// <summary>
        /// Creates a route for chapter-specific NPC dialogue.
        /// </summary>
        public static DialogueRoute CreateChapterRoute(
            string routeId,
            string npcId,
            string chapterId,
            List<string> lines,
            int priority = 3)
        {
            return new DialogueRoute
            {
                routeId = routeId,
                requiredNpcId = npcId,
                requiredChapter = chapterId,
                lines = lines,
                priority = priority
            };
        }
    }

    /// <summary>
    /// ScriptableObject containing dialogue routes for a region or NPC.
    /// </summary>
    [CreateAssetMenu(fileName = "DialogueRouteData", menuName = "Unreliable Prophecy/Dialogue Route Data")]
    public class DialogueRouteData : ScriptableObject
    {
        public string routeDataId;
        public List<DialogueRoute> routes = new List<DialogueRoute>();
    }
}
