using UnityEngine;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Resolves effective stats for equipment, accounting for quality tier, materials, and enhancements.
    /// </summary>
    public class ItemStatResolver : MonoBehaviour
    {
        public static ItemStatResolver Instance { get; private set; }

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
        /// Get effective stats for a crafted item, accounting for quality tier.
        /// </summary>
        public static EquipmentStats GetEffectiveStats(string itemId, int qualityTier)
        {
            var baseStats = GetBaseStats(itemId);
            var multiplier = 1.0f + (qualityTier * 0.2f);

            return new EquipmentStats
            {
                damage = Mathf.RoundToInt(baseStats.damage * multiplier),
                defense = Mathf.RoundToInt(baseStats.defense * multiplier),
                durability = Mathf.RoundToInt(baseStats.durability * multiplier),
                weight = Mathf.RoundToInt(baseStats.weight * multiplier),
                speed = Mathf.RoundToInt(baseStats.speed * multiplier),
                accuracy = Mathf.RoundToInt(baseStats.accuracy * multiplier),
                critChance = Mathf.RoundToInt(baseStats.critChance * multiplier),
                critDamage = Mathf.RoundToInt(baseStats.critDamage * multiplier),
                range = Mathf.RoundToInt(baseStats.range * multiplier),
                handling = Mathf.RoundToInt(baseStats.handling * multiplier)
            };
        }

        /// <summary>
        /// Get base stats for an item from the equipment database.
        /// </summary>
        public static EquipmentStats GetBaseStats(string itemId)
        {
            var db = EquipmentDatabase.Instance;
            if (db == null) return new EquipmentStats();

            var equipment = db.GetEquipment(itemId);
            if (equipment != null)
            {
                return equipment.baseStats;
            }

            var petEquipment = db.GetPetEquipment(itemId);
            if (petEquipment != null)
            {
                return petEquipment.baseStats;
            }

            return new EquipmentStats();
        }

        /// <summary>
        /// Calculate effective stats for customized equipment.
        /// </summary>
        public static EquipmentStats GetCustomizedStats(
            string itemId,
            int qualityTier,
            string materialId,
            List<string> enhancementIds)
        {
            var baseStats = GetBaseStats(itemId);
            var qualityMultiplier = 1.0f + (qualityTier * 0.2f);
            var result = baseStats * qualityMultiplier;

            // Apply material modifiers
            if (!string.IsNullOrEmpty(materialId) && EquipmentDatabase.Instance != null)
            {
                var material = EquipmentDatabase.Instance.GetMaterial(materialId);
                if (material != null)
                {
                    result = result + material.statModifiers;
                    result.durability = Mathf.RoundToInt(result.durability * material.durabilityMultiplier);
                    result.weight = Mathf.RoundToInt(result.weight * material.weightMultiplier);
                }
            }

            // Apply enhancement modifiers
            if (enhancementIds != null && EquipmentDatabase.Instance != null)
            {
                foreach (var enhId in enhancementIds)
                {
                    var enhancement = EquipmentDatabase.Instance.GetEnhancement(enhId);
                    if (enhancement != null)
                    {
                        result = result + enhancement.statModifiers;
                    }
                }
            }

            return result;
        }

        /// <summary>
        /// Calculate effective stats for pet equipment.
        /// </summary>
        public static EquipmentStats GetPetEquipmentStats(
            string equipmentId,
            List<string> enhancementIds)
        {
            var baseStats = GetBaseStats(equipmentId);
            var result = baseStats;

            if (enhancementIds != null && EquipmentDatabase.Instance != null)
            {
                foreach (var enhId in enhancementIds)
                {
                    var enhancement = EquipmentDatabase.Instance.GetEnhancement(enhId);
                    if (enhancement != null)
                    {
                        result = result + enhancement.statModifiers;
                    }
                }
            }

            return result;
        }
    }
}
