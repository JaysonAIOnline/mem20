using UnityEngine;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Places NPCs in the town scene at logical positions tied to their roles.
    /// Run this in the editor or at scene start to populate the scene with NPCs.
    /// </summary>
    public class NPCPlacement : MonoBehaviour
    {
        [Header("Prefab")]
        public GameObject npcPrefab;

        [Header("Scene References")]
        public Transform npcParent;

        [Header("Positions")]
        public List<NPCPlacementEntry> placements = new List<NPCPlacementEntry>();

        [System.Serializable]
        public class NPCPlacementEntry
        {
            public string npcId;
            public string npcDisplayName;
            public Vector3 position;
            public Vector3 rotation;
        }

        void Awake()
        {
            if (npcPrefab == null)
            {
                npcPrefab = CreateDefaultNPCPrefab();
            }

            PlaceAllNPCs();
        }

        void PlaceAllNPCs()
        {
            if (npcParent == null)
            {
                var parentObj = GameObject.Find("NPCs");
                if (parentObj != null) npcParent = parentObj.transform;
                else
                {
                    npcParent = new GameObject("NPCs").transform;
                }
            }

            foreach (var entry in placements)
            {
                PlaceNPC(entry);
            }
        }

        void PlaceNPC(NPCPlacementEntry entry)
        {
            GameObject npc = Instantiate(npcPrefab, entry.position, Quaternion.Euler(entry.rotation), npcParent);
            npc.name = $"NPC_{entry.npcId}";

            var controller = npc.GetComponent<NPCController>();
            if (controller != null)
            {
                controller.Data = DialogueLoader.Instance?.GetDialogueData(entry.npcId);
                if (controller.Data == null)
                {
                    Debug.LogWarning($"[NPCPlacement] No dialogue data found for {entry.npcId}");
                }
            }
        }

        /// <summary>
        /// Creates a default NPC prefab with all required components.
        /// </summary>
        GameObject CreateDefaultNPCPrefab()
        {
            GameObject prefab = new GameObject("NPC_Dialogue");

            // Visual representation (capsule)
            var capsule = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            capsule.name = "Model";
            capsule.transform.SetParent(prefab.transform);
            capsule.transform.localPosition = new Vector3(0, 1, 0);
            // Remove the collider from the capsule (we use a separate trigger collider)
            DestroyImmediate(capsule.GetComponent<Collider>());

            // Name label (world-space text)
            var labelObj = new GameObject("NameLabel");
            labelObj.transform.SetParent(prefab.transform);
            labelObj.transform.localPosition = new Vector3(0, 2.2f, 0);
            var tmp = labelObj.AddComponent<TMPro.TextMeshPro>();
            tmp.alignment = TMPro.TextAlignmentOptions.Center;
            tmp.fontSize = 2;
            tmp.color = Color.white;
            labelObj.AddComponent<TMPro.TMPro_UGUI>(); // Ensure TMP works

            // NPC Controller
            var npcController = prefab.AddComponent<NPCController>();
            npcController.interactionRadius = 3f;

            // Animator (for idle animation)
            prefab.AddComponent<Animator>();

            // SphereCollider for proximity trigger
            var col = prefab.AddComponent<SphereCollider>();
            col.isTrigger = true;
            col.radius = 3f;

            return prefab;
        }
    }
}
