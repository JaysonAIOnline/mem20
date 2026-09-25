using UnityEngine;
using UnityEngine.UI;
using TMPro;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Maintains a running history log of all dialogue exchanged with NPCs.
    /// Scrollable panel that appears during conversation showing previous lines.
    /// Each entry: NPC name + line text, or "You: [player response]".
    /// Styled to match the parchment aesthetic.
    /// </summary>
    public class DialogueHistoryUI : MonoBehaviour
    {
        [Header("UI References")]
        public GameObject historyPanel;
        public Transform historyContent;
        public ScrollRect scrollRect;
        public GameObject historyEntryPrefab;

        [Header("Styling")]
        public Color npcLineColor = new Color(0.95f, 0.95f, 0.9f);
        public Color playerLineColor = new Color(0.7f, 0.85f, 1.0f);
        public Color systemLineColor = new Color(0.6f, 0.6f, 0.6f);
        public int maxEntries = 50;

        [Header("Animation")]
        public float fadeInDuration = 0.2f;
        public float fadeOutDuration = 0.15f;

        // State
        private List<GameObject> entries = new List<GameObject>();
        private CanvasGroup canvasGroup;
        private bool isVisible = false;

        void Awake()
        {
            canvasGroup = GetComponent<CanvasGroup>();
            if (canvasGroup == null)
                canvasGroup = gameObject.AddComponent<CanvasGroup>();
            canvasGroup.alpha = 0f;
            canvasGroup.interactable = false;
            canvasGroup.blocksRaycasts = false;
        }

        /// <summary>
        /// Adds a line to the history log and scrolls to bottom.
        /// </summary>
        public void AddLine(string speaker, string text, bool isPlayer = false)
        {
            if (historyEntryPrefab == null || historyContent == null) return;

            // Remove oldest entries if we've hit the cap
            while (entries.Count >= maxEntries)
            {
                Destroy(entries[0]);
                entries.RemoveAt(0);
            }

            // Create entry
            var entry = Instantiate(historyEntryPrefab, historyContent);
            var tmp = entry.GetComponentInChildren<TextMeshProUGUI>();
            if (tmp != null)
            {
                tmp.text = $"<b>{speaker}:</b> {text}";
                tmp.color = isPlayer ? playerLineColor : npcLineColor;
            }
            entries.Add(entry);

            // Scroll to bottom on next frame (after layout rebuild)
            StartCoroutine(ScrollToBottom());
        }

        /// <summary>
        /// Adds a system message (e.g., "Conversation ended").
        /// </summary>
        public void AddSystemMessage(string text)
        {
            if (historyEntryPrefab == null || historyContent == null) return;

            var entry = Instantiate(historyEntryPrefab, historyContent);
            var tmp = entry.GetComponentInChildren<TextMeshProUGUI>();
            if (tmp != null)
            {
                tmp.text = $"<i>{text}</i>";
                tmp.color = systemLineColor;
            }
            entries.Add(entry);
            StartCoroutine(ScrollToBottom());
        }

        /// <summary>
        /// Clears all history entries.
        /// </summary>
        public void Clear()
        {
            foreach (var entry in entries)
            {
                if (entry != null) Destroy(entry);
            }
            entries.Clear();
        }

        /// <summary>
        /// Shows the history panel with fade.
        /// </summary>
        public void Show()
        {
            if (isVisible) return;
            gameObject.SetActive(true);
            StopAllCoroutines();
            StartCoroutine(FadeCanvas(1f, fadeInDuration));
            isVisible = true;
        }

        /// <summary>
        /// Hides the history panel with fade.
        /// </summary>
        public void Hide()
        {
            if (!isVisible) return;
            StopAllCoroutines();
            StartCoroutine(FadeOut());
            isVisible = false;
        }

        /// <summary>
        /// Toggles visibility.
        /// </summary>
        public void Toggle()
        {
            if (isVisible) Hide();
            else Show();
        }

        public bool IsVisible => isVisible;

        private System.Collections.IEnumerator FadeCanvas(float targetAlpha, float duration)
        {
            float startAlpha = canvasGroup.alpha;
            float elapsed = 0f;

            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                canvasGroup.alpha = Mathf.Lerp(startAlpha, targetAlpha, elapsed / duration);
                yield return null;
            }

            canvasGroup.alpha = targetAlpha;
            canvasGroup.interactable = targetAlpha > 0.5f;
            canvasGroup.blocksRaycasts = targetAlpha > 0.5f;
        }

        private System.Collections.IEnumerator FadeOut()
        {
            yield return StartCoroutine(FadeCanvas(0f, fadeOutDuration));
            gameObject.SetActive(false);
        }

        private System.Collections.IEnumerator ScrollToBottom()
        {
            yield return null;
            if (scrollRect != null)
            {
                scrollRect.verticalNormalizedPosition = 0f;
            }
        }
    }
}