using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.InputSystem;

namespace UnreliableProphecy
{
    /// <summary>
    /// Ensures gameplay scenes have a Camera and Player even when the scene was generated empty.
    /// Now handles all 7 region scenes (R1-R7) as defined in SceneRegistry.
    /// </summary>
    public static class GameplayInitializer
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Init()
        {
            SceneManager.sceneLoaded += OnSceneLoaded;
            // Also check already-loaded scene (for editor play)
            var active = SceneManager.GetActiveScene();
            if (IsRegionScene(active.name))
                EnsureScene(active);
        }

        static void OnSceneLoaded(Scene scene, LoadSceneMode mode)
        {
            EnsureScene(scene);
        }

        static bool IsRegionScene(string sceneName)
        {
            var id = SceneRegistry.GetIdentifierByName(sceneName);
            if (!id.HasValue) return false;
            return SceneRegistry.IsRegionScene(id.Value) || id.Value == SceneRegistry.SceneIdentifier.Quietvale 
                || id.Value == SceneRegistry.SceneIdentifier.BureaucracyHills
                || id.Value == SceneRegistry.SceneIdentifier.Forest
                || id.Value == SceneRegistry.SceneIdentifier.CityOfForms
                || id.Value == SceneRegistry.SceneIdentifier.Archives
                || id.Value == SceneRegistry.SceneIdentifier.Ruins
                || id.Value == SceneRegistry.SceneIdentifier.FinalZone
                || id.Value == SceneRegistry.SceneIdentifier.CombatTest;
        }

        static void EnsureScene(Scene scene)
        {
            var id = SceneRegistry.GetIdentifierByName(scene.name);
            if (!id.HasValue) return;
            
            var entry = SceneRegistry.GetScene(id.Value);
            if (entry.Mode != SceneRegistry.LoadMode.Additive && id.Value != SceneRegistry.SceneIdentifier.CombatTest) return;
            
            Debug.Log($"[Gameplay] Ensuring scene {scene.name} has Camera/Player/Lighting");
            EnsureLight(scene);
            EnsureCamera(scene);
            EnsurePlayer(scene);
        }

        static void EnsureLight(Scene scene)
        {
            // Check if any light exists in the scene
            foreach (var root in scene.GetRootGameObjects())
            {
                if (root.GetComponentInChildren<Light>() != null) return;
            }
            
            var go = new GameObject("Directional Light");
            go.transform.SetParent(null);
            scene.AddRootObject(go.transform);
            var light = go.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1f;
            go.transform.rotation = Quaternion.Euler(50f, -30f, 0f);
            Debug.Log("[Gameplay] Created Directional Light");
        }

        static void EnsureCamera(Scene scene)
        {
            if (Camera.main != null) return;
            
            // If player exists with a child camera, use that
            var player = GameObject.FindGameObjectWithTag("Player");
            if (player != null)
            {
                var camInPlayer = player.GetComponentInChildren<Camera>();
                if (camInPlayer != null) return;
            }
            
            var go = new GameObject("Main Camera");
            go.tag = "MainCamera";
            var cam = go.AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.Skybox;
            cam.backgroundColor = new Color(0.12f, 0.15f, 0.22f, 1f);
            go.transform.position = new Vector3(0, 5, -8);
            go.transform.LookAt(Vector3.zero);
            go.AddComponent<AudioListener>();
            Debug.Log("[Gameplay] Created fallback Main Camera");
        }

        static void EnsurePlayer(Scene scene)
        {
            if (GameObject.FindGameObjectWithTag("Player") != null) return;
            
            var spawn = GameObject.Find("Player Spawn");
            Vector3 pos = spawn ? spawn.transform.position : new Vector3(0, 1, 0);
            Quaternion rot = spawn ? spawn.transform.rotation : Quaternion.identity;

            var player = new GameObject("Player");
            player.tag = "Player";
            player.transform.position = pos;
            player.transform.rotation = rot;

            var cc = player.AddComponent<CharacterController>();
            cc.height = 1.8f;
            cc.radius = 0.4f;
            cc.center = new Vector3(0, 0.9f, 0);

            // PlayerInput is optional - try to add if InputSystem is available
            try { player.AddComponent<PlayerInput>(); } catch {}

            var pc = player.AddComponent<PlayerController>();
            pc.walkSpeed = 3.5f;
            pc.sprintSpeed = 5.5f;

            var health = player.AddComponent<Health>();
            health.maxHealth = 100f;
            health.currentHealth = 100f;

            // Child camera
            var camGO = new GameObject("Main Camera");
            camGO.tag = "MainCamera";
            camGO.transform.SetParent(player.transform);
            camGO.transform.localPosition = new Vector3(0, 1.5f, -3f);
            camGO.transform.localEulerAngles = new Vector3(10, 0, 0);
            var cam = camGO.AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.Skybox;
            cam.backgroundColor = new Color(0.12f, 0.15f, 0.22f, 1f);
            camGO.AddComponent<AudioListener>();
            pc.cameraTransform = camGO.transform;

            Debug.Log($"[Gameplay] Spawned Player at {pos} for scene {scene.name}");
        }
    }
}
