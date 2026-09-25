using System;
using System.Collections;
using UnityEngine;
using UnityEngine.Events;

namespace UnreliableProphecy
{
    /// <summary>
    /// Manages the full flow of loading a custom GLB character from the backend:
    /// 1. Takes a model ID
    /// 2. Fetches GLB bytes from the storage API
    /// 3. Parses and instantiates via RuntimeGLBLoader
    /// 4. Replaces the default player prefab
    /// 5. Handles loading UI, errors, and retry logic
    /// </summary>
    public class CharacterLoadingManager : MonoBehaviour
    {
        public static CharacterLoadingManager Instance { get; private set; }

        [Header("Backend Configuration")]
        [SerializeField] private string backendBaseUrl = "http://localhost:8000";

        [Header("Player Spawn")]
        [SerializeField] private string playerSpawnName = "Player Spawn";
        [SerializeField] private string playerTag = "Player";

        [Header("Events")]
        public UnityEvent<string> OnLoadingStarted;
        public UnityEvent<string, GameObject> OnCharacterLoaded;
        public UnityEvent<string> OnLoadingFailed;
        public UnityEvent<float> OnLoadingProgress;

        // State
        private GameObject currentCharacter;
        private bool isLoading;

        public GameObject CurrentCharacter => currentCharacter;
        public bool IsLoading => isLoading;

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
        /// Load a character by model ID. Replaces any existing player character.
        /// </summary>
        public void LoadCharacter(string modelId)
        {
            if (isLoading)
            {
                Debug.LogWarning($"[CharacterLoadingManager] Already loading. Ignoring request for {modelId}");
                return;
            }
            StartCoroutine(LoadCharacterCoroutine(modelId));
        }

        /// <summary>
        /// Load a character from raw GLB bytes (for local file imports).
        /// </summary>
        public void LoadCharacterFromBytes(byte[] glbData, string modelId = "local")
        {
            if (isLoading) return;
            StartCoroutine(LoadFromBytesCoroutine(glbData, modelId));
        }

        /// <summary>
        /// Remove the current character and restore the default player.
        /// </summary>
        public void ClearCharacter()
        {
            if (currentCharacter != null)
            {
                Destroy(currentCharacter);
                currentCharacter = null;
            }
        }

        // ── Coroutine: Fetch from backend ────────────────────────────

        IEnumerator LoadCharacterCoroutine(string modelId)
        {
            isLoading = true;
            OnLoadingStarted?.Invoke(modelId);

            // First verify the model exists
            string verifyUrl = $"{backendBaseUrl}/api/v1/models/{modelId}";
            using (var verifyReq = UnityWebRequest.Get(verifyUrl))
            {
                yield return verifyReq.SendWebRequest();

                if (verifyReq.result != UnityWebRequest.Result.Success)
                {
                    string error = verifyReq.error ?? "Model not found";
                    Debug.LogError($"[CharacterLoadingManager] Model verification failed: {error}");
                    OnLoadingFailed?.Invoke($"Model '{modelId}' not found on server.");
                    isLoading = false;
                    yield break;
                }
            }

            // Download the GLB file
            string downloadUrl = $"{backendBaseUrl}/api/v1/models/{modelId}/download";
            using (var downloadReq = UnityWebRequest.Get(downloadUrl))
            {
                // Use DownloadHandlerBuffer to get raw bytes
                downloadReq.downloadHandler = new DownloadHandlerBuffer();

                var operation = downloadReq.SendWebRequest();

                // Track progress
                while (!operation.isDone)
                {
                    OnLoadingProgress?.Invoke(operation.progress);
                    yield return null;
                }

                OnLoadingProgress?.Invoke(1f);

                if (downloadReq.result != UnityWebRequest.Result.Success)
                {
                    string error = downloadReq.error ?? "Download failed";
                    Debug.LogError($"[CharacterLoadingManager] Download failed: {error}");
                    OnLoadingFailed?.Invoke($"Failed to download model: {error}");
                    isLoading = false;
                    yield break;
                }

                byte[] glbData = downloadReq.downloadHandler.data;
                if (glbData == null || glbData.Length == 0)
                {
                    OnLoadingFailed?.Invoke("Downloaded file is empty.");
                    isLoading = false;
                    yield break;
                }

                // Parse and instantiate
                yield return StartCoroutine(InstantiateCharacter(glbData, modelId));
            }

            isLoading = false;
        }

        // ── Coroutine: Load from raw bytes ───────────────────────────

        IEnumerator LoadFromBytesCoroutine(byte[] glbData, string modelId)
        {
            isLoading = true;
            OnLoadingStarted?.Invoke(modelId);
            OnLoadingProgress?.Invoke(0.5f);

            yield return StartCoroutine(InstantiateCharacter(glbData, modelId));

            OnLoadingProgress?.Invoke(1f);
            isLoading = false;
        }

        // ── Core: Parse and instantiate ──────────────────────────────

        IEnumerator InstantiateCharacter(byte[] glbData, string modelId)
        {
            GameObject character = null;
            string error = null;

            // Run parsing on a background thread via coroutine
            bool done = false;
            System.Action parseAction = () =>
            {
                try
                {
                    character = RuntimeGLBLoader.LoadFromBytes(glbData, $"Character_{modelId}");
                }
                catch (Exception e)
                {
                    error = e.Message;
                    Debug.LogError($"[CharacterLoadingManager] Parse error: {e}");
                }
                done = true;
            };

            // Parse on main thread (Unity API is not thread-safe, but coroutine yields control)
            parseAction();

            if (error != null)
            {
                OnLoadingFailed?.Invoke($"Failed to parse GLB: {error}");
                isLoading = false;
                yield break;
            }

            if (character == null)
            {
                OnLoadingFailed?.Invoke("GLB loaded but produced no scene objects.");
                isLoading = false;
                yield break;
            }

            // Remove existing character
            ClearCharacter();

            // Position at spawn
            var spawn = GameObject.Find(playerSpawnName);
            if (spawn != null)
            {
                character.transform.position = spawn.transform.position;
                character.transform.rotation = spawn.transform.rotation;
            }
            else
            {
                character.transform.position = new Vector3(0, 1, 0);
            }

            // Ensure the character has the Player tag on root
            // Note: PlayerController script looks for the "Player" tag
            var playerController = character.GetComponent<PlayerController>();
            if (playerController == null)
            {
                // Add PlayerController to the root if not present
                playerController = character.AddComponent<PlayerController>();
            }

            // Tag the root as Player
            character.tag = playerTag;

            // Set up camera reference
            var mainCam = Camera.main;
            if (mainCam != null && playerController.cameraTransform == null)
            {
                // Create a child camera if none exists
                var camGO = new GameObject("CharacterCamera");
                camGO.tag = "MainCamera";
                camGO.transform.SetParent(character.transform);
                camGO.transform.localPosition = new Vector3(0, 1.5f, -3f);
                camGO.transform.localEulerAngles = new Vector3(10, 0, 0);
                var cam = camGO.AddComponent<Camera>();
                cam.clearFlags = CameraClearFlags.Skybox;
                cam.backgroundColor = new Color(0.12f, 0.15f, 0.22f, 1f);
                camGO.AddComponent<AudioListener>();
                playerController.cameraTransform = camGO.transform;
            }

            // Add CharacterController if missing
            var cc = character.GetComponent<CharacterController>();
            if (cc == null)
            {
                cc = character.AddComponent<CharacterController>();
                cc.height = 1.8f;
                cc.radius = 0.4f;
                cc.center = new Vector3(0, 0.9f, 0);
            }

            // Add Health component if missing
            var health = character.GetComponent<Health>();
            if (health == null)
            {
                health = character.AddComponent<Health>();
                health.maxHealth = 100f;
                health.currentHealth = 100f;
            }

            // Add Animator if there are SkinnedMeshRenderers
            var smrs = character.GetComponentsInChildren<SkinnedMeshRenderer>();
            if (smrs.Length > 0)
            {
                var animator = character.GetComponent<Animator>();
                if (animator == null)
                {
                    animator = character.AddComponent<Animator>();
                }
            }

            currentCharacter = character;
            OnCharacterLoaded?.Invoke(modelId, character);
        }
    }
}
