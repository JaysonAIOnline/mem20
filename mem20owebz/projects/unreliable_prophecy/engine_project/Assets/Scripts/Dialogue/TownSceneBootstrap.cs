using UnityEngine;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Places NPCs in the town scene at logical positions based on their roles.
    /// Called at scene start. Reads dialogue data from Resources/Dialogue/.
    /// </summary>
    public class TownSceneBootstrap : MonoBehaviour
    {
        [Header("Prefab")]
        public GameObject npcPrefab;

        [Header("Scene References")]
        public Transform npcParent;

        /// <summary>
        /// NPC placement data — maps NPC ID to a world position and rotation.
        /// Positions are based on the world layout document.
        /// </summary>
        [System.Serializable]
        public class NPCEntry
        {
            public string npcId;
            public Vector3 position;
            public Vector3 rotation = Vector3.zero;
        }

        public List<NPCEntry> npcPlacements = new List<NPCEntry>
        {
            // Quietvale NPCs — placed at logical positions from world layout
            new NPCEntry { npcId = "mira_shopkeeper", position = new Vector3(10, 0, -5) },    // Near Ink & Parchment Cart / shop area
            new NPCEntry { npcId = "aldric_guard", position = new Vector3(0, 0, 105) },        // Village Exit Gate
            new NPCEntry { npcId = "bertram_farmer", position = new Vector3(-50, 0, -30) },    // Reflection Pond (farm area)
            new NPCEntry { npcId = "pip_gossip", position = new Vector3(-15, 0, 10) },         // Near Filing Cabinet (tavern area)
            new NPCEntry { npcId = "lyra_questgiver", position = new Vector3(25, 0, 35) },     // Wizard's Corner (Guild)
            new NPCEntry { npcId = "sister_wren", position = new Vector3(-30, 0, -30) },       // Player House area (healer)
            new NPCEntry { npcId = "kael_blacksmith", position = new Vector3(15, 0, 15) },     // Central square area (forge)
            new NPCEntry { npcId = "dolly_innkeeper", position = new Vector3(-20, 0, -30) },   // Player House (inn)
            new NPCEntry { npcId = "aldous_priest", position = new Vector3(-5, 0, 15) },       // Form Station area (temple)
            new NPCEntry { npcId = "jasper_bard", position = new Vector3(-10, 0, 5) },         // Village Square (performer)
        };

        void Awake()
        {
            // Ensure DialogueLoader exists
            if (DialogueLoader.Instance == null)
            {
                var loaderObj = new GameObject("DialogueLoader");
                loaderObj.AddComponent<DialogueLoader>();
            }

            // Ensure DialogueManager exists
            if (DialogueManager.Instance == null)
            {
                var dmObj = new GameObject("DialogueManager");
                dmObj.AddComponent<DialogueManager>();
            }

            // Find or create NPC parent
            if (npcParent == null)
            {
                var npcParentObj = GameObject.Find("NPCs");
                if (npcParentObj == null)
                {
                    npcParentObj = new GameObject("NPCs");
                }
                npcParent = npcParentObj.transform;
            }

            // Place all NPCs
            PlaceAllNPCs();

            // Setup UI
            SetupDialogueUI();
        }

        void PlaceAllNPCs()
        {
            if (npcPrefab == null)
            {
                // Try to load from Resources or create default
                npcPrefab = Resources.Load<GameObject>("Prefabs/NPC_Dialogue");
                if (npcPrefab == null)
                {
                    npcPrefab = CreateDefaultNPCPrefab();
                }
            }

            foreach (var entry in npcPlacements)
            {
                PlaceNPC(entry);
            }
        }

        void PlaceNPC(NPCEntry entry)
        {
            Vector3 pos = entry.position;
            Quaternion rot = Quaternion.Euler(entry.rotation);

            GameObject npc = Instantiate(npcPrefab, pos, rot, npcParent);
            npc.name = $"NPC_{entry.npcId}";

            // Assign dialogue data
            var controller = npc.GetComponent<NPCController>();
            if (controller != null)
            {
                var data = DialogueLoader.Instance?.GetDialogueData(entry.npcId);
                if (data != null)
                {
                    controller.Data = data;

                    // Set the name label
                    var label = npc.GetComponentInChildren<TMPro.TextMeshPro>();
                    if (label != null)
                    {
                        label.text = data.npcDisplayName;
                    }
                }
                else
                {
                    Debug.LogWarning($"[TownSceneBootstrap] No dialogue data for {entry.npcId}");
                }
            }
        }

        void SetupDialogueUI()
        {
            // Check if UI canvas already exists
            var existingCanvas = GameObject.Find("DialogueUICanvas");
            if (existingCanvas != null) return;

            // Create canvas
            var canvasObj = new GameObject("DialogueUICanvas");
            var canvas = canvasObj.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 100;
            canvasObj.AddComponent<UnityEngine.UI.CanvasScaler>();
            canvasObj.AddComponent<UnityEngine.UI.GraphicRaycaster>();

            // CanvasGroup for fade
            canvasObj.AddComponent<UnityEngine.UI.CanvasGroup>();

            // Create dialogue UI component
            var dialogueUI = canvasObj.AddComponent<DialogueUI>();

            // Create background panel
            var bgObj = new GameObject("Background");
            bgObj.transform.SetParent(canvasObj.transform, false);
            var bgImage = bgObj.AddComponent<UnityEngine.UI.Image>();
            bgImage.color = new Color(0.1f, 0.1f, 0.15f, 0.85f);
            var bgRect = bgObj.GetComponent<UnityEngine.RectTransform>();
            bgRect.anchorMin = new Vector2(0, 0);
            bgRect.anchorMax = new Vector2(1, 0.3f);
            bgRect.pivot = new Vector2(0.5f, 0);
            bgRect.offsetMin = Vector2.zero;
            bgRect.offsetMax = Vector2.zero;

            // Create speaker name text
            var speakerObj = new GameObject("SpeakerName");
            speakerObj.transform.SetParent(canvasObj.transform, false);
            var speakerText = speakerObj.AddComponent<TMPro.TextMeshProUGUI>();
            speakerText.fontSize = 24;
            speakerText.fontStyle = TMPro.FontStyles.Bold;
            speakerText.color = new Color(1f, 0.85f, 0.6f);
            speakerText.alignment = TMPro.TextAlignmentOptions.Center;
            var speakerRect = speakerObj.GetComponent<UnityEngine.RectTransform>();
            speakerRect.anchorMin = new Vector2(0, 0.5f);
            speakerRect.anchorMax = new Vector2(1, 1);
            speakerRect.pivot = new Vector2(0.5f, 0.5f);
            speakerRect.offsetMin = Vector2.zero;
            speakerRect.offsetMax = Vector2.zero;

            // Create dialogue text
            var dialogueObj = new GameObject("DialogueText");
            dialogueObj.transform.SetParent(canvasObj.transform, false);
            var dialogueText = dialogueObj.AddComponent<TMPro.TextMeshProUGUI>();
            dialogueText.fontSize = 18;
            dialogueText.color = Color.white;
            dialogueText.alignment = TMPro.TextAlignmentOptions.TopLeft;
            dialogueText.wordWrapping = true;
            var dialogueRect = dialogueObj.GetComponent<UnityEngine.RectTransform>();
            dialogueRect.anchorMin = new Vector2(0.05f, 0.15f);
            dialogueRect.anchorMax = new Vector2(0.95f, 0.45f);
            dialogueRect.pivot = new Vector2(0.5f, 0.5f);
            dialogueRect.offsetMin = Vector2.zero;
            dialogueRect.offsetMax = Vector2.zero;

            // Create advance prompt text
            var promptObj = new GameObject("AdvancePrompt");
            promptObj.transform.SetParent(canvasObj.transform, false);
            var promptText = promptObj.AddComponent<TMPro.TextMeshProUGUI>();
            promptText.fontSize = 14;
            promptText.fontStyle = TMPro.FontStyles.Italic;
            promptText.color = new Color(0.7f, 0.7f, 0.7f);
            promptText.alignment = TMPro.TextAlignmentOptions.Center;
            var promptRect = promptObj.GetComponent<UnityEngine.RectTransform>();
            promptRect.anchorMin = new Vector2(0, 0);
            promptRect.anchorMax = new Vector2(1, 0.12f);
            promptRect.pivot = new Vector2(0.5f, 0.5f);
            promptRect.offsetMin = Vector2.zero;
            promptRect.offsetMax = Vector2.zero;

            // Create response container
            var responseObj = new GameObject("ResponseContainer");
            responseObj.transform.SetParent(canvasObj.transform, false);
            responseObj.AddComponent<UnityEngine.UI.VerticalLayoutGroup>();
            var responseRect = responseObj.GetComponent<UnityEngine.RectTransform>();
            responseRect.anchorMin = new Vector2(0.05f, 0.05f);
            responseRect.anchorMax = new Vector2(0.95f, 0.25f);
            responseRect.pivot = new Vector2(0.5f, 0.5f);
            responseRect.offsetMin = Vector2.zero;
            responseRect.offsetMax = Vector2.zero;

            // Wire up references
            dialogueUI.npcNameText = speakerText;
            dialogueUI.dialogueText = dialogueText;
            dialogueUI.advancePromptText = promptText;
            dialogueUI.responseContainer = responseObj.transform;

            // Link to DialogueManager
            if (DialogueManager.Instance != null)
            {
                DialogueManager.Instance.dialogueUI = dialogueUI;
            }

            // Start hidden
            var canvasGroup = canvasObj.GetComponent<UnityEngine.UI.CanvasGroup>();
            if (canvasGroup != null)
            {
                canvasGroup.alpha = 0f;
                canvasGroup.interactable = false;
                canvasGroup.blocksRaycasts = false;
            }

            // === Create Dialogue History Panel ===
            SetupHistoryPanel(canvasObj);

            // === Create Proximity Prompt UI ===
            SetupProximityPromptUI();

            // === Create Dialogue Audio ===
            SetupDialogueAudio();
        }

        /// <summary>
        /// Creates a scrollable history panel that appears during dialogue.
        /// </summary>
        void SetupHistoryPanel(GameObject canvasObj)
        {
            // History panel (right side of screen)
            var historyObj = new GameObject("DialogueHistory");
            historyObj.transform.SetParent(canvasObj.transform, false);
            var historyImage = historyObj.AddComponent<UnityEngine.UI.Image>();
            historyImage.color = new Color(0.08f, 0.08f, 0.12f, 0.9f);
            var historyRect = historyObj.GetComponent<UnityEngine.RectTransform>();
            historyRect.anchorMin = new Vector2(0.7f, 0.35f);
            historyRect.anchorMax = new Vector2(0.98f, 0.95f);
            historyRect.pivot = new Vector2(0.5f, 0.5f);
            historyRect.offsetMin = Vector2.zero;
            historyRect.offsetMax = Vector2.zero;

            // Add ScrollRect
            var scrollRect = historyObj.AddComponent<UnityEngine.UI.ScrollRect>();

            // Viewport
            var viewportObj = new GameObject("Viewport");
            viewportObj.transform.SetParent(historyObj.transform, false);
            var viewportImage = viewportObj.AddComponent<UnityEngine.UI.Image>();
            viewportImage.color = new Color(0.05f, 0.05f, 0.08f, 0.5f);
            var viewportRect = viewportObj.GetComponent<UnityEngine.RectTransform>();
            viewportRect.anchorMin = Vector2.zero;
            viewportRect.anchorMax = Vector2.one;
            viewportRect.offsetMin = Vector2.zero;
            viewportRect.offsetMax = Vector2.zero;
            var viewportMask = viewportObj.AddComponent<UnityEngine.UI.Mask>();

            // Content
            var contentObj = new GameObject("Content");
            contentObj.transform.SetParent(viewportObj.transform, false);
            var contentRect = contentObj.GetComponent<UnityEngine.RectTransform>();
            contentRect.anchorMin = new Vector2(0, 1);
            contentRect.anchorMax = Vector2.one;
            contentRect.pivot = new Vector2(0.5f, 1f);
            contentRect.offsetMin = new Vector2(5, 0);
            contentRect.offsetMax = new Vector2(-5, 0);
            var contentLayout = contentObj.AddComponent<UnityEngine.UI.VerticalLayoutGroup>();
            contentLayout.childControlHeight = false;
            contentLayout.childForceExpandHeight = false;
            contentLayout.spacing = 4f;
            contentLayout.padding = new RectOffset(5, 5, 5, 5);
            contentObj.AddComponent<UnityEngine.UI.ContentSizeFitter>().verticalFit = UnityEngine.UI.ContentSizeFitter.FitMode.PreferredSize;

            // Wire up scroll rect
            scrollRect.content = contentRect;
            scrollRect.viewport = viewportRect;
            scrollRect.vertical = true;
            scrollRect.horizontal = false;
            scrollRect.movementType = UnityEngine.UI.ScrollRect.MovementType.Clamped;
            scrollRect.scrollSensitivity = 10f;

            // Add DialogueHistoryUI component
            var historyUI = historyObj.AddComponent<DialogueHistoryUI>();
            historyUI.historyContent = contentObj.transform;
            historyUI.scrollRect = scrollRect;

            // Start hidden
            historyObj.SetActive(false);
        }

        /// <summary>
        /// Creates a world-space proximity prompt canvas.
        /// </summary>
        void SetupProximityPromptUI()
        {
            var promptCanvasObj = new GameObject("ProximityPromptCanvas");
            var promptCanvas = promptCanvasObj.AddComponent<Canvas>();
            promptCanvas.renderMode = RenderMode.ScreenSpaceOverlay;
            promptCanvas.sortingOrder = 50;
            promptCanvasObj.AddComponent<UnityEngine.UI.CanvasScaler>();
            promptCanvasObj.AddComponent<UnityEngine.UI.GraphicRaycaster>();

            // Prompt panel
            var promptPanelObj = new GameObject("PromptPanel");
            promptPanelObj.transform.SetParent(promptCanvasObj.transform, false);
            var promptImage = promptPanelObj.AddComponent<UnityEngine.UI.Image>();
            promptImage.color = new Color(0.1f, 0.1f, 0.15f, 0.8f);
            var promptRect = promptPanelObj.GetComponent<UnityEngine.RectTransform>();
            promptRect.anchorMin = new Vector2(0.5f, 0.3f);
            promptRect.anchorMax = new Vector2(0.5f, 0.3f);
            promptRect.pivot = new Vector2(0.5f, 0.5f);
            promptRect.sizeDelta = new Vector2(200, 30);

            // Prompt text
            var promptTextObj = new GameObject("PromptText");
            promptTextObj.transform.SetParent(promptPanelObj.transform, false);
            var promptText = promptTextObj.AddComponent<TMPro.TextMeshProUGUI>();
            promptText.fontSize = 14;
            promptText.color = Color.white;
            promptText.alignment = TMPro.TextAlignmentOptions.Center;
            var promptTextRect = promptTextObj.GetComponent<UnityEngine.RectTransform>();
            promptTextRect.anchorMin = Vector2.zero;
            promptTextRect.anchorMax = Vector2.one;
            promptTextRect.offsetMin = Vector2.zero;
            promptTextRect.offsetMax = Vector2.zero;

            // Add ProximityPromptUI component
            var proximityUI = promptCanvasObj.AddComponent<ProximityPromptUI>();
            proximityUI.canvas = promptCanvas;
            proximityUI.promptText = promptText;
            proximityUI.promptPanel = promptRect;

            // Start hidden
            promptPanelObj.SetActive(false);
        }

        /// <summary>
        /// Creates the dialogue audio manager.
        /// </summary>
        void SetupDialogueAudio()
        {
            var audioObj = new GameObject("DialogueAudio");
            audioObj.AddComponent<DialogueAudio>();
        }

        /// <summary>
        /// Creates a default NPC prefab at runtime if no prefab is assigned.
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
