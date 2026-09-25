using UnityEngine;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Equipment slot types for player and pet.
    /// </summary>
    public enum EquipmentSlot
    {
        PrimaryWeapon,
        SecondaryWeapon,
        Armor,
        Accessory1,
        Accessory2
    }

    public enum PetEquipmentSlot
    {
        Collar,
        Saddle,
        Trinket1,
        Trinket2
    }

    /// <summary>
    /// Equipment types for categorization.
    /// </summary>
    public enum EquipmentType
    {
        OneHanded,
        TwoHanded,
        Shield,
        LightArmor,
        MediumArmor,
        HeavyArmor,
        Accessory,
        PetCollar,
        PetSaddle,
        PetTrinket
    }

    /// <summary>
    /// Base stats that equipment can modify.
    /// </summary>
    [System.Serializable]
    public class EquipmentStats
    {
        public int damage;
        public int defense;
        public int durability;
        public int weight;
        public int speed;
        public int accuracy;
        public int critChance;
        public int critDamage;
        public int range;
        public int handling;

        public static EquipmentStats operator *(EquipmentStats a, float multiplier)
        {
            return new EquipmentStats
            {
                damage = Mathf.RoundToInt(a.damage * multiplier),
                defense = Mathf.RoundToInt(a.defense * multiplier),
                durability = Mathf.RoundToInt(a.durability * multiplier),
                weight = Mathf.RoundToInt(a.weight * multiplier),
                speed = Mathf.RoundToInt(a.speed * multiplier),
                accuracy = Mathf.RoundToInt(a.accuracy * multiplier),
                critChance = Mathf.RoundToInt(a.critChance * multiplier),
                critDamage = Mathf.RoundToInt(a.critDamage * multiplier),
                range = Mathf.RoundToInt(a.range * multiplier),
                handling = Mathf.RoundToInt(a.handling * multiplier)
            };
        }

        public static EquipmentStats operator +(EquipmentStats a, EquipmentStats b)
        {
            return new EquipmentStats
            {
                damage = a.damage + b.damage,
                defense = a.defense + b.defense,
                durability = a.durability + b.durability,
                weight = a.weight + b.weight,
                speed = a.speed + b.speed,
                accuracy = a.accuracy + b.accuracy,
                critChance = a.critChance + b.critChance,
                critDamage = a.critDamage + b.critDamage,
                range = a.range + b.range,
                handling = a.handling + b.handling
            };
        }
    }

    /// <summary>
    /// ScriptableObject for base equipment definitions.
    /// </summary>
    [CreateAssetMenu(fileName = "NewEquipment", menuName = "UnreliableProphecy/Equipment/EquipmentData")]
    public class EquipmentData : ScriptableObject
    {
        public string equipmentId;
        public string displayName;
        public string description;
        public Sprite icon;
        public EquipmentSlot slot;
        public EquipmentType type;
        public List<string> compatibleMaterials;
        public List<string> compatibleEnhancements;
        public int enhancementSlots = 1;
        public EquipmentStats baseStats;
        public Color defaultColor = Color.white;
        public Mesh equipmentMesh;
        public Material equipmentMaterial;
    }

    /// <summary>
    /// Material types for customization.
    /// </summary>
    public enum MaterialType
    {
        Metal,
        Leather,
        Cloth,
        Wood,
        Crystal,
        Gem,
        Elemental,
        Composite
    }

    /// <summary>
    /// ScriptableObject for crafting materials.
    /// </summary>
    [CreateAssetMenu(fileName = "NewMaterial", menuName = "UnreliableProphecy/Equipment/Material")]
    public class MaterialData : ScriptableObject
    {
        public string materialId;
        public string displayName;
        public string description;
        public Sprite icon;
        public MaterialType type;
        public EquipmentStats statModifiers;
        public Color tintColor = Color.white;
        public float durabilityMultiplier = 1.0f;
        public float weightMultiplier = 1.0f;
        public float craftingSpeedMultiplier = 1.0f;
        public List<string> compatibleEquipmentTypes;
        public int tier;
    }

    /// <summary>
    /// Enhancement types for equipment modifications.
    /// </summary>
    public enum EnhancementType
    {
        Gem,
        Rune,
        Enchantment,
        Sharpening,
        Reinforcement,
        Engraving
    }

    /// <summary>
    /// ScriptableObject for equipment enhancements.
    /// </summary>
    [CreateAssetMenu(fileName = "NewEnhancement", menuName = "UnreliableProphecy/Equipment/Enhancement")]
    public class EnhancementData : ScriptableObject
    {
        public string enhancementId;
        public string displayName;
        public string description;
        public Sprite icon;
        public EnhancementType type;
        public EquipmentStats statModifiers;
        public Color glowColor = Color.white;
        public List<string> exclusiveWith;
        public int tier;
        public float duration; // 0 = permanent
    }

    /// <summary>
    /// ScriptableObject for pet-specific equipment definitions.
    /// </summary>
    [CreateAssetMenu(fileName = "NewPetEquipment", menuName = "UnreliableProphecy/Equipment/PetEquipment")]
    public class PetEquipmentData : ScriptableObject
    {
        public string equipmentId;
        public string displayName;
        public string description;
        public Sprite icon;
        public PetEquipmentSlot slot;
        public EquipmentType type;
        public List<string> compatibleSpecies;
        public EquipmentStats baseStats;
        public int enhancementSlots = 1;
        public List<string> compatibleEnhancements;
        public Color defaultColor = Color.white;
    }
}
