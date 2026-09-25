using UnityEngine;
using UnityEngine.UI;
using TMPro;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// UI component for displaying dynamic dialogue.
    /// Shows NPC name, dialogue text, player response options, and interaction prompts.
    /// Parchment-styled to match the game's aesthetic.
    /// </summary>
    [RequireComponent(typeof(CanvasGroup))]
    public class DialogueUI : MonoBehaviour
    {
        [Header("Dialogue Display")]
        public TextMeshProUGUI npcNameText;
        public TextMeshProUGUI dialogueText;
        public TextMeshProUGUI advancePromptText;
        public Image portraitImage;

        [Header("Response Options")]
        public Transform responseContainer;
        public GameObject responseButtonPrefab;
        public int maxResponseOptions = 3;

        [Header("Interaction Prompt")]
        public GameObject interactionPrompt;
        public TextMeshProUGUI interactionPromptText;

        [Header("Animation")]
        public float fadeInDuration = 0.3f;
        public float fadeOutDuration = 0.2f;
        public float typewriterSpeed = 0.05f;

        [Header("Styling")]
        public Color npcNameColor = new Color(0.9f, 0.85f, 0.7f);
        public Color dialogueColor = new Color(0.95f, 0.95f, 0.9f);
        public Sprite parchmentBackground;

        // State
        private CanvasGroup canvasGroup;
        private List<GameObject> responseButtons = new List<GameObject>();
        private bool isVisible = false;
        private Coroutine typewriterCoroutine;
        private string pendingFullText = "";
        private bool typewriterSkipped = false;

        void Awake()
        {
            canvasGroup = GetComponent<CanvasGroup>();
            canvasGroup.alpha = 0f;
            canvasGroup.interactable = false;
            canvasGroup.blocksRaycasts = false;

            if (interactionPrompt != null)
                interactionPrompt.SetActive(false);
        }

        /// <summary>
        /// Shows the dialogue UI with the given NPC name.
        /// </summary>
        public void Show(string npcName)
        {
            if (npcNameText != null)
            {
                npcNameText.text = npcName;
                npcNameText.color = npcNameColor;
            }

            gameObject.SetActive(true);
            StopAllCoroutines();
            StartCoroutine(FadeCanvas(1f, fadeInDuration));
            isVisible = true;
        }

        /// <summary>
        /// Sets the dialogue text with optional typewriter effect.
        /// Pressing E during typewriter skips to end.
        /// </summary>
        public void SetDialogueText(string text, bool useTypewriter = true)
        {
            if (typewriterCoroutine != null)
                StopCoroutine(typewriterCoroutine);

            pendingFullText = text;
            typewriterSkipped = false;

            if (useTypewriter)
                typewriterCoroutine = StartCoroutine(TypewriterEffect(text));
            else
                dialogueText.text = text;
        }

        /// <summary>
        /// Skips the current typewriter effect to display full text immediately.
        /// </summary>
        public void SkipTypewriter()
        {
            if (typewriterCoroutine != null)
            {
                StopCoroutine(typewriterCoroutine);
                typewriterCoroutine = null;
                typewriterSkipped = true;
                if (!string.IsNullOrEmpty(pendingFullText))
                {
                    dialogueText.text = pendingFullText;
                }
            }
        }

        /// <summary>
        /// Sets the advance prompt text (e.g., "Press E to continue...").
        /// </summary>
        public void SetAdvancePrompt(string prompt)
        {
            if (advancePromptText != null)
                advancePromptText.text = prompt;
        }

        /// <summary>
        /// Shows player response options.
        /// </summary>
        public void ShowResponses(List<string> responses, System.Action<int> onSelected)
        {
            ClearResponses();

            for (int i = 0; i < Mathf.Min(responses.Count, maxResponseOptions); i++)
            {
                var btn = Instantiate(responseButtonPrefab, responseContainer);
                var tmp = btn.GetComponentInChildren<TextMeshProUGUI>();
                if (tmp != null)
                    tmp.text = responses[i];

                int index = i; // capture for closure
                var button = btn.GetComponent<Button>();
                if (button != null)
                    button.onClick.AddListener(() => {
                        onSelected?.Invoke(index);
                        ClearResponses();
                    });

                responseButtons.Add(btn);
            }
        }

        /// <summary>
        /// Clears all response buttons.
        /// </summary>
        public void ClearResponses()
        {
            foreach (var btn in responseButtons)
            {
                if (btn != null)
                    Destroy(btn);
            }
            responseButtons.Clear();
        }

        /// <summary>
        /// Hides the dialogue UI.
        /// </summary>
        public void Hide()
        {
            StopAllCoroutines();
            StartCoroutine(FadeOut());
        }

        /// <summary>
        /// Shows the interaction prompt (e.g., "Press E to talk to [NPC]").
        /// </summary>
        public void ShowInteractionPrompt(string npcName)
        {
            if (interactionPrompt != null)
            {
                interactionPrompt.SetActive(true);
                if (interactionPromptText != null)
                    interactionPromptText.text = $"Press E to talk to {npcName}";
            }
        }

        /// <summary>
        /// Hides the interaction prompt.
        /// </summary>
        public void HideInteractionPrompt()
        {
            if (interactionPrompt != null)
                interactionPrompt.SetActive(false);
        }

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
            isVisible = false;
        }

        private System.Collections.IEnumerator TypewriterEffect(string text)
        {
            dialogueText.text = "";
            int charIndex = 0;

            while (charIndex < text.Length)
            {
                // Check for skip input
                if (Input.GetKeyDown(KeyCode.E) || Input.GetKeyDown(KeyCode.Space) || Input.GetMouseButtonDown(0))
                {
                    dialogueText.text = text;
                    typewriterSkipped = true;
                    yield break;
                }

                dialogueText.text += text[charIndex];
                charIndex++;

                // Play typewriter click audio
                var audio = DialogueAudio.Instance;
                if (audio != null) audio.PlayTypewriterClick();

                yield return new WaitForSeconds(typewriterSpeed);
            }

            typewriterCoroutine = null;
        }

        public bool IsVisible => isVisible;
        public bool IsTypewriterActive => typewriterCoroutine != null;
    }
}