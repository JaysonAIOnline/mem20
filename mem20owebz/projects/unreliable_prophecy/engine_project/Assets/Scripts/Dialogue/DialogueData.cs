using UnityEngine;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// ScriptableObject containing all dialogue data for one NPC.
    /// Created per NPC archetype. Loaded by DialogueManager at runtime.
    /// </summary>
    [CreateAssetMenu(fileName = "DialogueData", menuName = "Unreliable Prophecy/Dialogue Data", order = 0)]
    public class DialogueData : ScriptableObject
    {
        [Header("NPC Identity")]
        public string npcId;
        public string npcDisplayName;
        public string npcRole;
        [TextArea(2, 4)]
        public string coreBackstory;
        [TextArea(2, 4)]
        public string personalityTraits;
        [TextArea(2, 4)]
        public string speechPattern;

        [Header("Dialogue Lines")]
        public List<string> greetings = new List<string>();
        public List<string> idleChatter = new List<string>();
        public List<string> farewells = new List<string>();
        public List<string> reactiveComments = new List<string>();

        [Header("Responses (player can pick one to continue)")]
        public List<string> playerResponses = new List<string>();

        public string GetRandomLine(List<string> list)
        {
            if (list == null || list.Count == 0) return "";
            return list[Random.Range(0, list.Count)];
        }
    }
}