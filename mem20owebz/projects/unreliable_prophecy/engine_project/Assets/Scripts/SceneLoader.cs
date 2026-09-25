using UnityEngine;
using UnityEngine.SceneManagement;
using System;
using System.Collections;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Handles scene loading/unloading with support for both single and additive modes.
    /// Provides a clean API for transitioning between scenes and managing additive region scenes.
    /// </summary>
    public static class SceneLoader
    {
        private static readonly HashSet<string> _loadedScenes = new HashSet<string>();
        private static SceneIdentifier? _currentRegion;
        private static bool _isLoading = false;

        public static bool IsLoading => _isLoading;
        public static SceneIdentifier? CurrentRegion => _currentRegion;
        public static IReadOnlyCollection<string> LoadedScenes => _loadedScenes;

        public static event Action<SceneIdentifier> OnSceneLoadStarted;
        public static event Action<SceneIdentifier> OnSceneLoadCompleted;
        public static event Action<SceneIdentifier> OnSceneUnloadStarted;
        public static event Action<SceneIdentifier> OnSceneUnloadCompleted;

        /// <summary>
        /// Load a scene by its identifier. Handles both single and additive modes.
        /// </summary>
        public static Coroutine LoadScene(SceneIdentifier id)
        {
            if (_isLoading)
            {
                Debug.LogWarning($"[SceneLoader] Already loading a scene. Cannot load {id}.");
                return null;
            }

            var entry = SceneRegistry.GetScene(id);
            Debug.Log($"[SceneLoader] Loading scene: {entry.SceneName} (mode: {entry.Mode})");

            var runner = SceneLoaderRunner.Instance;
            return runner.StartCoroutine(LoadSceneCoroutine(id, entry));
        }

        private static IEnumerator LoadSceneCoroutine(SceneIdentifier id, SceneRegistry.SceneEntry entry)
        {
            _isLoading = true;
            OnSceneLoadStarted?.Invoke(id);

            if (entry.Mode == SceneRegistry.LoadMode.Single)
            {
                // Unload all currently loaded scenes first
                yield return UnloadAllScenes();

                var op = SceneManager.LoadSceneAsync(entry.SceneName);
                while (!op.isDone)
                {
                    yield return null;
                }

                _loadedScenes.Add(entry.SceneName);
                _currentRegion = id;
            }
            else
            {
                // Additive mode - load on top of current scene
                if (_loadedScenes.Contains(entry.SceneName))
                {
                    Debug.LogWarning($"[SceneLoader] Scene {entry.SceneName} already loaded.");
                    _isLoading = false;
                    yield break;
                }

                var op = SceneManager.LoadSceneAsync(entry.SceneName, LoadSceneMode.Additive);
                while (!op.isDone)
                {
                    yield return null;
                }

                _loadedScenes.Add(entry.SceneName);
                _currentRegion = id;
                SceneManager.SetActiveScene(SceneManager.GetSceneByName(entry.SceneName));
            }

            _isLoading = false;
            OnSceneLoadCompleted?.Invoke(id);
            Debug.Log($"[SceneLoader] Scene loaded: {entry.SceneName}");
        }

        /// <summary>
        /// Unload a scene by its identifier.
        /// </summary>
        public static Coroutine UnloadScene(SceneIdentifier id)
        {
            var entry = SceneRegistry.GetScene(id);
            if (!_loadedScenes.Contains(entry.SceneName))
            {
                Debug.LogWarning($"[SceneLoader] Scene {entry.SceneName} is not loaded.");
                return null;
            }

            var runner = SceneLoaderRunner.Instance;
            return runner.StartCoroutine(UnloadSceneCoroutine(id, entry));
        }

        private static IEnumerator UnloadSceneCoroutine(SceneIdentifier id, SceneRegistry.SceneEntry entry)
        {
            OnSceneUnloadStarted?.Invoke(id);
            Debug.Log($"[SceneLoader] Unloading scene: {entry.SceneName}");

            var op = SceneManager.UnloadSceneAsync(entry.SceneName);
            while (!op.isDone)
            {
                yield return null;
            }

            _loadedScenes.Remove(entry.SceneName);

            if (_currentRegion == id)
            {
                _currentRegion = null;
            }

            OnSceneUnloadCompleted?.Invoke(id);
            Debug.Log($"[SceneLoader] Scene unloaded: {entry.SceneName}");
        }

        /// <summary>
        /// Transition from one scene to another. Unloads current region, loads new one.
        /// </summary>
        public static Coroutine TransitionTo(SceneIdentifier from, SceneIdentifier to)
        {
            var runner = SceneLoaderRunner.Instance;
            return runner.StartCoroutine(TransitionCoroutine(from, to));
        }

        private static IEnumerator TransitionCoroutine(SceneIdentifier from, SceneIdentifier to)
        {
            if (_isLoading)
            {
                Debug.LogWarning("[SceneLoader] Already loading. Cannot transition.");
                yield break;
            }

            // Trigger autosave on region transition
            if (SceneRegistry.IsRegionScene(from))
            {
                SaveManager.Instance?.OnRegionChanged(SceneRegistry.GetSceneName(to));
            }

            // Unload current region
            if (from != SceneIdentifier.Boot && from != SceneIdentifier.MainMenu)
            {
                yield return UnloadScene(from);
            }

            // Load new region
            yield return LoadScene(to);
        }

        /// <summary>
        /// Unload all currently loaded scenes.
        /// </summary>
        public static IEnumerator UnloadAllScenes()
        {
            var scenesToUnload = new List<string>(_loadedScenes);
            foreach (var sceneName in scenesToUnload)
            {
                var op = SceneManager.UnloadSceneAsync(sceneName);
                while (!op.isDone)
                {
                    yield return null;
                }
            }
            _loadedScenes.Clear();
            _currentRegion = null;
        }

        /// <summary>
        /// Check if a scene is currently loaded.
        /// </summary>
        public static bool IsSceneLoaded(SceneIdentifier id)
        {
            var entry = SceneRegistry.GetScene(id);
            return _loadedScenes.Contains(entry.SceneName);
        }

        /// <summary>
        /// Get the currently active region scene.
        /// </summary>
        public static string GetCurrentRegionSceneName()
        {
            return _currentRegion.HasValue ? SceneRegistry.GetSceneName(_currentRegion.Value) : null;
        }
    }

    /// <summary>
    /// Singleton MonoBehaviour to run scene loading coroutines.
    /// </summary>
    public class SceneLoaderRunner : MonoBehaviour
    {
        public static SceneLoaderRunner Instance { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureExists()
        {
            if (Instance == null)
            {
                var go = new GameObject("SceneLoaderRunner");
                Instance = go.AddComponent<SceneLoaderRunner>();
                DontDestroyOnLoad(go);
            }
        }
    }
}
