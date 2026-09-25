using UnityEngine;
using UnityEngine.UI;
using TMPro;

namespace UnreliableProphecy
{
    /// <summary>
    /// UI controller for the character loading panel.
    /// Allows the player to enter a model ID, load a custom GLB character,
    /// see loading progress, and handle errors.
    /// </summary>
    public class CharacterLoadingUI : MonoBehaviour
    {
        [Header("UI References")]
        public TMP_InputField modelIdInput;
        public Button loadButton;
        public Button clearButton;
        public Slider progressSlider;
        public TextMeshProUGUI statusText;
        public TextMeshProUGUI errorText;
        public GameObject loadingPanel;
        public GameObject errorPanel;

        [Header("Settings")]
        [SerializeField] private string loadPrompt = "Enter Model ID and press Load";

        void Start()
        {
            // Subscribe to CharacterLoadingManager events
            var manager = CharacterLoadingManager.Instance;
            if (manager != null)
            {
                manager.OnLoadingStarted += OnLoadingStarted;
                manager.OnCharacterLoaded += OnCharacterLoaded;
                manager.OnLoadingFailed += OnLoadingFailed;
                manager.OnLoadingProgress += OnLoadingProgress;
            }

            // Set up button listeners
            if (loadButton != null)
                loadButton.onClick.AddListener(OnLoadClicked);
            if (clearButton != null)
                clearButton.onClick.AddListener(OnClearClicked);

            // Initialize UI state
            ResetUI();
        }

        void OnDestroy()
        {
            var manager = CharacterLoadingManager.Instance;
            if (manager != null)
            {
                manager.OnLoadingStarted -= OnLoadingStarted;
                manager.OnCharacterLoaded -= OnCharacterLoaded;
                manager.OnLoadingFailed -= OnLoadingFailed;
                manager.OnLoadingProgress -= OnLoadingProgress;
            }
        }

        void ResetUI()
        {
            if (progressSlider != null)
                progressSlider.value = 0f;
            if (statusText != null)
                statusText.text = loadPrompt;
            if (errorText != null)
                errorText.text = "";
            if (errorPanel != null)
                errorPanel.SetActive(false);
            if (loadingPanel != null)
                loadingPanel.SetActive(true);
            if (loadButton != null)
                loadButton.interactable = true;
        }

        void OnLoadClicked()
        {
            if (modelIdInput == null || string.IsNullOrWhiteSpace(modelIdInput.text))
            {
                ShowError("Please enter a model ID.");
                return;
            }

            string modelId = modelIdInput.text.Trim();
            var manager = CharacterLoadingManager.Instance;
            if (manager != null)
            {
                manager.LoadCharacter(modelId);
            }
            else
            {
                ShowError("CharacterLoadingManager not found in scene.");
            }
        }

        void OnClearClicked()
        {
            var manager = CharacterLoadingManager.Instance;
            if (manager != null)
            {
                manager.ClearCharacter();
            }
            ResetUI();
        }

        // ── Event handlers ───────────────────────────────────────────

        void OnLoadingStarted(string modelId)
        {
            if (loadButton != null)
                loadButton.interactable = false;
            if (statusText != null)
                statusText.text = $"Loading {modelId}...";
            if (errorPanel != null)
                errorPanel.SetActive(false);
            if (progressSlider != null)
                progressSlider.value = 0f;
        }

        void OnCharacterLoaded(string modelId, GameObject character)
        {
            if (loadButton != null)
                loadButton.interactable = true;
            if (statusText != null)
                statusText.text = $"Loaded: {modelId}";
            if (progressSlider != null)
                progressSlider.value = 1f;
        }

        void OnLoadingFailed(string error)
        {
            if (loadButton != null)
                loadButton.interactable = true;
            if (statusText != null)
                statusText.text = "Load failed.";
            if (progressSlider != null)
                progressSlider.value = 0f;
            ShowError(error);
        }

        void OnLoadingProgress(float progress)
        {
            if (progressSlider != null)
                progressSlider.value = progress;
        }

        void ShowError(string message)
        {
            if (errorText != null)
                errorText.text = message;
            if (errorPanel != null)
                errorPanel.SetActive(true);
        }
    }
}
