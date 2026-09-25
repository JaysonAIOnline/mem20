using UnityEngine;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Customization station where players can modify their equipment with materials and enhancements.
    /// Extends the crafting station framework for equipment customization.
    /// </summary>
    public class CustomizationStation : WorldInteractable
    {
        [Header("Customization Station")]
        public GameObject customizationUIPrefab;
        public MaterialType[] allowedMaterialTypes;
        public EnhancementType[] allowedEnhancementTypes;
        public int maxEnhancementsPerItem = 3;
        public float customizationFee = 0f;

        private GameObject customizationUIInstance;

        public override void Interact(PlayerController player)
        {
            OpenCustomizationUI(player);
        }

        public override string GetInteractionText() => "Customize Equipment";

        void OpenCustomizationUI(PlayerController player)
        {
            if (customizationUIInstance == null)
            {
                customizationUIInstance = Instantiate(customizationUIPrefab);
                var ui = customizationUIInstance.GetComponent<EquipmentCustomizationUI>();
                if (ui != null && PlayerEquipment.Instance != null && PlayerEquipment.Instance.primaryWeapon != null)
                {
                    ui.Open(PlayerEquipment.Instance.primaryWeapon);
                }
            }
            else
            {
                customizationUIInstance.SetActive(true);
            }
        }

        /// <summary>
        /// Check if a material type is allowed at this station.
        /// </summary>
        public bool IsMaterialTypeAllowed(MaterialType type)
        {
            return System.Array.Exists(allowedMaterialTypes, t => t == type);
        }

        /// <summary>
        /// Check if an enhancement type is allowed at this station.
        /// </summary>
        public bool IsEnhancementTypeAllowed(EnhancementType type)
        {
            return System.Array.Exists(allowedEnhancementTypes, t => t == type);
        }
    }

    /// <summary>
    /// Customization recipe that produces customized equipment.
    /// </summary>
    [System.Serializable]
    public class CustomizationRecipe
    {
        public string recipeId;
        public string displayName;
        public string description;
        public string baseEquipmentId;
        public List<string> requiredMaterials;
        public List<string> requiredEnhancements;
        public int craftingTime;
        public int stationTier;
    }

    /// <summary>
    /// Manager for customization recipes.
    /// </summary>
    public class CustomizationRecipeManager : MonoBehaviour
    {
        public static CustomizationRecipeManager Instance { get; private set; }

        [SerializeField] private List<CustomizationRecipe> recipes = new List<CustomizationRecipe>();
        private Dictionary<string, CustomizationRecipe> recipeLookup = new Dictionary<string, CustomizationRecipe>();

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            foreach (var recipe in recipes)
            {
                if (!string.IsNullOrEmpty(recipe.recipeId))
                    recipeLookup[recipe.recipeId] = recipe;
            }
        }

        public CustomizationRecipe GetRecipe(string recipeId)
        {
            recipeLookup.TryGetValue(recipeId, out var recipe);
            return recipe;
        }

        public List<CustomizationRecipe> GetAllRecipes()
        {
            return new List<CustomizationRecipe>(recipes);
        }

        /// <summary>
        /// Process a customization recipe to produce customized equipment.
        /// </summary>
        public CustomizedEquipment ProcessRecipe(CustomizationRecipe recipe)
        {
            var customEquipment = new CustomizedEquipment
            {
                equipmentId = recipe.baseEquipmentId,
                enhancementIds = new List<string>(recipe.requiredEnhancements),
                qualityTier = 0,
                isDirty = true
            };

            return customEquipment;
        }
    }
}
