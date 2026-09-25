using UnityEngine;
using System.Collections.Generic;
using System.IO;

namespace UnreliableProphecy
{
    /// <summary>
    /// Loads dialogue JSON files from Resources/Dialogue/ and provides them to NPCs.
    /// Each JSON file maps to one NPC archetype.
    /// </summary>
    public class DialogueLoader : MonoBehaviour
    {
        public static DialogueLoader Instance { get; private set; }

        private Dictionary<string, DialogueData> loadedData = new Dictionary<string, DialogueData>();

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);
            LoadAllDialogue();
        }

        void LoadAllDialogue()
        {
            // Load all JSON files from Resources/Dialogue/
            TextAsset[] jsonFiles = Resources.LoadAll<TextAsset>("Dialogue");
            foreach (var file in jsonFiles)
            {
                try
                {
                    DialogueData parsed = JsonUtility.FromJson<DialogueData>(file.text);
                    if (parsed != null && !string.IsNullOrEmpty(parsed.npcId))
                    {
                        loadedData[parsed.npcId] = parsed;
                        Debug.Log($"[DialogueLoader] Loaded dialogue for: {parsed.npcId}");
                    }
                    else if (parsed != null)
                    {
                        // Use filename as npcId fallback
                        string npcId = System.IO.Path.GetFileNameWithoutExtension(file.name);
                        parsed.npcId = npcId;
                        loadedData[npcId] = parsed;
                        Debug.Log($"[DialogueLoader] Loaded dialogue for: {npcId}");
                    }
                    else
                    {
                        Debug.LogWarning($"[DialogueLoader] Failed to parse JSON from: {file.name}");
                    }
                }
                catch (System.Exception ex)
                {
                    Debug.LogError($"[DialogueLoader] Error loading {file.name}: {ex.Message}");
                }
            }
            Debug.Log($"[DialogueLoader] Total NPCs loaded: {loadedData.Count}");
        }

        public DialogueData GetDialogueData(string npcId)
        {
            if (loadedData.TryGetValue(npcId, out DialogueData data))
                return data;
            return null;
        }
    }
}
