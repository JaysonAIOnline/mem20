using UnityEngine;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using System.Text.Json;
using UnreliableProphecy.Building;

namespace UnreliableProphecy
{
    /// <summary>
    /// Save data structure matching production package §11.4.
    /// Local JSON + backup recovery + version field.
    /// Save slots (3) show region, playtime, timestamp, short status.
    /// Autosave on region transition / tutorial gate.
    /// Round-trip required: save in Hills → quit → load → correct position, quests, inventory, amendment list.
    /// </summary>
    [System.Serializable]
    public class SaveData
    {
        public int version = 1;
        public int slotIndex;
        public string region;
        public float playtime;
        public string timestamp;
        public string status;

        // Player state
        public Vector3Serializable position;
        public Vector3Serializable rotation;
        public float health;
        public float maxHealth;
        public int currentAbility1Cooldown;
        public int currentAbility2Cooldown;

        // Quest state
        public List<QuestSaveData> activeQuests = new List<QuestSaveData>();
        public List<QuestSaveData> completedQuests = new List<QuestSaveData>();

        // Inventory
        public List<InventoryItem> inventory = new List<InventoryItem>();
        public int equippedWeaponIndex = 0;

        // Amendments
        public List<string> collectedAmendments = new List<string>();
        public List<string> guidebookEntries = new List<string>();

        // Companions
        public List<CompanionSaveData> companions = new List<CompanionSaveData>();

        // NPC Relationships (dialogue state persistence)
        public List<NPCRelationshipSaveData> npcRelationships = new List<NPCRelationshipSaveData>();

        // Crafting state
        public List<string> unlockedRecipeIds = new List<string>();
        public List<CraftingSaveData> activeCraftingProcesses = new List<CraftingSaveData>();

        // Equipment customization
        public EquipmentSaveData equipmentData = new EquipmentSaveData();

        // Building state
        public BuildingSaveData buildingData = new BuildingSaveData();
    }

    [System.Serializable]
    public class Vector3Serializable
    {
        public float x, y, z;
        public Vector3Serializable() { }
        public Vector3Serializable(Vector3 v) { x = v.x; y = v.y; z = v.z; }
        public Vector3 ToVector3() => new Vector3(x, y, z);
    }

    [System.Serializable]
    public class QuestSaveData
    {
        public string questId;
        public int status; // QuestStatus enum
        public List<ObjectiveSaveData> objectives = new List<ObjectiveSaveData>();
    }

    [System.Serializable]
    public class ObjectiveSaveData
    {
        public string description;
        public bool isCompleted;
        public int currentAmount;
    }

    [System.Serializable]
    public class InventoryItem
    {
        public string itemId;
        public int quantity;
        public bool isEquipped;
    }

    [System.Serializable]
    public class CompanionSaveData
    {
        public string companionId;
        public Vector3Serializable localPosition;
        public bool isActive;
        public int banterLinesPlayed;
    }

    /// <summary>
    /// Persistent state for an NPC relationship — tracks how many times the player
    /// has spoken to them, their current emotional state, and any relationship flags.
    /// </summary>
    [System.Serializable]
    public class NPCRelationshipSaveData
    {
        public string npcId;
        public int conversationCount;
        public string lastEmotion; // WorldStateService.Emotion enum name
        public List<string> unlockedDialogueFlags = new List<string>();
        public float lastInteractionTime;
    }

    /// <summary>
    /// Save/Load Manager - handles 3 save slots, autosave, round-trip.
    /// </summary>
    public class SaveManager : MonoBehaviour
    {
        public static SaveManager Instance { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureExists()
        {
            if (Instance == null)
            {
                var go = new GameObject(typeof(SaveManager).Name);
                Instance = go.AddComponent<SaveManager>();
            }
        }

        [Header("Settings")]
        public int maxSaveSlots = 3;
        public float autosaveInterval = 60f;
        public bool autosaveOnRegionChange = true;
        public bool autosaveOnTutorialGate = true;

        [Header("Paths")]
        private string saveDirectory;
        private const string SAVE_PREFIX = "save_slot_";
        private const string SAVE_EXTENSION = ".json";

        // State
        private float autosaveTimer;
        private string lastRegion;

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            saveDirectory = Path.Combine(Application.persistentDataPath, "Saves");
            Directory.CreateDirectory(saveDirectory);

            lastRegion = "";
        }

        void Update()
        {
            autosaveTimer += Time.deltaTime;
            if (autosaveTimer >= autosaveInterval)
            {
                autosaveTimer = 0f;
                AutoSave();
            }
        }

        public void OnRegionChanged(string newRegion)
        {
            if (autosaveOnRegionChange && newRegion != lastRegion)
            {
                AutoSave();
                lastRegion = newRegion;
            }
        }

        public void OnTutorialGatePassed()
        {
            if (autosaveOnTutorialGate)
                AutoSave();
        }

        public void SaveGame(int slotIndex)
        {
            var saveData = CollectSaveData();
            saveData.slotIndex = slotIndex;
            saveData.timestamp = System.DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
            saveData.status = $"Slot {slotIndex + 1} - {saveData.region} - {FormatPlaytime(saveData.playtime)}";

            string json = JsonSerializer.Serialize(saveData, new JsonSerializerOptions { WriteIndented = true });
            string path = GetSavePath(slotIndex);
            File.WriteAllText(path, json);

            Debug.Log($"Game saved to slot {slotIndex}: {path}");
        }

        public SaveData LoadGame(int slotIndex)
        {
            string path = GetSavePath(slotIndex);
            if (!File.Exists(path))
            {
                Debug.LogWarning($"No save file at slot {slotIndex}");
                return null;
            }

            string json = File.ReadAllText(path);
            var saveData = JsonSerializer.Deserialize<SaveData>(json);

            Debug.Log($"Game loaded from slot {slotIndex}: {path}");
            return saveData;
        }

        public void ApplySaveData(SaveData data)
        {
            if (data == null) return;

            // Restore player
            var player = GameObject.FindGameObjectWithTag("Player");
            if (player != null)
            {
                var controller = player.GetComponent<PlayerController>();
                if (controller != null)
                {
                    controller.transform.position = data.position.ToVector3();
                    controller.transform.rotation = Quaternion.Euler(data.rotation.ToVector3());
                }

                var health = player.GetComponent<Health>();
                if (health != null)
                {
                    health.currentHealth = data.health;
                    health.maxHealth = data.maxHealth;
                }
            }

            // Restore quests
            var questManager = QuestManager.Instance;
            if (questManager != null)
            {
                foreach (var qData in data.activeQuests)
                {
                    var quest = questManager.GetQuest(qData.questId);
                    if (quest != null)
                    {
                        quest.status = (QuestStatus)qData.status;
                        questManager.activeQuests.Add(quest);

                        foreach (var objData in qData.objectives)
                        {
                            var obj = quest.objectives.FirstOrDefault(o => o.description == objData.description);
                            if (obj != null)
                            {
                                obj.isCompleted = objData.isCompleted;
                                obj.currentAmount = objData.currentAmount;
                            }
                        }
                    }
                }

                foreach (var qData in data.completedQuests)
                {
                    var quest = questManager.GetQuest(qData.questId);
                    if (quest != null)
                    {
                        quest.status = (QuestStatus)qData.status;
                        questManager.completedQuests.Add(quest);
                    }
                }

                questManager.RefreshQuestLists();
            }

            // Restore inventory
            var inventory = InventoryManager.Instance;
            if (inventory != null)
            {
                inventory.Clear();
                foreach (var item in data.inventory)
                {
                    inventory.AddItem(item.itemId, item.quantity);
                    if (item.isEquipped)
                        inventory.EquipItem(item.itemId);
                }
            }

            // Restore amendments & guidebook
            var binder = BinderManager.Instance;
            if (binder != null)
            {
                binder.LoadAmendments(data.collectedAmendments);
                binder.LoadGuidebookEntries(data.guidebookEntries);
            }

            // Restore companions
            var companionManager = CompanionManager.Instance;
            if (companionManager != null)
            {
                foreach (var cData in data.companions)
                {
                    companionManager.RestoreCompanion(cData);
                }
            }

            // Restore NPC relationships
            ApplyNPCRelationships(data.npcRelationships);

            // Restore equipment customization
            var playerEquipment = PlayerEquipment.Instance;
            if (playerEquipment != null)
            {
                // Clear existing equipment
                playerEquipment.Clear();

                // Restore player equipment
                foreach (var eqData in data.equipmentData.playerEquipment)
                {
                    var customEq = new CustomizedEquipment
                    {
                        equipmentId = eqData.equipmentId,
                        materialId = eqData.materialId,
                        enhancementIds = new List<string>(eqData.enhancementIds),
                        qualityTier = eqData.qualityTier,
                        customColor = new Color(eqData.customColorR, eqData.customColorG, eqData.customColorB),
                        isDirty = true
                    };

                    playerEquipment.AddToInventory(customEq);
                }
            }


            // Restore building state
            BuildingSaveManager.ApplySaveData(data.buildingData);
            Debug.Log($"Save data applied from slot {data.slotIndex}");
        }

        public SaveData[] GetAllSaveSlots()
        {
            var slots = new SaveData[maxSaveSlots];
            for (int i = 0; i < maxSaveSlots; i++)
            {
                string path = GetSavePath(i);
                if (File.Exists(path))
                {
                    string json = File.ReadAllText(path);
                    slots[i] = JsonSerializer.Deserialize<SaveData>(json);
                }
                else
                {
                    slots[i] = new SaveData { slotIndex = i, status = "Empty" };
                }
            }
            return slots;
        }

        public void DeleteSave(int slotIndex)
        {
            string path = GetSavePath(slotIndex);
            if (File.Exists(path))
            {
                File.Delete(path);
                Debug.Log($"Save slot {slotIndex} deleted");
            }
        }

        void AutoSave()
        {
            // Auto-save to slot 0
            SaveGame(0);
        }

        SaveData CollectSaveData()
        {
            var data = new SaveData();

            // Player
            var player = GameObject.FindGameObjectWithTag("Player");
            if (player != null)
            {
                data.position = new Vector3Serializable(player.transform.position);
                data.rotation = new Vector3Serializable(player.transform.eulerAngles);

                var health = player.GetComponent<Health>();
                if (health != null)
                {
                    data.health = health.currentHealth;
                    data.maxHealth = health.maxHealth;
                }

                var controller = player.GetComponent<PlayerController>();
                if (controller != null)
                {
                    data.currentAbility1Cooldown = Mathf.RoundToInt(controller.GetAbility1Cooldown());
                    data.currentAbility2Cooldown = Mathf.RoundToInt(controller.GetAbility2Cooldown());
                }
            }

            // Region
            data.region = lastRegion;

            // Playtime
            data.playtime = Time.timeSinceLevelLoad;

            // Quests
            var qm = QuestManager.Instance;
            if (qm != null)
            {
                foreach (var quest in qm.activeQuests)
                {
                    data.activeQuests.Add(new QuestSaveData
                    {
                        questId = quest.id,
                        status = (int)quest.status,
                        objectives = quest.objectives.ConvertAll(o => new ObjectiveSaveData
                        {
                            description = o.description,
                            isCompleted = o.isCompleted,
                            currentAmount = o.currentAmount
                        })
                    });
                }

                foreach (var quest in qm.completedQuests)
                {
                    data.completedQuests.Add(new QuestSaveData
                    {
                        questId = quest.id,
                        status = (int)quest.status,
                        objectives = quest.objectives.ConvertAll(o => new ObjectiveSaveData
                        {
                            description = o.description,
                            isCompleted = o.isCompleted,
                            currentAmount = o.currentAmount
                        })
                    });
                }
            }

            // Inventory
            var inv = InventoryManager.Instance;
            if (inv != null)
            {
                data.inventory = inv.GetAllItems();
                data.equippedWeaponIndex = inv.equippedWeaponIndex;
            }

            // Amendments & Guidebook
            var binder = BinderManager.Instance;
            if (binder != null)
            {
                data.collectedAmendments = binder.GetCollectedAmendments();
                data.guidebookEntries = binder.GetGuidebookEntries();
            }

            // Companions
            var companionManager = CompanionManager.Instance;
            if (companionManager != null)
            {
                data.companions = companionManager.GetCompanionSaveData();
            }

            // NPC Relationships
            data.npcRelationships = CollectNPCRelationships();

            // Equipment customization
            var playerEquipment = PlayerEquipment.Instance;
            if (playerEquipment != null)
            {
                data.equipmentData.playerEquipment = playerEquipment.GetAllEquipped()
                    .ConvertAll(eq => new CustomizedEquipmentSaveData
                    {
                        equipmentId = eq.equipmentId,
                        materialId = eq.materialId,
                        enhancementIds = new List<string>(eq.enhancementIds),
                        qualityTier = eq.qualityTier,
                        customColorR = eq.customColor.r,
                        customColorG = eq.customColor.g,
                        customColorB = eq.customColor.b
                    });
            }

            // Building state
            data.buildingData = BuildingSaveManager.CollectSaveData();

            return data;
        }

        string GetSavePath(int slotIndex)
        {
            return Path.Combine(saveDirectory, $"{SAVE_PREFIX}{slotIndex}{SAVE_EXTENSION}");
        }

        string FormatPlaytime(float seconds)
        {
            int hours = Mathf.FloorToInt(seconds / 3600f);
            int minutes = Mathf.FloorToInt((seconds % 3600f) / 60f);
            return $"{hours}h {minutes}m";
        }

        public void Reset()
        {
            // Clear save directory
            if (Directory.Exists(saveDirectory))
            {
                Directory.Delete(saveDirectory, true);
                Directory.CreateDirectory(saveDirectory);
            }
            lastRegion = "";
            autosaveTimer = 0f;
        }

        // === NPC Relationship Persistence ===

        /// <summary>
        /// Collects all NPC relationship data from the world state service.
        /// </summary>
        List<NPCRelationshipSaveData> CollectNPCRelationships()
        {
            var result = new List<NPCRelationshipSaveData>();
            var wss = WorldStateService.Instance;
            if (wss == null) return result;

            // Collect from all NPCs in the scene
            var npcs = FindObjectsOfType<NPCController>();
            foreach (var npc in npcs)
            {
                var rel = new NPCRelationshipSaveData
                {
                    npcId = npc.Data != null ? npc.Data.npcId : npc.npcId,
                    lastEmotion = wss.GetNpcEmotion(npc.Data != null ? npc.Data.npcId : npc.npcId).ToString(),
                    lastInteractionTime = Time.time
                };
                result.Add(rel);
            }
            return result;
        }

        /// <summary>
        /// Restores NPC relationship data to the world state service.
        /// </summary>
        public void ApplyNPCRelationships(List<NPCRelationshipSaveData> relationships)
        {
            if (relationships == null || relationships.Count == 0) return;

            var wss = WorldStateService.Instance;
            if (wss == null) return;

            foreach (var rel in relationships)
            {
                // Restore emotion state
                if (System.Enum.TryParse<WorldStateService.Emotion>(rel.lastEmotion, out var emotion))
                {
                    wss.SetNpcEmotion(rel.npcId, emotion);
                }
            }
        }
    }

    /// <summary>
    /// Health component for player.
    /// </summary>
    public class Health : MonoBehaviour
    {
        public float maxHealth = 100f;
        public float currentHealth = 100f;

        public void TakeDamage(float amount)
        {
            currentHealth = Mathf.Max(0, currentHealth - amount);
            if (currentHealth <= 0)
                Die();
        }

        public void Heal(float amount)
        {
            currentHealth = Mathf.Min(maxHealth, currentHealth + amount);
        }

        void Die()
        {
            // Respawn at checkpoint
            var saveManager = SaveManager.Instance;
            if (saveManager != null)
            {
                var lastSave = saveManager.LoadGame(0);
                if (lastSave != null)
                    saveManager.ApplySaveData(lastSave);
            }
        }
    }

    /// <summary>
    /// Inventory item data structure for save system and inventory management.
    /// </summary>
    [System.Serializable]
    public class InventoryItem
    {
        public string itemId;
        public int quantity;
        public bool isEquipped;
    }

    /// <summary>
    /// Inventory Manager - basic inventory with ≥5 distinct items per production package.
    /// </summary>
    public class InventoryManager : MonoBehaviour
    {
        public static InventoryManager Instance { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureExists()
        {
            if (Instance == null)
            {
                var go = new GameObject(typeof(InventoryManager).Name);
                Instance = go.AddComponent<InventoryManager>();
            }
        }

        [System.Serializable]
        public class Item
        {
            public string id;
            public string displayName;
            public int quantity;
            public bool isEquipped;
            public ItemType type;
        }

        public enum ItemType { Weapon, Armor, Consumable, Key, Quest, Misc }

        public List<Item> items = new List<Item>();
        public int equippedWeaponIndex = 0;

        public System.Action OnInventoryChanged;

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

        public void AddItem(string itemId, int quantity = 1)
        {
            var existing = items.Find(i => i.id == itemId);
            if (existing != null)
            {
                existing.quantity += quantity;
            }
            else
            {
                items.Add(new Item { id = itemId, displayName = itemId, quantity = quantity, type = ItemType.Misc });
            }
            OnInventoryChanged?.Invoke();
        }

        public void RemoveItem(string itemId, int quantity = 1)
        {
            var item = items.Find(i => i.id == itemId);
            if (item != null)
            {
                item.quantity -= quantity;
                if (item.quantity <= 0)
                    items.Remove(item);
                OnInventoryChanged?.Invoke();
            }
        }

        public bool HasItem(string itemId, int quantity = 1)
        {
            var item = items.Find(i => i.id == itemId);
            return item != null && item.quantity >= quantity;
        }

        public void EquipItem(string itemId)
        {
            var item = items.Find(i => i.id == itemId && i.type == ItemType.Weapon);
            if (item != null)
            {
                foreach (var i in items)
                    i.isEquipped = false;
                item.isEquipped = true;
                equippedWeaponIndex = items.IndexOf(item);
                OnInventoryChanged?.Invoke();
            }
        }

        public void Clear()
        {
            items.Clear();
            OnInventoryChanged?.Invoke();
        }

        public List<InventoryItem> GetAllItems()
        {
            return items.ConvertAll(i => new InventoryItem
            {
                itemId = i.id,
                quantity = i.quantity,
                isEquipped = i.isEquipped
            });
        }

        public void Reset()
        {
            items.Clear();
            OnInventoryChanged?.Invoke();
        }
    }

    /// <summary>
    /// Binder Manager - Prophecy Binder UI with amendments.
    /// </summary>
    public class BinderManager : MonoBehaviour
    {
        public static BinderManager Instance { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureExists()
        {
            if (Instance == null)
            {
                var go = new GameObject(typeof(BinderManager).Name);
                Instance = go.AddComponent<BinderManager>();
            }
        }

        public List<string> collectedAmendments = new List<string>();
        public List<string> guidebookEntries = new List<string>();

        public System.Action OnBinderUpdated;

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

        public void AddAmendment(string amendmentId)
        {
            if (!collectedAmendments.Contains(amendmentId))
            {
                collectedAmendments.Add(amendmentId);
                OnBinderUpdated?.Invoke();
            }
        }

        public void AddGuidebookEntry(string entryId)
        {
            if (!guidebookEntries.Contains(entryId))
            {
                guidebookEntries.Add(entryId);
                OnBinderUpdated?.Invoke();
            }
        }

        public void LoadAmendments(List<string> amendments)
        {
            collectedAmendments = new List<string>(amendments);
            OnBinderUpdated?.Invoke();
        }

        public void LoadGuidebookEntries(List<string> entries)
        {
            guidebookEntries = new List<string>(entries);
            OnBinderUpdated?.Invoke();
        }

        public List<string> GetCollectedAmendments() => new List<string>(collectedAmendments);
        public List<string> GetGuidebookEntries() => new List<string>(guidebookEntries);

        public void Reset()
        {
            collectedAmendments.Clear();
            guidebookEntries.Clear();
            OnBinderUpdated?.Invoke();
        }
    }

    /// <summary>
    /// Companion Manager - follows, banter system.
    /// </summary>
    public class CompanionManager : MonoBehaviour
    {
        public static CompanionManager Instance { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureExists()
        {
            if (Instance == null)
            {
                var go = new GameObject(typeof(CompanionManager).Name);
                Instance = go.AddComponent<CompanionManager>();
            }
        }

        [System.Serializable]
        public class Companion
        {
            public string id;
            public string displayName;
            public GameObject prefab;
            public Transform followTarget;
            public float followDistance = 2f;
            public List<string> banterLines = new List<string>();
            public float banterCooldown = 90f;
            public float banterTimer = 0f;
            public bool isActive = false;
            public int banterLinesPlayed = 0;
        }

        public List<Companion> allCompanions = new List<Companion>();
        public List<Companion> activeCompanions = new List<Companion>();

        public System.Action OnCompanionsChanged;

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            // Initialize from production package
            InitializeCompanions();
        }

        void InitializeCompanions()
        {
            allCompanions.Add(new Companion
            {
                id = "CH_Wizard",
                displayName = "Old Wizard",
                banterLines = new List<string>
                {
                    "Another prophecy. Joy.",
                    "I've seen twelve Chosen Ones. You're... adequate.",
                    "The paperwork never ends. Neither do I, unfortunately.",
                    "Try not to die. The forms for a replacement are tedious."
                },
                banterCooldown = 120f
            });

            allCompanions.Add(new Companion
            {
                id = "CH_Companion2",
                displayName = "Organized Sorceress",
                banterLines = new List<string>
                {
                    "Filing system's corrupt. Standard procedure.",
                    "Efficiency rating: minimal. Improvement required.",
                    "I'll handle the paperwork. You handle the dying."
                },
                banterCooldown = 90f
            });
        }

        void Update()
        {
            // Banter timer
            foreach (var comp in activeCompanions)
            {
                comp.banterTimer -= Time.deltaTime;
                if (comp.banterTimer <= 0 && comp.banterLinesPlayed < comp.banterLines.Count)
                {
                    PlayBanter(comp);
                    comp.banterTimer = comp.banterCooldown;
                }
            }
        }

        void PlayBanter(Companion comp)
        {
            if (comp.banterLinesPlayed < comp.banterLines.Count)
            {
                string line = comp.banterLines[comp.banterLinesPlayed];
                Debug.Log($"[{comp.displayName}]: {line}");
                comp.banterLinesPlayed++;
                // TODO: Trigger VO/TTS via Kokoro
            }
        }

        public void ActivateCompanion(string companionId)
        {
            var comp = allCompanions.Find(c => c.id == companionId);
            if (comp != null && !comp.isActive)
            {
                comp.isActive = true;
                activeCompanions.Add(comp);
                OnCompanionsChanged?.Invoke();
            }
        }

        public void DeactivateCompanion(string companionId)
        {
            var comp = allCompanions.Find(c => c.id == companionId);
            if (comp != null && comp.isActive)
            {
                comp.isActive = false;
                activeCompanions.Remove(comp);
                OnCompanionsChanged?.Invoke();
            }
        }

        public List<CompanionSaveData> GetCompanionSaveData()
        {
            return activeCompanions.ConvertAll(c => new CompanionSaveData
            {
                companionId = c.id,
                banterLinesPlayed = c.banterLinesPlayed,
                isActive = c.isActive
            });
        }

        public void RestoreCompanion(CompanionSaveData data)
        {
            var comp = allCompanions.Find(c => c.id == data.companionId);
            if (comp != null)
            {
                comp.banterLinesPlayed = data.banterLinesPlayed;
                if (data.isActive)
                    ActivateCompanion(data.companionId);
            }
        }

        public void Reset()
        {
            allCompanions.Clear();
            activeCompanions.Clear();
            InitializeCompanions();
        }
    }
}