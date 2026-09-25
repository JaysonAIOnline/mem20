using UnityEngine;
using UnityEngine.UI;
using TMPro;

namespace UnreliableProphecy
{
    /// <summary>
    /// Proximity prompt UI — shows "Press E to talk to [NPC]" when near an NPC.
    /// World-space overlay that follows the NPC.
    /// </summary>
    public class ProximityPromptUI : MonoBehaviour
    {
        [Header("UI References")]
        public Canvas canvas;
        public TextMeshProUGUI promptText;
        public RectTransform promptPanel;

        [Header("Settings")]
        public Vector3 worldOffset = new Vector3(0, 2.2f, 0);
        public float smoothSpeed = 8f;

        private Camera mainCamera;
        private NPCController trackedNPC;
        private bool isVisible = false;

        void Awake()
        {
            mainCamera = Camera.main;
            if (canvas == null)
                canvas = GetComponent<Canvas>();
            if (promptText == null)
                promptText = GetComponentInChildren<TextMeshProUGUI>();

            // Start hidden
            if (promptPanel != null)
                promptPanel.gameObject.SetActive(false);
        }

        void Update()
        {
            if (trackedNPC != null && isVisible)
            {
                // Follow the NPC in world space
                Vector3 worldPos = trackedNPC.GetInteractionPosition() + worldOffset;
                Vector3 screenPos = mainCamera.WorldToScreenPoint(worldPos);

                if (screenPos.z > 0)
                {
                    promptPanel.position = Vector3.Lerp(promptPanel.position, screenPos, Time.deltaTime * smoothSpeed);
                    promptPanel.gameObject.SetActive(true);
                }
                else
                {
                    promptPanel.gameObject.SetActive(false);
                }
            }
            else
            {
                if (promptPanel != null)
                    promptPanel.gameObject.SetActive(false);
            }
        }

        /// <summary>
        /// Show the prompt for a specific NPC.
        /// </summary>
        public void ShowPrompt(NPCController npc)
        {
            trackedNPC = npc;
            isVisible = true;
            if (promptText != null && npc.Data != null)
                promptText.text = $"Press E to talk to {npc.Data.npcDisplayName}";
        }

        /// <summary>
        /// Hide the prompt.
        /// </summary>
        public void HidePrompt()
        {
            isVisible = false;
            trackedNPC = null;
            if (promptPanel != null)
                promptPanel.gameObject.SetActive(false);
        }
    }
}
