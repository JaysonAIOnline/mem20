using UnityEngine;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Preview system for equipment customization.
    /// Shows stat changes and visual changes before confirming.
    /// </summary>
    public class EquipmentPreviewSystem : MonoBehaviour
    {
        public static EquipmentPreviewSystem Instance { get; private set; }

        [Header("Preview Settings")]
        public float previewRotationSpeed = 30f;
        public float previewZoomSpeed = 2f;
        public float previewMinDistance = 1f;
        public float previewMaxDistance = 5f;

        // Current preview state
        private CustomizedEquipment currentPreview;
        private CustomizedPetEquipment currentPetPreview;
        private GameObject previewModel;
        private float previewRotation;
        private float previewDistance = 3f;
        private bool isPreviewing;

        // Events
        public event System.Action<CustomizedEquipment> OnPreviewUpdated;
        public event System.Action<EquipmentStats, EquipmentStats> OnStatsCompared;

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
        /// Start previewing equipment customization.
        /// </summary>
        public void StartPreview(CustomizedEquipment equipment)
        {
            currentPreview = equipment;
            currentPetPreview = null;
            isPreviewing = true;
            previewRotation = 0f;
            OnPreviewUpdated?.Invoke(equipment);
        }

        /// <summary>
        /// Start previewing pet equipment customization.
        /// </summary>
        public void StartPetPreview(CustomizedPetEquipment equipment)
        {
            currentPetPreview = equipment;
            currentPreview = null;
            isPreviewing = true;
            previewRotation = 0f;
        }

        /// <summary>
        /// End the current preview.
        /// </summary>
        public void EndPreview()
        {
            currentPreview = null;
            currentPetPreview = null;
            isPreviewing = false;

            if (previewModel != null)
            {
                Destroy(previewModel);
                previewModel = null;
            }
        }

        /// <summary>
        /// Get the current preview equipment.
        /// </summary>
        public CustomizedEquipment GetCurrentPreview()
        {
            return currentPreview;
        }

        /// <summary>
        /// Get the current pet preview equipment.
        /// </summary>
        public CustomizedPetEquipment GetCurrentPetPreview()
        {
            return currentPetPreview;
        }

        /// <summary>
        /// Compare stats between base and customized equipment.
        /// </summary>
        public EquipmentStats CompareStats(CustomizedEquipment equipment)
        {
            var baseStats = ItemStatResolver.GetBaseStats(equipment.equipmentId);
            var customizedStats = ItemStatResolver.GetCustomizedStats(
                equipment.equipmentId,
                equipment.qualityTier,
                equipment.materialId,
                equipment.enhancementIds
            );

            OnStatsCompared?.Invoke(baseStats, customizedStats);
            return customizedStats;
        }

        /// <summary>
        /// Get stat differences between base and customized.
        /// </summary>
        public EquipmentStats GetStatDifferences(CustomizedEquipment equipment)
        {
            var baseStats = ItemStatResolver.GetBaseStats(equipment.equipmentId);
            var customizedStats = ItemStatResolver.GetCustomizedStats(
                equipment.equipmentId,
                equipment.qualityTier,
                equipment.materialId,
                equipment.enhancementIds
            );

            return new EquipmentStats
            {
                damage = customizedStats.damage - baseStats.damage,
                defense = customizedStats.defense - baseStats.defense,
                durability = customizedStats.durability - baseStats.durability,
                weight = customizedStats.weight - baseStats.weight,
                speed = customizedStats.speed - baseStats.speed,
                accuracy = customizedStats.accuracy - baseStats.accuracy,
                critChance = customizedStats.critChance - baseStats.critChance,
                critDamage = customizedStats.critDamage - baseStats.critDamage,
                range = customizedStats.range - baseStats.range,
                handling = customizedStats.handling - baseStats.handling
            };
        }

        /// <summary>
        /// Get stat differences for pet equipment.
        /// </summary>
        public EquipmentStats GetPetStatDifferences(CustomizedPetEquipment equipment)
        {
            var baseStats = ItemStatResolver.GetBaseStats(equipment.equipmentId);
            var customizedStats = ItemStatResolver.GetPetEquipmentStats(
                equipment.equipmentId,
                equipment.enhancementIds
            );

            return new EquipmentStats
            {
                damage = customizedStats.damage - baseStats.damage,
                defense = customizedStats.defense - baseStats.defense,
                durability = customizedStats.durability - baseStats.durability,
                weight = customizedStats.weight - baseStats.weight,
                speed = customizedStats.speed - baseStats.speed,
                accuracy = customizedStats.accuracy - baseStats.accuracy,
                critChance = customizedStats.critChance - baseStats.critChance,
                critDamage = customizedStats.critDamage - baseStats.critDamage,
                range = customizedStats.range - baseStats.range,
                handling = customizedStats.handling - baseStats.handling
            };
        }

        /// <summary>
        /// Update preview rotation.
        /// </summary>
        public void UpdatePreviewRotation(float delta)
        {
            previewRotation += delta * previewRotationSpeed;
        }

        /// <summary>
        /// Update preview zoom.
        /// </summary>
        public void UpdatePreviewZoom(float delta)
        {
            previewDistance = Mathf.Clamp(previewDistance - delta * previewZoomSpeed, previewMinDistance, previewMaxDistance);
        }

        /// <summary>
        /// Check if currently previewing.
        /// </summary>
        public bool IsPreviewing()
        {
            return isPreviewing;
        }

        /// <summary>
        /// Get preview model rotation.
        /// </summary>
        public float GetPreviewRotation()
        {
            return previewRotation;
        }

        /// <summary>
        /// Get preview distance.
        /// </summary>
        public float GetPreviewDistance()
        {
            return previewDistance;
        }
    }
}
