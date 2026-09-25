using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Save/load DTOs for equipment customization state.
    /// </summary>
    [System.Serializable]
    public class EquipmentSaveData
    {
        public List<CustomizedEquipmentSaveData> playerEquipment = new List<CustomizedEquipmentSaveData>();
        public List<CustomizedPetEquipmentSaveData> petEquipment = new List<CustomizedPetEquipmentSaveData>();
        public List<string> unlockedMaterials = new List<string>();
        public List<string> unlockedEnhancements = new List<string>();
    }

    [System.Serializable]
    public class CustomizedEquipmentSaveData
    {
        public string equipmentId;
        public string materialId;
        public List<string> enhancementIds = new List<string>();
        public int qualityTier;
        public float customColorR = 1f;
        public float customColorG = 1f;
        public float customColorB = 1f;
    }

    [System.Serializable]
    public class CustomizedPetEquipmentSaveData
    {
        public string equipmentId;
        public List<string> enhancementIds = new List<string>();
        public float customColorR = 1f;
        public float customColorG = 1f;
        public float customColorB = 1f;
    }

    [System.Serializable]
    public class PlayerEquipmentSaveData
    {
        public string equippedPrimaryWeapon;
        public string equippedSecondaryWeapon;
        public string equippedArmor;
        public string equippedAccessory1;
        public string equippedAccessory2;
        public List<string> inventoryEquipment = new List<string>();
    }
}
