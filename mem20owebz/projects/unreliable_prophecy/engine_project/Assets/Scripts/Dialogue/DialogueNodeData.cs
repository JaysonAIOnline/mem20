using UnityEngine;
using System;
using System.Collections.Generic;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Data structure for a conditional dialogue node.
    /// Each node represents one possible line with conditions that must be met.
    /// </summary>
    [Serializable]
    public class DialogueNodeData
    {
        public string nodeId;
        public string npcId;
        public string slot; // greeting, idle, farewell, reactive
        public string text;
        public DialogueCondition conditions;
        public int priority; // higher = evaluated first
        public List<string> suppressWhen; // condition strings like "reputation:Villain"
        public List<DialogueVariation> variations;
    }

    [Serializable]
    public class DialogueCondition
    {
        public List<string> reputation; // Unknown, Acquaintance, Friend, Hero, Feared, Villain
        public List<string> time; // Dawn, Morning, Afternoon, Evening, Night
        public List<string> weather; // Clear, Rainy, Stormy, Foggy, Snow, Heatwave
        public List<string> questState; // QUEST_NOT_OFFERED, QUEST_OFFERED, QUEST_ACTIVE, etc.
        public List<string> proximity; // ALONE, NEAR_ALLY, NEAR_ENEMY, NEAR_AUTHORITY, NEAR_CROWD
        public List<string> recentActions; // HELPED_TOWN, HARMED_TOWN, etc.
        public List<string> npcEmotion; // ECSTATIC, HAPPY, NEUTRAL, CONCERNED, DISTRESSED, ANGRY
    }

    [Serializable]
    public class DialogueVariation
    {
        public string text;
        public DialogueCondition conditions;
    }

    /// <summary>
    /// Evaluates dialogue nodes against current world state to select the best line.
    /// Implements the priority-based rule evaluation from the trigger system design.
    /// </summary>
    public class DialogueEvaluator
    {
        private List<DialogueNodeData> nodes = new List<DialogueNodeData>();

        public void RegisterNode(DialogueNodeData node)
        {
            nodes.Add(node);
        }

        public void RegisterNodes(IEnumerable<DialogueNodeData> newNodes)
        {
            nodes.AddRange(newNodes);
        }

        public void Clear() => nodes.Clear();

        /// <summary>
        /// Evaluates all nodes for a given NPC and slot, returns the highest-priority matching line.
        /// </summary>
        public string Evaluate(string npcId, string slot, DialogueStateVector state, string fallbackLine)
        {
            var candidates = nodes
                .Where(n => n.npcId == npcId && n.slot == slot)
                .Where(n => !IsSuppressed(n, state))
                .Where(n => MatchesConditions(n.conditions, state))
                .OrderByDescending(n => n.priority)
                .ToList();

            if (candidates.Count == 0)
                return fallbackLine;

            var best = candidates.First();

            // Check variations for a more specific match
            if (best.variations != null)
            {
                var variation = best.variations
                    .Where(v => MatchesConditions(v.conditions, state))
                    .OrderByDescending(v => CountMatches(v.conditions, state))
                    .FirstOrDefault();

                if (variation != null)
                    return variation.text;
            }

            return best.text;
        }

        private bool IsSuppressed(DialogueNodeData node, DialogueStateVector state)
        {
            if (node.suppressWhen == null) return false;

            foreach (var rule in node.suppressWhen)
            {
                var parts = rule.Split(':');
                if (parts.Length != 2) continue;

                string key = parts[0].ToLower();
                string value = parts[1];

                switch (key)
                {
                    case "reputation":
                        if (state.reputationTier.ToString() == value) return true;
                        break;
                    case "weather":
                        if (state.weather.ToString() == value) return true;
                        break;
                    case "time":
                        if (state.timePeriod.ToString() == value) return true;
                        break;
                    case "quest":
                        if (state.questState == value) return true;
                        break;
                    case "emotion":
                        if (state.npcEmotion.ToString().ToUpper() == value.ToUpper()) return true;
                        break;
                }
            }
            return false;
        }

        private bool MatchesConditions(DialogueCondition cond, DialogueStateVector state)
        {
            if (cond == null) return true;

            if (cond.reputation != null && cond.reputation.Count > 0)
                if (!cond.reputation.Contains(state.reputationTier.ToString())) return false;

            if (cond.time != null && cond.time.Count > 0)
                if (!cond.time.Contains(state.timePeriod.ToString())) return false;

            if (cond.weather != null && cond.weather.Count > 0)
                if (!cond.weather.Contains(state.weather.ToString())) return false;

            if (cond.questState != null && cond.questState.Count > 0)
                if (!cond.questState.Contains(state.questState)) return false;

            if (cond.proximity != null && cond.proximity.Count > 0)
                if (!cond.proximity.Contains(state.proximity.ToString().ToUpper())) return false;

            if (cond.recentActions != null && cond.recentActions.Count > 0)
                if (!cond.recentActions.Any(a => state.recentActions.Contains(a))) return false;

            if (cond.npcEmotion != null && cond.npcEmotion.Count > 0)
                if (!cond.npcEmotion.Contains(state.npcEmotion.ToString().ToUpper())) return false;

            return true;
        }

        private int CountMatches(DialogueCondition cond, DialogueStateVector state)
        {
            int count = 0;
            if (cond.reputation?.Contains(state.reputationTier.ToString()) == true) count++;
            if (cond.time?.Contains(state.timePeriod.ToString()) == true) count++;
            if (cond.weather?.Contains(state.weather.ToString()) == true) count++;
            if (cond.questState?.Contains(state.questState) == true) count++;
            if (cond.proximity?.Contains(state.proximity.ToString().ToUpper()) == true) count++;
            if (cond.recentActions?.Any(a => state.recentActions.Contains(a)) == true) count++;
            if (cond.npcEmotion?.Contains(state.npcEmotion.ToString().ToUpper()) == true) count++;
            return count;
        }
    }
}