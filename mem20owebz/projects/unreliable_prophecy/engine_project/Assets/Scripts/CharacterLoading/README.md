# Runtime GLB Character Loading System

This system allows players to provide their own GLB character model at runtime. It replaces the default player prefab with a custom-loaded 3D model from the backend storage API.

## Architecture

### Components

1. **RuntimeGLBLoader** - Pure C# GLB parser (no dependencies)
   - Parses GLB v2 binary format
   - Handles meshes, materials, transforms, skins, and animations
   - Supports sparse accessors, multiple primitives, vertex colors
   - Works standalone — no Unity Package Manager packages needed

2. **CharacterLoadingManager** - Singleton coordinator
   - Fetches GLB from backend by model ID
   - Validates model existence before download
   - Parses GLB and instantiates into scene
   - Adds required components (PlayerController, CharacterController, Health, Animator)
   - Positions character at Player Spawn point
   - Emits events for UI binding

3. **CharacterLoadingUI** - UI controller
   - Input field for model ID
   - Load/clear buttons
   - Progress bar during download
   - Error display panel

## Setup

1. Add `CharacterLoadingManager` to a GameObject in your scene (e.g., the same GameObject holding `GameplayInitializer`). It's a singleton with `DontDestroyOnLoad`.

2. Configure the backend URL in the Inspector (default: `http://localhost:8000`).

3. Ensure your scene has a "Player Spawn" empty GameObject where the character should appear.

4. For UI, create a Canvas with:
   - TMP_InputField (model ID input)
   - Button (load)
   - Button (clear)
   - Slider (progress)
   - TextMeshPro texts (status, error)
   - Assign all to `CharacterLoadingUI`

## API

```csharp
// Load from backend by model ID
CharacterLoadingManager.Instance.LoadCharacter("mdl_a1b2c3d4e5f6");

// Load from raw bytes (e.g., from file picker)
CharacterLoadingManager.Instance.LoadCharacterFromBytes(glbBytes, "local");

// Clear current character
CharacterLoadingManager.Instance.ClearCharacter();

// Events
CharacterLoadingManager.Instance.OnLoadingStarted.AddListener(...);
CharacterLoadingManager.Instance.OnCharacterLoaded.AddListener(...);
CharacterLoadingManager.Instance.OnLoadingFailed.AddListener(...);
CharacterLoadingManager.Instance.OnLoadingProgress.AddListener(...);
```

## GLB Requirements

The GLB must meet the validation rules from the backend:
- Format: GLB v2
- File size: ≤50 MB
- Triangle count: ≤100,000
- Bones: ≤256
- Must have a skeleton/skin

## Tested Features

- [ ] GLB loading from backend
- [ ] Mesh reconstruction (vertices, normals, UVs, colors)
- [ ] Material conversion (PBR metallic-roughness)
- [ ] Skinned mesh binding
- [ ] Node transforms (TRS + matrix)
- [ ] Error handling (missing model, invalid format, download failure)
