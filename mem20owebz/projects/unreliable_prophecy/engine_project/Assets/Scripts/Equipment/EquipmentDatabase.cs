using UnityEngine;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Runtime database for all equipment, materials, enhancements, and pet equipment.
    /// </summary>
    public class EquipmentDatabase : MonoBehaviour
    {
        public static EquipmentDatabase Instance { get; private set; }

        [Header("Equipment")]
        [SerializeField] private List<EquipmentData> allEquipment = new List<EquipmentData>();

        [Header("Materials")]
        [SerializeField] private List<MaterialData> allMaterials = new List<MaterialData>();

        [Header("Enhancements")]
        [SerializeField] private List<EnhancementData> allEnhancements = new List<EnhancementData>();

        [Header("Pet Equipment")]
        [SerializeField] private List<PetEquipmentData> allPetEquipment = new List<PetEquipmentData>();

        private Dictionary<string, EquipmentData> equipmentLookup;
        private Dictionary<string, MaterialData> materialLookup;
        private Dictionary<string, EnhancementData> enhancementLookup;
        private Dictionary<string, PetEquipmentData> petEquipmentLookup;

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            BuildLookups();
        }

        private void BuildLookups()
        {
            equipmentLookup = new Dictionary<string, EquipmentData>();
            foreach (var eq in allEquipment)
            {
                if (!string.IsNullOrEmpty(eq.equipmentId))
                    equipmentLookup[eq.equipmentId] = eq;
            }

            materialLookup = new Dictionary<string, MaterialData>();
            foreach (var mat in allMaterials)
            {
                if (!string.IsNullOrEmpty(mat.materialId))
                    materialLookup[mat.materialId] = mat;
            }

            enhancementLookup = new Dictionary<string, EnhancementData>();
            foreach (var enh in allEnhancements)
            {
                if (!string.IsNullOrEmpty(enh.enhancementId))
                    enhancementLookup[enh.enhancementId] = enh;
            }

            petEquipmentLookup = new Dictionary<string, PetEquipmentData>();
            foreach (var peq in allPetEquipment)
            {
                if (!string.IsNullOrEmpty(peq.equipmentId))
                    petEquipmentLookup[peq.equipmentId] = peq;
            }
        }

        #region Equipment Lookups

        public EquipmentData GetEquipment(string equipmentId)
        {
            equipmentLookup.TryGetValue(equipmentId, out var data);
            return data;
        }

        public List<EquipmentData> GetEquipmentBySlot(EquipmentSlot slot)
        {
            return allEquipment.FindAll(e => e.slot == slot);
        }

        public List<EquipmentData> GetEquipmentByType(EquipmentType type)
        {
            return allEquipment.FindAll(e => e.type == type);
        }

        public List<EquipmentData> GetAllEquipment()
        {
            return new List<EquipmentData>(allEquipment);
        }

        #endregion

        #region Material Lookups

        public MaterialData GetMaterial(string materialId)
        {
            materialLookup.TryGetValue(materialId, out var data);
            return data;
        }

        public List<MaterialData> GetMaterialsByType(MaterialType type)
        {
            return allMaterials.FindAll(m => m.type == type);
        }

        public List<MaterialData> GetMaterialsByTier(int tier)
        {
            return allMaterials.FindAll(m => m.tier == tier);
        }

        public List<MaterialData> GetCompatibleMaterials(EquipmentData equipment)
        {
            return allMaterials.FindAll(m =>
                m.compatibleEquipmentTypes.Contains(equipment.type.ToString()) &&
                equipment.compatibleMaterials.Contains(m.materialId));
        }

        public List<MaterialData> GetAllMaterials()
        {
            return new List<MaterialData>(allMaterials);
        }

        #endregion

        #region Enhancement Lookups

        public EnhancementData GetEnhancement(string enhancementId)
        {
            enhancementLookup.TryGetValue(enhancementId, out var data);
            return data;
        }

        public List<EnhancementData> GetEnhancementsByType(EnhancementType type)
        {
            return allEnhancements.FindAll(e => e.type == type);
        }

        public List<EnhancementData> GetCompatibleEnhancements(EquipmentData equipment)
        {
            return allEnhancements.FindAll(e =>
                equipment.compatibleEnhancements.Contains(e.enhancementId));
        }

        public List<EnhancementData> GetCompatiblePetEnhancements(PetEquipmentData petEquipment)
        {
            return allEnhancements.FindAll(e =>
                petEquipment.compatibleEnhancements.Contains(e.enhancementId));
        }

        public List<EnhancementData> GetAllEnhancements()
        {
            return new List<EnhancementData>(allEnhancements);
        }

        #endregion

        #region Pet Equipment Lookups

        public PetEquipmentData GetPetEquipment(string equipmentId)
        {
            petEquipmentLookup.TryGetValue(equipmentId, out var data);
            return data;
        }

        public List<PetEquipmentData> GetPetEquipmentBySlot(PetEquipmentSlot slot)
        {
            return allPetEquipment.FindAll(e => e.slot == slot);
        }

        public List<PetEquipmentData> GetPetEquipmentBySpecies(string speciesId)
        {
            return allPetEquipment.FindAll(e => e.compatibleSpecies.Contains(speciesId));
        }

        public List<PetEquipmentData> GetAllPetEquipment()
        {
            return new List<PetEquipmentData>(allPetEquipment);
        }

        #endregion
    }
}
