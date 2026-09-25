using UnityEngine;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Represents a customized piece of equipment with material and enhancement data.
    /// </summary>
    [System.Serializable]
    public class CustomizedEquipment
    {
        public string equipmentId;
        public string materialId;
        public List<string> enhancementIds = new List<string>();
        public int qualityTier;
        public Color customColor = Color.white;
        public EquipmentStats cachedStats;
        public bool isDirty = true;

        public void InvalidateCache()
        {
            isDirty = true;
        }
    }

    /// <summary>
    /// Represents a customized pet piece with enhancement data.
    /// </summary>
    [System.Serializable]
    public class CustomizedPetEquipment
    {
        public string equipmentId;
        public List<string> enhancementIds = new List<string>();
        public Color customColor = Color.white;
        public EquipmentStats cachedStats;
        public bool isDirty = true;

        public void InvalidateCache()
        {
            isDirty = true;
        }
    }

    /// <summary>
    /// Core logic for applying materials and enhancements to equipment.
    /// </summary>
    public class EquipmentCustomizer : MonoBehaviour
    {
        public static EquipmentCustomizer Instance { get; private set; }

        // Event fired when equipment is customized
        public event System.Action<CustomizedEquipment> OnEquipmentCustomized;
        public event System.Action<string> OnEquipmentMaterialChanged;
        public event System.Action<string, string> OnEnhancementApplied;
        public event System.Action<string, string> OnEnhancementRemoved;

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

        #region Player Equipment

        /// <summary>
        /// Create a new customized equipment instance.
        /// </summary>
        public CustomizedEquipment CreateCustomizedEquipment(string equipmentId)
        {
            return new CustomizedEquipment
            {
                equipmentId = equipmentId,
                materialId = null,
                enhancementIds = new List<string>(),
                qualityTier = 0,
                customColor = Color.white,
                isDirty = true
            };
        }

        /// <summary>
        /// Apply a material to customized equipment.
        /// </summary>
        public bool ApplyMaterial(CustomizedEquipment equipment, string materialId)
        {
            if (equipment == null) return false;

            var db = EquipmentDatabase.Instance;
            if (db == null) return false;

            var material = db.GetMaterial(materialId);
            if (material == null) return false;

            var equipmentData = db.GetEquipment(equipment.equipmentId);
            if (equipmentData == null) return false;

            // Check compatibility
            if (!equipmentData.compatibleMaterials.Contains(materialId))
            {
                Debug.LogWarning($"Material {materialId} is not compatible with {equipment.equipmentId}");
                return false;
            }

            equipment.materialId = materialId;
            equipment.InvalidateCache();
            OnEquipmentMaterialChanged?.Invoke(equipment.equipmentId);
            OnEquipmentCustomized?.Invoke(equipment);

            Debug.Log($"Applied material {materialId} to {equipment.equipmentId}");
            return true;
        }

        /// <summary>
        /// Remove material from customized equipment.
        /// </summary>
        public bool RemoveMaterial(CustomizedEquipment equipment)
        {
            if (equipment == null) return false;

            equipment.materialId = null;
            equipment.InvalidateCache();
            OnEquipmentMaterialChanged?.Invoke(equipment.equipmentId);
            OnEquipmentCustomized?.Invoke(equipment);
            return true;
        }

        /// <summary>
        /// Apply an enhancement to customized equipment.
        /// </summary>
        public bool ApplyEnhancement(CustomizedEquipment equipment, string enhancementId)
        {
            if (equipment == null) return false;

            var db = EquipmentDatabase.Instance;
            if (db == null) return false;

            var enhancement = db.GetEnhancement(enhancementId);
            if (enhancement == null) return false;

            var equipmentData = db.GetEquipment(equipment.equipmentId);
            if (equipmentData == null) return false;

            // Check compatibility
            if (!equipmentData.compatibleEnhancements.Contains(enhancementId))
            {
                Debug.LogWarning($"Enhancement {enhancementId} is not compatible with {equipment.equipmentId}");
                return false;
            }

            // Check slot count
            if (equipment.enhancementIds.Count >= equipmentData.enhancementSlots)
            {
                Debug.LogWarning($"No empty enhancement slots on {equipment.equipmentId}");
                return false;
            }

            // Check exclusivity
            foreach (var existingId in equipment.enhancementIds)
            {
                var existing = db.GetEnhancement(existingId);
                if (existing != null && existing.exclusiveWith.Contains(enhancementId))
                {
                    Debug.LogWarning($"Enhancement {enhancementId} is exclusive with {existingId}");
                    return false;
                }
            }

            // Check for duplicates
            if (equipment.enhancementIds.Contains(enhancementId))
            {
                Debug.LogWarning($"Enhancement {enhancementId} already applied to {equipment.equipmentId}");
                return false;
            }

            equipment.enhancementIds.Add(enhancementId);
            equipment.InvalidateCache();
            OnEnhancementApplied?.Invoke(equipment.equipmentId, enhancementId);
            OnEquipmentCustomized?.Invoke(equipment);

            Debug.Log($"Applied enhancement {enhancementId} to {equipment.equipmentId}");
            return true;
        }

        /// <summary>
        /// Remove an enhancement from customized equipment.
        /// </summary>
        public bool RemoveEnhancement(CustomizedEquipment equipment, string enhancementId)
        {
            if (equipment == null) return false;

            bool removed = equipment.enhancementIds.Remove(enhancementId);
            if (removed)
            {
                equipment.InvalidateCache();
                OnEnhancementRemoved?.Invoke(equipment.equipmentId, enhancementId);
                OnEquipmentCustomized?.Invoke(equipment);
            }

            return removed;
        }

        /// <summary>
        /// Recalculate cached stats for equipment.
        /// </summary>
        public void RecalculateStats(CustomizedEquipment equipment)
        {
            if (equipment == null || !equipment.isDirty) return;

            equipment.cachedStats = ItemStatResolver.GetCustomizedStats(
                equipment.equipmentId,
                equipment.qualityTier,
                equipment.materialId,
                equipment.enhancementIds
            );
            equipment.isDirty = false;
        }

        #endregion

        #region Pet Equipment

        /// <summary>
        /// Create a new customized pet equipment instance.
        /// </summary>
        public CustomizedPetEquipment CreateCustomizedPetEquipment(string equipmentId)
        {
            return new CustomizedPetEquipment
            {
                equipmentId = equipmentId,
                enhancementIds = new List<string>(),
                customColor = Color.white,
                isDirty = true
            };
        }

        /// <summary>
        /// Apply an enhancement to customized pet equipment.
        /// </summary>
        public bool ApplyPetEnhancement(CustomizedPetEquipment equipment, string enhancementId)
        {
            if (equipment == null) return false;

            var db = EquipmentDatabase.Instance;
            if (db == null) return false;

            var enhancement = db.GetEnhancement(enhancementId);
            if (enhancement == null) return false;

            var equipmentData = db.GetPetEquipment(equipment.equipmentId);
            if (equipmentData == null) return false;

            // Check compatibility
            if (!equipmentData.compatibleEnhancements.Contains(enhancementId))
            {
                Debug.LogWarning($"Enhancement {enhancementId} is not compatible with pet equipment {equipment.equipmentId}");
                return false;
            }

            // Check slot count
            if (equipment.enhancementIds.Count >= equipmentData.enhancementSlots)
            {
                Debug.LogWarning($"No empty enhancement slots on pet equipment {equipment.equipmentId}");
                return false;
            }

            // Check exclusivity
            foreach (var existingId in equipment.enhancementIds)
            {
                var existing = db.GetEnhancement(existingId);
                if (existing != null && existing.exclusiveWith.Contains(enhancementId))
                {
                    Debug.LogWarning($"Enhancement {enhancementId} is exclusive with {existingId}");
                    return false;
                }
            }

            equipment.enhancementIds.Add(enhancementId);
            equipment.InvalidateCache();
            Debug.Log($"Applied enhancement {enhancementId} to pet equipment {equipment.equipmentId}");
            return true;
        }

        /// <summary>
        /// Remove an enhancement from pet equipment.
        /// </summary>
        public bool RemovePetEnhancement(CustomizedPetEquipment equipment, string enhancementId)
        {
            if (equipment == null) return false;

            return equipment.enhancementIds.Remove(enhancementId);
        }

        /// <summary>
        /// Recalculate cached stats for pet equipment.
        /// </summary>
        public void RecalculatePetStats(CustomizedPetEquipment equipment)
        {
            if (equipment == null || !equipment.isDirty) return;

            equipment.cachedStats = ItemStatResolver.GetPetEquipmentStats(
                equipment.equipmentId,
                equipment.enhancementIds
            );
            equipment.isDirty = false;
        }

        #endregion
    }
}
