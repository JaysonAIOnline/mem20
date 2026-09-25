using UnityEngine;
using UnityEditor;
using UnityEditor.Build;
using System.Collections.Generic;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Editor tool to ensure all registered scenes appear in the build settings.
    /// Run via: Tools/Unreliable Prophecy/Update Build Scenes
    /// </summary>
    public static class BuildSettingsHelper
    {
        [MenuItem("Tools/Unreliable Prophecy/Update Build Scenes")]
        public static void UpdateBuildScenes()
        {
            var scenes = new List<EditorBuildSettingsScene>();

            foreach (var id in SceneRegistry.GetAllScenes())
            {
                var entry = SceneRegistry.GetScene(id);
                string path = $"Assets/Scenes/{entry.SceneName}.unity";

                // Check if scene file exists
                if (!System.IO.File.Exists(System.IO.Path.GetFullPath(path)))
                {
                    Debug.LogWarning($"[BuildSettings] Scene file not found: {path} (skipping)");
                    continue;
                }

                // Check if already in build settings
                bool alreadyExists = EditorBuildSettings.scenes.Any(s => s.path == path);
                if (!alreadyExists)
                {
                    scenes.Add(new EditorBuildSettingsScene(path, true));
                    Debug.Log($"[BuildSettings] Added to build: {entry.SceneName}");
                }
            }

            if (scenes.Count > 0)
            {
                var existingScenes = EditorBuildSettings.scenes.ToList();
                existingScenes.AddRange(scenes);
                EditorBuildSettings.scenes = existingScenes.ToArray();
                Debug.Log($"[BuildSettings] Added {scenes.Count} new scenes to build settings.");
            }
            else
            {
                Debug.Log("[BuildSettings] All scenes already present in build settings.");
            }

            // Verify all scenes are present
            VerifyBuildScenes();
        }

        [MenuItem("Tools/Unreliable Prophecy/Verify Build Scenes")]
        public static void VerifyBuildScenes()
        {
            var buildScenePaths = EditorBuildSettings.scenes.Select(s => s.path).ToHashSet();
            int missing = 0;

            foreach (var id in SceneRegistry.GetAllScenes())
            {
                var entry = SceneRegistry.GetScene(id);
                string path = $"Assets/Scenes/{entry.SceneName}.unity";

                if (!buildScenePaths.Contains(path))
                {
                    Debug.LogError($"[BuildSettings] MISSING from build: {entry.SceneName} ({path})");
                    missing++;
                }
            }

            if (missing == 0)
            {
                Debug.Log("[BuildSettings] All registered scenes are present in build settings.");
            }
            else
            {
                Debug.LogError($"[BuildSettings] {missing} scenes missing from build settings! Run 'Update Build Scenes' to fix.");
            }
        }

        [MenuItem("Tools/Unreliable Prophecy/Create Missing Scenes")]
        public static void CreateMissingScenes()
        {
            int created = 0;

            foreach (var id in SceneRegistry.GetAllScenes())
            {
                var entry = SceneRegistry.GetScene(id);
                string path = $"Assets/Scenes/{entry.SceneName}.unity";
                string fullPath = System.IO.Path.GetFullPath(path);

                if (System.IO.File.Exists(fullPath))
                {
                    continue;
                }

                // Create a new empty scene
                var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

                // Add basic root objects
                var env = new GameObject("Environment");
                var playerSpawn = new GameObject("Player Spawn");
                playerSpawn.transform.position = new Vector3(0, 0, 0);

                // Save the scene
                EditorSceneManager.SaveScene(scene, path);
                Debug.Log($"[BuildSettings] Created scene: {entry.SceneName}");
                created++;
            }

            if (created > 0)
            {
                Debug.Log($"[BuildSettings] Created {created} new scenes.");
                UpdateBuildScenes();
            }
            else
            {
                Debug.Log("[BuildSettings] All scene files already exist.");
            }
        }
    }
}
