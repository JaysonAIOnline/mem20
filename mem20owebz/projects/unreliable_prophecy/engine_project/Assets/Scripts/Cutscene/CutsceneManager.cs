using UnityEngine;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Manages cinematic cutscenes: camera tracks, sequenced events, and player control.
    /// Supports spline-based camera paths, timed events, and quest-integration triggers.
    /// </summary>
    public class CutsceneManager : MonoBehaviour
    {
        public static CutsceneManager Instance { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureExists()
        {
            if (Instance == null)
            {
                var go = new GameObject(typeof(CutsceneManager).Name);
                Instance = go.AddComponent<CutsceneManager>();
            }
        }

        [Header("Camera Settings")]
        public Camera cutsceneCamera;
        public Camera mainCamera;
        public float defaultBlendTime = 0.5f;
        public float defaultFOV = 60f;

        [Header("UI")]
        public GameObject cutsceneOverlay;
        public GameObject skipPrompt;

        // State
        private bool isPlaying = false;
        private Coroutine playbackCoroutine;
        private CutsceneData activeCutscene;
        private List<CutsceneEventData> eventTimeline = new List<CutsceneEventData>();
        private int currentEventIndex;

        // Events
        public event Action<CutsceneData> OnCutsceneStarted;
        public event Action<CutsceneData> OnCutsceneCompleted;
        public event Action<CutsceneEventData> OnCutsceneEventTriggered;

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            // Create cutscene camera if needed
            EnsureCutsceneCamera();
        }

        void Update()
        {
            if (!isPlaying) return;

            // Skip input
            if (Input.GetKeyDown(KeyCode.Escape) || Input.GetKeyDown(KeyCode.Space))
            {
                SkipCutscene();
            }
        }

        void EnsureCutsceneCamera()
        {
            if (cutsceneCamera == null)
            {
                var camObj = new GameObject("CutsceneCamera");
                camObj.transform.SetParent(transform);
                cutsceneCamera = camObj.AddComponent<Camera>();
                cutsceneCamera.fieldOfView = defaultFOV;
                cutsceneCamera.enabled = false;
                camObj.AddComponent<AudioListener>();
            }

            if (mainCamera == null)
            {
                mainCamera = Camera.main;
            }
        }

        /// <summary>
        /// Plays a cutscene from a CutsceneData ScriptableObject.
        /// </summary>
        public void PlayCutscene(CutsceneData data)
        {
            if (isPlaying || data == null) return;

            activeCutscene = data;
            EnsureCutsceneCamera();

            // Build event timeline from the cutscene data
            eventTimeline = new List<CutsceneEventData>(data.events);
            eventTimeline.Sort((a, b) => a.startTime.CompareTo(b.startTime));
            currentEventIndex = 0;

            playbackCoroutine = StartCoroutine(PlaybackCoroutine());
        }

        /// <summary>
        /// Plays a cutscene by name from a registry.
        /// </summary>
        public void PlayCutscene(string cutsceneId)
        {
            var registry = CutsceneRegistry.Instance;
            if (registry == null) return;

            var data = registry.GetCutscene(cutsceneId);
            if (data != null)
            {
                PlayCutscene(data);
            }
            else
            {
                Debug.LogWarning($"[CutsceneManager] Cutscene '{cutsceneId}' not found in registry");
            }
        }

        private IEnumerator PlaybackCoroutine()
        {
            isPlaying = true;

            // Disable player
            SetPlayerControl(false);

            // Switch to cutscene camera
            if (mainCamera != null) mainCamera.enabled = false;
            cutsceneCamera.enabled = true;

            // Show overlay
            if (cutsceneOverlay != null) cutsceneOverlay.SetActive(true);
            if (skipPrompt != null) skipPrompt.SetActive(true);

            // Initialize camera at first keyframe position
            if (activeCutscene.cameraTrack != null && activeCutscene.cameraTrack.keyframes.Count > 0)
            {
                ApplyCameraKeyframe(activeCutscene.cameraTrack.keyframes[0]);
            }

            OnCutsceneStarted?.Invoke(activeCutscene);

            float elapsed = 0f;
            float duration = activeCutscene.duration;

            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;

                // Update camera track
                if (activeCutscene.cameraTrack != null)
                {
                    UpdateCameraTrack(elapsed);
                }

                // Fire events whose time has come
                while (currentEventIndex < eventTimeline.Count && eventTimeline[currentEventIndex].startTime <= elapsed)
                {
                    FireEvent(eventTimeline[currentEventIndex]);
                    currentEventIndex++;
                }

                yield return null;
            }

            // Complete the cutscene
            CompleteCutscene();
        }

        private void UpdateCameraTrack(float elapsed)
        {
            var track = activeCutscene.cameraTrack;
            if (track.keyframes.Count == 0) return;

            // Find the two keyframes we're between
            CameraKeyframe prev = track.keyframes[0];
            CameraKeyframe next = track.keyframes[track.keyframes.Count - 1];

            for (int i = 0; i < track.keyframes.Count - 1; i++)
            {
                if (track.keyframes[i].time <= elapsed && track.keyframes[i + 1].time >= elapsed)
                {
                    prev = track.keyframes[i];
                    next = track.keyframes[i + 1];
                    break;
                }
            }

            // Interpolate
            float segmentDuration = next.time - prev.time;
            float t = segmentDuration > 0.001f ? (elapsed - prev.time) / segmentDuration : 1f;

            // Apply interpolation type
            float smoothT = ApplyInterpolation(t, track.interpolationType);

            cutsceneCamera.transform.position = Vector3.Lerp(prev.position, next.position, smoothT);
            cutsceneCamera.transform.rotation = Quaternion.Slerp(prev.rotation, next.rotation, smoothT);
            cutsceneCamera.fieldOfView = Mathf.Lerp(prev.fov, next.fov, smoothT);
        }

        private float ApplyInterpolation(float t, InterpolationType type)
        {
            return type switch
            {
                InterpolationType.Linear => t,
                InterpolationType.EaseInOut => Mathf.SmoothStep(0f, 1f, t),
                InterpolationType.EaseIn => t * t,
                InterpolationType.EaseOut => 1f - (1f - t) * (1f - t),
                InterpolationType.Step => t >= 1f ? 1f : 0f,
                _ => t
            };
        }

        private void ApplyCameraKeyframe(CameraKeyframe keyframe)
        {
            cutsceneCamera.transform.position = keyframe.position;
            cutsceneCamera.transform.rotation = keyframe.rotation;
            cutsceneCamera.fieldOfView = keyframe.fov;
        }

        private void FireEvent(CutsceneEventData evt)
        {
            OnCutsceneEventTriggered?.Invoke(evt);

            switch (evt.eventType)
            {
                case CutsceneEventType.PlayAnimation:
                    PlayAnimationEvent(evt);
                    break;
                case CutsceneEventType.TriggerQuest:
                    TriggerQuestEvent(evt);
                    break;
                case CutsceneEventType.PlayAudio:
                    PlayAudioEvent(evt);
                    break;
                case CutsceneEventType.ShowUI:
                    ShowUIEvent(evt);
                    break;
                case CutsceneEventType.SpawnObject:
                    SpawnObjectEvent(evt);
                    break;
                case CutsceneEventType.FadeToBlack:
                    StartCoroutine(FadeToBlackEvent(evt));
                    break;
                case CutsceneEventType.FadeFromBlack:
                    StartCoroutine(FadeFromBlackEvent(evt));
                    break;
                case CutsceneEventType.SetPlayerPosition:
                    SetPlayerPositionEvent(evt);
                    break;
                case CutsceneEventType.EnableObject:
                    EnableObjectEvent(evt);
                    break;
                case CutsceneEventType.DisableObject:
                    DisableObjectEvent(evt);
                    break;
                default:
                    Debug.Log($"[CutsceneManager] Unhandled event type: {evt.eventType}");
                    break;
            }
        }

        private void PlayAnimationEvent(CutsceneEventData evt)
        {
            var target = GameObject.Find(evt.targetName);
            if (target != null)
            {
                var anim = target.GetComponent<Animator>();
                if (anim != null)
                {
                    anim.Play(evt.parameter);
                }
            }
        }

        private void TriggerQuestEvent(CutsceneEventData evt)
        {
            var qm = QuestManager.Instance;
            if (qm == null) return;

            switch (evt.parameter)
            {
                case "accept":
                    qm.AcceptQuest(evt.targetName);
                    break;
                case "update":
                    qm.UpdateObjective(evt.targetName, evt.secondaryParameter);
                    break;
                case "complete":
                    // Force complete a quest
                    var quest = qm.GetQuest(evt.targetName);
                    if (quest != null)
                    {
                        quest.status = QuestStatus.Completed;
                        qm.OnQuestCompleted?.Invoke(quest);
                    }
                    break;
                default:
                    Debug.Log($"[CutsceneManager] Unknown quest action: {evt.parameter}");
                    break;
            }
        }

        private void PlayAudioEvent(CutsceneEventData evt)
        {
            var audio = FindObjectOfType<AudioSource>();
            if (audio != null)
            {
                var clip = Resources.Load<AudioClip>($"Audio/Cutscene/{evt.parameter}");
                if (clip != null)
                {
                    audio.PlayOneShot(clip);
                }
            }
        }

        private void ShowUIEvent(CutsceneEventData evt)
        {
            // Find and show a UI element
            var uiObj = GameObject.Find(evt.targetName);
            if (uiObj != null)
            {
                uiObj.SetActive(evt.parameter == "show");
            }
        }

        private void SpawnObjectEvent(CutsceneEventData evt)
        {
            var prefab = Resources.Load<GameObject>($"CutsceneObjects/{evt.parameter}");
            if (prefab != null)
            {
                var spawnPoint = GameObject.Find(evt.targetName);
                Vector3 pos = spawnPoint != null ? spawnPoint.transform.position : Vector3.zero;
                Quaternion rot = spawnPoint != null ? spawnPoint.transform.rotation : Quaternion.identity;
                Instantiate(prefab, pos, rot);
            }
        }

        private System.Collections.IEnumerator FadeToBlackEvent(CutsceneEventData evt)
        {
            // Simple fade implementation - in production, use a fade overlay
            float duration = string.IsNullOrEmpty(evt.secondaryParameter) ? 1f : float.Parse(evt.secondaryParameter);
            float elapsed = 0f;
            // Note: Would reference a fade overlay here
            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                yield return null;
            }
        }

        private System.Collections.IEnumerator FadeFromBlackEvent(CutsceneEventData evt)
        {
            float duration = string.IsNullOrEmpty(evt.secondaryParameter) ? 1f : float.Parse(evt.secondaryParameter);
            float elapsed = 0f;
            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                yield return null;
            }
        }

        private void SetPlayerPositionEvent(CutsceneEventData evt)
        {
            var player = GameObject.FindGameObjectWithTag("Player");
            if (player != null)
            {
                var target = GameObject.Find(evt.targetName);
                if (target != null)
                {
                    player.transform.position = target.transform.position;
                    player.transform.rotation = target.transform.rotation;
                }
            }
        }

        private void EnableObjectEvent(CutsceneEventData evt)
        {
            var obj = GameObject.Find(evt.targetName);
            if (obj != null) obj.SetActive(evt.parameter != "disable");
        }

        private void DisableObjectEvent(CutsceneEventData evt)
        {
            var obj = GameObject.Find(evt.targetName);
            if (obj != null) obj.SetActive(false);
        }

        public void SkipCutscene()
        {
            if (!isPlaying) return;

            StopCoroutine(playbackCoroutine);
            CompleteCutscene();
            Debug.Log("[CutsceneManager] Cutscene skipped by player");
        }

        private void CompleteCutscene()
        {
            isPlaying = false;

            // Re-enable player
            SetPlayerControl(true);

            // Switch back to main camera
            cutsceneCamera.enabled = false;
            if (mainCamera != null) mainCamera.enabled = true;

            // Hide overlay
            if (cutsceneOverlay != null) cutsceneOverlay.SetActive(false);
            if (skipPrompt != null) skipPrompt.SetActive(false);

            OnCutsceneCompleted?.Invoke(activeCutscene);

            // Post-cutscene: trigger next quest if specified
            if (activeCutscene != null && !activeCutscene.nextQuestId.IsEmpty())
            {
                var qm = QuestManager.Instance;
                if (qm != null)
                {
                    qm.AcceptQuest(activeCutscene.nextQuestId);
                }
            }
        }

        private void SetPlayerControl(bool enabled)
        {
            var player = GameObject.FindGameObjectWithTag("Player");
            if (player != null)
            {
                var pc = player.GetComponent<PlayerController>();
                if (pc != null) pc.enabled = enabled;
            }
        }

        public bool IsPlaying => isPlaying;
    }

    // === Data Structures ===

    /// <summary>
    /// ScriptableObject containing all cutscene data: camera track and event timeline.
    /// </summary>
    [CreateAssetMenu(fileName = "CutsceneData", menuName = "Unreliable Prophecy/Cutscene Data")]
    public class CutsceneData : ScriptableObject
    {
        public string cutsceneId;
        public string displayName;
        [TextArea(2, 4)]
        public string description;
        public float duration = 5f;
        public CameraTrackData cameraTrack;
        public List<CutsceneEventData> events = new List<CutsceneEventData>();
        public string nextQuestId; // Quest to auto-start after cutscene
        public bool skippable = true;
        public bool pauseGameDuringCutscene = true;
    }

    [Serializable]
    public class CameraTrackData
    {
        public List<CameraKeyframe> keyframes = new List<CameraKeyframe>();
        public InterpolationType interpolationType = InterpolationType.EaseInOut;
    }

    [Serializable]
    public class CameraKeyframe
    {
        public float time;
        public Vector3 position;
        public Quaternion rotation;
        public float fov = 60f;

        public CameraKeyframe(float t, Vector3 pos, Quaternion rot, float fovVal = 60f)
        {
            time = t;
            position = pos;
            rotation = rot;
            fov = fovVal;
        }
    }

    public enum InterpolationType { Linear, EaseInOut, EaseIn, EaseOut, Step }

    [Serializable]
    public class CutsceneEventData
    {
        public float startTime;
        public CutsceneEventType eventType;
        public string parameter; // Animation name, quest ID, audio clip, etc.
        public string targetName; // GameObject target
        public string secondaryParameter; // Optional secondary data

        public CutsceneEventData(float time, CutsceneEventType type, string param, string target = "", string secondary = "")
        {
            startTime = time;
            eventType = type;
            parameter = param;
            targetName = target;
            secondaryParameter = secondary;
        }
    }

    public enum CutsceneEventType
    {
        PlayAnimation,
        TriggerQuest,
        PlayAudio,
        ShowUI,
        SpawnObject,
        FadeToBlack,
        FadeFromBlack,
        SetPlayerPosition,
        EnableObject,
        DisableObject
    }

    /// <summary>
    /// Registry that tracks all cutscene data assets by ID.
    /// </summary>
    public class CutsceneRegistry : MonoBehaviour
    {
        public static CutsceneRegistry Instance { get; private set; }

        public List<CutsceneData> allCutscenes = new List<CutsceneData>();

        private Dictionary<string, CutsceneData> lookup = new Dictionary<string, CutsceneData>();

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            RebuildLookup();
        }

        public void RebuildLookup()
        {
            lookup.Clear();
            foreach (var cs in allCutscenes)
            {
                if (cs != null && !string.IsNullOrEmpty(cs.cutsceneId))
                {
                    lookup[cs.cutsceneId] = cs;
                }
            }
        }

        public CutsceneData GetCutscene(string id)
        {
            return lookup.TryGetValue(id, out var cs) ? cs : null;
        }
    }
}
