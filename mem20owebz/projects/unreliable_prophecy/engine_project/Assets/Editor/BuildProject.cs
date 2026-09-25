using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEditor.Build;
using UnityEngine.AI;
using UnityEngine.InputSystem;
using System.IO;
using System.Collections.Generic;
using UnreliableProphecy;

/// <summary>
/// Editor script to build the Unity project structure and import assets.
/// Run via: Unity -batchmode -executeMethod BuildProject.SetupProject
/// </summary>
public class BuildProject
{
    [MenuItem("Tools/Unreliable Prophecy/Setup Project")]
    public static void SetupProject()
    {
        string projectPath = "Assets";
        
        // Create folder structure
        CreateFolderStructure();
        
        // Import GLB assets
        ImportGLBAssets();
        
        // Create materials
        CreateMaterials();
        
        // Create scenes
        CreateScenes();
        
        // Create prefabs
        CreatePrefabs();
        
        // Configure build settings
        ConfigureBuildSettings();
        
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        
        Debug.Log("Unreliable Prophecy project setup complete!");
    }
    
    static void CreateFolderStructure()
    {
        string[] folders = new string[]
        {
            "Assets/Scripts",
            "Assets/Scenes",
            "Assets/Prefabs",
            "Assets/Materials",
            "Assets/Models/Characters",
            "Assets/Models/Creatures",
            "Assets/Models/Props",
            "Assets/Models/Weapons",
            "Assets/Models/Environments",
            "Assets/UI",
            "Assets/Resources",
            "Assets/Audio/VO",
            "Assets/Audio/Music",
            "Assets/Audio/SFX",
            "Assets/Animation",
            "Assets/Animation/Characters",
            "Assets/Animation/Creatures",
            "Assets/Shaders",
            "Assets/VFX",
        };
        
        foreach (string folder in folders)
        {
            if (!AssetDatabase.IsValidFolder(folder))
            {
                string parent = Path.GetDirectoryName(folder);
                string name = Path.GetFileName(folder);
                if (parent == "Assets")
                    AssetDatabase.CreateFolder("Assets", name);
                else
                    AssetDatabase.CreateFolder(parent, name);
            }
        }
    }
    
    static void ImportGLBAssets()
    {
        string artRoot = Path.GetFullPath("../art");
        if (!Directory.Exists(artRoot))
        {
            Debug.LogWarning($"Art directory not found: {artRoot}");
            return;
        }
        
        // Character models
        ImportGLB(artRoot + "/characters/CH_PC1.glb", "Assets/Models/Characters/CH_PC1");
        ImportGLB(artRoot + "/characters/CH_Wizard.glb", "Assets/Models/Characters/CH_Wizard");
        ImportGLB(artRoot + "/characters/CH_Companion2.glb", "Assets/Models/Characters/CH_Companion2");
        ImportGLB(artRoot + "/characters/CH_Bureaucrat.glb", "Assets/Models/Characters/CH_Bureaucrat");
        
        // Creature models
        ImportGLB(artRoot + "/creatures/CR_MisfiledSkeleton.glb", "Assets/Models/Creatures/CR_MisfiledSkeleton");
        ImportGLB(artRoot + "/creatures/CR_InkBlot.glb", "Assets/Models/Creatures/CR_InkBlot");
        
        // Prop models
        ImportGLB(artRoot + "/props/PR_Binder.glb", "Assets/Models/Props/PR_Binder");
        ImportGLB(artRoot + "/props/PR_Desk.glb", "Assets/Models/Props/PR_Desk");
        ImportGLB(artRoot + "/props/PR_FilingCabinet.glb", "Assets/Models/Props/PR_FilingCabinet");
        ImportGLB(artRoot + "/props/PR_Forms.glb", "Assets/Models/Props/PR_Forms");
        
        // Weapon models
        ImportGLB(artRoot + "/weapons/WP_BasicMelee.glb", "Assets/Models/Weapons/WP_BasicMelee");
        
        // Environment models
        ImportGLB(artRoot + "/environments/ENV_Quietvale.glb", "Assets/Models/Environments/ENV_Quietvale");
        ImportGLB(artRoot + "/environments/ENV_Hills.glb", "Assets/Models/Environments/ENV_Hills");
        
        // Materials
        if (File.Exists(artRoot + "/materials/UP_Materials.blend"))
        {
            AssetDatabase.ImportAsset("Assets/Materials/UP_Materials.blend");
        }
    }
    
    static void ImportGLB(string sourcePath, string destFolder)
    {
        if (!File.Exists(sourcePath))
        {
            Debug.LogWarning($"GLB not found: {sourcePath}");
            return;
        }
        
        string fileName = Path.GetFileName(sourcePath);
        string destPath = destFolder + "/" + fileName;
        
        // Create destination folder
        string folderPath = destFolder;
        string[] parts = folderPath.Split('/');
        string currentPath = "Assets";
        for (int i = 1; i < parts.Length; i++)
        {
            string nextPath = currentPath + "/" + parts[i];
            if (!AssetDatabase.IsValidFolder(nextPath))
            {
                AssetDatabase.CreateFolder(currentPath, parts[i]);
            }
            currentPath = nextPath;
        }
        
        // Copy file
        File.Copy(sourcePath, Path.GetFullPath(destPath), true);
        AssetDatabase.ImportAsset(destPath);
        
        Debug.Log($"Imported {fileName} to {destPath}");
    }
    
    static void CreateMaterials()
    {
        // Materials are imported from UP_Materials.blend
        // Create fallback materials if needed
        CreateMaterial("MAT_Parchment", new Color(0.92f, 0.88f, 0.78f), 0f, 0.9f);
        CreateMaterial("MAT_Wood", new Color(0.45f, 0.30f, 0.18f), 0f, 0.7f);
        CreateMaterial("MAT_MetalStamp", new Color(0.55f, 0.55f, 0.58f), 0.9f, 0.3f);
        CreateMaterial("MAT_Ink", new Color(0.05f, 0.03f, 0.08f), 0f, 0.3f);
        CreateMaterial("MAT_Skin", new Color(0.95f, 0.78f, 0.65f), 0f, 0.6f);
        CreateMaterial("MAT_Robe", new Color(0.25f, 0.20f, 0.35f), 0f, 0.8f);
        CreateMaterial("MAT_Robe_Cynical", new Color(0.15f, 0.12f, 0.25f), 0f, 0.85f);
        CreateMaterial("MAT_Bureaucrat", new Color(0.40f, 0.35f, 0.30f), 0.1f, 0.6f);
        CreateMaterial("MAT_Bone", new Color(0.85f, 0.80f, 0.70f), 0f, 0.5f);
        CreateMaterial("MAT_InkCreature", new Color(0.02f, 0.01f, 0.05f), 0f, 0.2f);
    }
    
    static Material CreateMaterial(string name, Color color, float metallic, float roughness)
    {
        string path = $"Assets/Materials/{name}.mat";
        Material mat = AssetDatabase.LoadAssetAtPath<Material>(path);
        
        if (mat == null)
        {
            mat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
            AssetDatabase.CreateAsset(mat, path);
        }
        
        mat.color = color;
        mat.SetFloat("_Metallic", metallic);
        mat.SetFloat("_Smoothness", 1f - roughness);
        mat.name = name;
        
        EditorUtility.SetDirty(mat);
        return mat;
    }
    
    static void CreateScenes()
    {
        // Boot Scene
        CreateScene("Boot", new string[] { "[BootManager]" });
        
        // MainMenu Scene
        CreateScene("MainMenu", new string[] { "[MainMenuManager]", "UI Canvas" });
        
        // Quietvale Scene
        CreateScene("Quietvale", new string[] 
        { 
            "Environment", "Player Spawn", "NPCs", "Enemies", 
            "Quest Objects", "UI Canvas" 
        });
        
        // BureaucracyHills Scene
        CreateScene("BureaucracyHills", new string[] 
        { 
            "Environment", "Player Spawn", "NPCs", "Enemies", 
            "Quest Objects", "UI Canvas" 
        });
        
        // CombatTest Scene
        CreateScene("CombatTest", new string[] { "Environment", "Player Spawn", "Enemies" });
    }
    
    static void CreateScene(string name, string[] rootObjects)
    {
        string path = $"Assets/Scenes/{name}.unity";
        
        if (File.Exists(Path.GetFullPath(path)))
        {
            Debug.Log($"Scene {name} already exists");
            return;
        }
        
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        
        foreach (string objName in rootObjects)
        {
            var go = new GameObject(objName);
            if (objName.StartsWith("["))
            {
                // Manager - will be added via script
                UnityEngine.Object.DestroyImmediate(go);
            }
        }
        
        EditorSceneManager.SaveScene(scene, path);
        Debug.Log($"Created scene: {name}");
    }
    
    static void CreatePrefabs()
    {
        // Player Prefab
        CreatePlayerPrefab();
        
        // Companion Prefabs
        CreateCompanionPrefab("CH_Wizard", "Old Wizard");
        CreateCompanionPrefab("CH_Companion2", "Organized Sorceress");
        
        // NPC Prefabs
        CreateNPCPrefab("CH_Bureaucrat", "Celestial Bureaucrat");
        
        // Enemy Prefabs
        CreateEnemyPrefab("CR_MisfiledSkeleton", EnemyAI.EnemyType.MisfiledSkeleton);
        CreateEnemyPrefab("CR_InkBlot", EnemyAI.EnemyType.InkBlot);
        
        // Prop Prefabs
        CreatePropPrefab("PR_Binder");
        CreatePropPrefab("PR_FilingCabinet");
        CreatePropPrefab("PR_Desk");
        CreatePropPrefab("PR_Forms");
        
        // Weapon Prefabs
        CreateWeaponPrefab("WP_BasicMelee");
        
        // UI Prefabs
        CreateUIPrefabs();
    }
    
    static void CreatePlayerPrefab()
    {
        var go = new GameObject("CH_PC1_Player");
        go.tag = "Player";
        
        // Add components
        var controller = go.AddComponent<CharacterController>();
        controller.height = 1.8f;
        controller.radius = 0.4f;
        controller.center = new Vector3(0, 0.9f, 0);
        
        var playerInput = go.AddComponent<PlayerInput>();
        
        var pc = go.AddComponent<PlayerController>();
        pc.walkSpeed = 3.5f;
        pc.sprintSpeed = 5.5f;
        
        // Add camera
        var cam = new GameObject("Main Camera");
        cam.transform.SetParent(go.transform);
        cam.transform.localPosition = new Vector3(0, 1.5f, -3f);
        cam.AddComponent<Camera>();
        cam.tag = "MainCamera";
        pc.cameraTransform = cam.transform;
        
        // Save prefab
        SavePrefab(go, "Assets/Prefabs/CH_PC1_Player.prefab");
    }
    
    static void CreateCompanionPrefab(string id, string displayName)
    {
        var go = new GameObject(id);
        go.tag = "Companion";
        
        var agent = go.AddComponent<NavMeshAgent>();
        agent.speed = 3.5f;
        agent.stoppingDistance = 2f;
        
        var animator = go.AddComponent<Animator>();
        
        // Save prefab
        SavePrefab(go, $"Assets/Prefabs/{id}.prefab");
    }
    
    static void CreateNPCPrefab(string id, string displayName)
    {
        var go = new GameObject(id);
        go.tag = "NPC";
        
        var interactable = go.AddComponent<BureaucratNPC>();
        interactable.interactableName = displayName;
        
        var agent = go.AddComponent<NavMeshAgent>();
        agent.speed = 2f;
        
        SavePrefab(go, $"Assets/Prefabs/{id}.prefab");
    }
    
    static void CreateEnemyPrefab(string id, EnemyAI.EnemyType type)
    {
        var go = new GameObject(id);
        go.tag = "Enemy";
        
        var enemyAI = go.AddComponent<EnemyAI>();
        enemyAI.enemyId = id;
        enemyAI.type = type;
        
        var controller = go.AddComponent<CharacterController>();
        controller.height = 1.8f;
        controller.radius = 0.4f;
        
        var agent = go.AddComponent<NavMeshAgent>();
        agent.speed = 3f;
        
        var health = go.AddComponent<Health>();
        health.maxHealth = 50f;
        
        SavePrefab(go, $"Assets/Prefabs/{id}.prefab");
    }
    
    static void CreatePropPrefab(string id)
    {
        var go = new GameObject(id);
        
        switch (id)
        {
            case "PR_Binder":
                var binder = go.AddComponent<WorldInteractable>();
                binder.type = InteractionType.Binder;
                binder.interactableName = "Prophecy Binder";
                break;
            case "PR_FilingCabinet":
                var cabinet = go.AddComponent<FilingCabinet>();
                cabinet.interactableName = "Filing Cabinet";
                break;
            case "PR_Desk":
                var desk = go.AddComponent<DeskInteractable>();
                desk.interactableName = "Bureaucrat's Desk";
                break;
            case "PR_Forms":
                var forms = go.AddComponent<FormItem>();
                forms.type = InteractionType.Form;
                break;
        }
        
        var collider = go.AddComponent<BoxCollider>();
        
        SavePrefab(go, $"Assets/Prefabs/{id}.prefab");
    }
    
    static void CreateWeaponPrefab(string id)
    {
        var go = new GameObject(id);
        go.tag = "Weapon";
        
        var collider = go.AddComponent<BoxCollider>();
        collider.isTrigger = true;
        
        SavePrefab(go, $"Assets/Prefabs/{id}.prefab");
    }
    
    static void CreateUIPrefabs()
    {
        // Quest Tracker UI
        var questTracker = new GameObject("UI_QuestTracker");
        var canvas = questTracker.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        var trackerUI = questTracker.AddComponent<QuestTrackerUI>();
        
        SavePrefab(questTracker, "Assets/Prefabs/UI_QuestTracker.prefab");
        
        // Binder UI
        var binderUI = new GameObject("UI_Binder");
        var binderCanvas = binderUI.AddComponent<Canvas>();
        binderCanvas.renderMode = RenderMode.ScreenSpaceOverlay;
        binderCanvas.sortingOrder = 10;
        
        SavePrefab(binderUI, "Assets/Prefabs/UI_Binder.prefab");
        
        // Main Menu UI
        var mainMenu = new GameObject("UI_MainMenu");
        var mmCanvas = mainMenu.AddComponent<Canvas>();
        mmCanvas.renderMode = RenderMode.ScreenSpaceOverlay;
        
        SavePrefab(mainMenu, "Assets/Prefabs/UI_MainMenu.prefab");
    }
    
    static void SavePrefab(GameObject go, string path)
    {
        string folder = Path.GetDirectoryName(path);
        if (!AssetDatabase.IsValidFolder(folder))
        {
            string[] parts = folder.Split('/');
            string currentPath = "Assets";
            for (int i = 1; i < parts.Length; i++)
            {
                string nextPath = currentPath + "/" + parts[i];
                if (!AssetDatabase.IsValidFolder(nextPath))
                    AssetDatabase.CreateFolder(currentPath, parts[i]);
                currentPath = nextPath;
            }
        }
        
        PrefabUtility.SaveAsPrefabAsset(go, path);
        UnityEngine.Object.DestroyImmediate(go);
        Debug.Log($"Created prefab: {path}");
    }
    
    static void ConfigureBuildSettings()
    {
        var scenes = new List<EditorBuildSettingsScene>
        {
            new EditorBuildSettingsScene("Assets/Scenes/Boot.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/MainMenu.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/Quietvale.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/BureaucracyHills.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/Forest.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/CityOfForms.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/Archives.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/Ruins.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/FinalZone.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/CombatTest.unity", true),
        };

        EditorBuildSettings.scenes = scenes.ToArray();

        // Player settings
        PlayerSettings.productName = "The Unreliable Prophecy";
        PlayerSettings.companyName = "Jayson";

        // Platform-specific settings
        ConfigureWindowsSettings();
        ConfigureLinuxSettings();

        Debug.Log("Build settings configured for Windows Standalone x64 and Linux x64");
    }
    
    static void ConfigureWindowsSettings()
    {
        // Windows-specific settings
        PlayerSettings.defaultScreenWidth = 1920;
        PlayerSettings.defaultScreenHeight = 1080;
        PlayerSettings.resizableWindow = true;
        PlayerSettings.runInBackground = true;
        
        // Windows x64 specific
        PlayerSettings.stripEngineCode = true;
        PlayerSettings.stripUnusedMeshComponents = true;
    }
    
    static void ConfigureLinuxSettings()
    {
        // Linux-specific settings
        PlayerSettings.defaultScreenWidth = 1920;
        PlayerSettings.defaultScreenHeight = 1080;
        PlayerSettings.resizableWindow = true;
        PlayerSettings.runInBackground = true;
        
        // Linux x64 specific
        PlayerSettings.stripEngineCode = true;
        PlayerSettings.stripUnusedMeshComponents = true;
    }
    
    static List<EditorBuildSettingsScene> GetBuildScenes()
    {
        return new List<EditorBuildSettingsScene>
        {
            new EditorBuildSettingsScene("Assets/Scenes/Boot.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/MainMenu.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/Quietvale.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/BureaucracyHills.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/Forest.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/CityOfForms.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/Archives.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/Ruins.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/FinalZone.unity", true),
            new EditorBuildSettingsScene("Assets/Scenes/CombatTest.unity", true),
        };
    }
    
    [MenuItem("Tools/Unreliable Prophecy/Build Windows")]
    public static void BuildWindows()
    {
        string buildPath = "Builds/Windows/v0.5.0_VerticalSlice/TheUnreliableProphecy.exe";
        BuildPipeline.BuildPlayer(
            GetBuildScenes().ToArray(),
            buildPath,
            BuildTarget.StandaloneWindows64,
            BuildOptions.None
        );
        Debug.Log($"Windows build complete: {buildPath}");
    }
    
    [MenuItem("Tools/Unreliable Prophecy/Build Linux")]
    public static void BuildLinux()
    {
        string buildPath = "Builds/Linux/v0.5.0_VerticalSlice/TheUnreliableProphecy";
        BuildPipeline.BuildPlayer(
            GetBuildScenes().ToArray(),
            buildPath,
            BuildTarget.StandaloneLinux64,
            BuildOptions.None
        );
        Debug.Log($"Linux build complete: {buildPath}");
    }
    
    [MenuItem("Tools/Unreliable Prophecy/Build Both")]
    public static void BuildBoth()
    {
        BuildWindows();
        BuildLinux();
        Debug.Log("Both Windows and Linux builds complete!");
    }

    [MenuItem("Tools/Unreliable Prophecy/Build Linux Smoke")]
    public static void BuildLinuxSmoke()
    {
        var scenePath = "Assets/Scenes/MainMenu.unity";
        var scene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);

        // Inject the headless smoke harness for this test build only.
        var harness = new GameObject("SmokeTest");
        harness.AddComponent<SmokeTest>();
        EditorSceneManager.SaveScene(scene);

        string buildPath = "Builds/Smoke/TheUnreliableProphecy";
        BuildPipeline.BuildPlayer(
            GetBuildScenes().ToArray(),
            buildPath,
            BuildTarget.StandaloneLinux64,
            BuildOptions.None
        );
        Debug.Log($"Smoke build complete: {buildPath}");

        // Restore MainMenu.unity to its clean state (no harness).
        UnityEngine.Object.DestroyImmediate(harness);
        EditorSceneManager.SaveScene(scene);
    }
}