using UnityEngine;
using UnityEngine.SceneManagement;

namespace UnreliableProphecy
{
    /// <summary>
    /// Place this on trigger objects at region boundaries.
    /// When the player enters the trigger, the specified scene transition is performed.
    /// </summary>
    public class SceneTransitionTrigger : MonoBehaviour
    {
        [Header("Transition")]
        public SceneRegistry.SceneIdentifier FromScene;
        public SceneRegistry.SceneIdentifier ToScene;
        public string SpawnPointName;

        [Header("Settings")]
        public bool AutoSave = true;
        public bool DestroyPreviousScene = true;

        private bool _triggered;

        void OnTriggerEnter(Collider other)
        {
            if (_triggered) return;
            if (!other.CompareTag("Player")) return;

            _triggered = true;
            PerformTransition();
        }

        void PerformTransition()
        {
            Debug.Log($"[SceneTransition] Transitioning from {FromScene} to {ToScene}");

            // Autosave before transition
            if (AutoSave && SaveManager.Instance != null)
            {
                SaveManager.Instance.SaveGame(0);
                SaveManager.Instance.OnRegionChanged(SceneRegistry.GetSceneName(ToScene));
            }

            // Start the transition
            if (DestroyPreviousScene)
            {
                SceneLoader.TransitionTo(FromScene, ToScene);
            }
            else
            {
                SceneLoader.LoadScene(ToScene);
            }

            // Teleport player to spawn point after load
            StartCoroutine(TeleportPlayerNextFrame());
        }

        System.Collections.IEnumerator TeleportPlayerNextFrame()
        {
            yield return null;
            yield return null;

            if (string.IsNullOrEmpty(SpawnPointName)) yield break;

            var spawn = GameObject.Find(SpawnPointName);
            if (spawn == null)
            {
                Debug.LogWarning($"[SceneTransition] Spawn point '{SpawnPointName}' not found");
                yield break;
            }

            var player = GameObject.FindGameObjectWithTag("Player");
            if (player != null)
            {
                player.transform.position = spawn.transform.position;
                player.transform.rotation = spawn.transform.rotation;
                Debug.Log($"[SceneTransition] Player teleported to {SpawnPointName}");
            }
        }
    }
}
