using UnityEngine;
using UnityEngine.UI;
using TMPro;
using System.Collections.Generic;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// UI Controller for the equipment customization interface.
    /// Shows equipment slots, materials, enhancements, and stat comparisons.
    /// </summary>
    public class EquipmentCustomizationUI : MonoBehaviour
    {
        [Header("UI Containers")]
        public Transform playerSlotsContainer;
        public Transform petSlotsContainer;
        public Transform materialListContainer;
        public Transform enhancementListContainer;
        public Transform inventoryListContainer;

        [Header("Prefabs")]
        public GameObject slotEntryPrefab;
        public GameObject materialEntryPrefab;
        public GameObject enhancementEntryPrefab;
        public GameObject inventoryEntryPrefab;
        public GameObject statRowPrefab;

        [Header("Selected Item Display")]
        public TextMeshProUGUI selectedItemName;
        public TextMeshProUGUI selectedItemDescription;
        public Image selectedItemIcon;

        [Header("Stats Display")]
        public Transform currentStatsContainer;
        public Transform previewStatsContainer;

        [Header("Buttons")]
        public Button applyMaterialButton;
        public Button removeMaterialButton;
        public Button applyEnhancementButton;
        public Button removeEnhancementButton;
        public Button confirmButton;
        public Button cancelButton;

        [Header("Toggle")]
        public Toggle playerPetToggle; // false = player, true = pet

        [Header("Color Picker")]
        public Slider colorRSlider;
        public Slider colorGSlider;
        public Slider colorBSlider;
        public Image colorPreview;

        // State
        private CustomizedEquipment selectedPlayerEquipment;
        private CustomizedPetEquipment selectedPetEquipment;
        private string selectedMaterialId;
        private string selectedEnhancementId;
        private bool isPlayerMode = true;

        void Start()
        {
            if (applyMaterialButton != null)
                applyMaterialButton.onClick.AddListener(OnApplyMaterialClicked);
            if (removeMaterialButton != null)
                removeMaterialButton.onClick.AddListener(OnRemoveMaterialClicked);
            if (applyEnhancementButton != null)
                applyEnhancementButton.onClick.AddListener(OnApplyEnhancementClicked);
            if (removeEnhancementButton != null)
                removeEnhancementButton.onClick.AddListener(OnRemoveEnhancementClicked);
            if (confirmButton != null)
                confirmButton.onClick.AddListener(OnConfirmClicked);
            if (cancelButton != null)
                cancelButton.onClick.AddListener(OnCancelClicked);
            if (playerPetToggle != null)
                playerPetToggle.onValueChanged.AddListener(OnModeToggled);

            // Subscribe to events
            if (EquipmentCustomizer.Instance != null)
            {
                EquipmentCustomizer.Instance.OnEquipmentCustomized += OnEquipmentUpdated;
            }
        }

        void OnDestroy()
        {
            if (EquipmentCustomizer.Instance != null)
            {
                EquipmentCustomizer.Instance.OnEquipmentCustomized -= OnEquipmentUpdated;
            }
        }

        /// <summary>
        /// Open the customization UI for a piece of equipment.
        /// </summary>
        public void Open(CustomizedEquipment equipment)
        {
            selectedPlayerEquipment = equipment;
            selectedPetEquipment = null;
            isPlayerMode = true;
            gameObject.SetActive(true);

            RefreshEquipmentSlots();
            RefreshMaterialList();
            RefreshEnhancementList();
            RefreshStatsDisplay();
            UpdateSelectedItemDisplay();
        }

        /// <summary>
        /// Open the customization UI for a pet equipment.
        /// </summary>
        public void OpenPet(CustomizedPetEquipment equipment)
        {
            selectedPetEquipment = equipment;
            selectedPlayerEquipment = null;
            isPlayerMode = false;
            gameObject.SetActive(true);

            RefreshPetEquipmentSlots();
            RefreshEnhancementList();
            RefreshPetStatsDisplay();
            UpdatePetSelectedItemDisplay();
        }

        /// <summary>
        /// Close the customization UI.
        /// </summary>
        public void Close()
        {
            selectedPlayerEquipment = null;
            selectedPetEquipment = null;
            gameObject.SetActive(false);
        }

        #region UI Refresh Methods

        private void RefreshEquipmentSlots()
        {
            if (playerSlotsContainer == null) return;

            foreach (Transform child in playerSlotsContainer)
                Destroy(child.gameObject);

            if (PlayerEquipment.Instance == null) return;

            var slots = new[]
            {
                ("Primary Weapon", PlayerEquipment.Instance.primaryWeapon),
                ("Secondary Weapon", PlayerEquipment.Instance.secondaryWeapon),
                ("Armor", PlayerEquipment.Instance.armor),
                ("Accessory 1", PlayerEquipment.Instance.accessory1),
                ("Accessory 2", PlayerEquipment.Instance.accessory2)
            };

            foreach (var (name, equipment) in slots)
            {
                var entry = Instantiate(slotEntryPrefab, playerSlotsContainer);
                var text = entry.GetComponentInChildren<TextMeshProUGUI>();
                if (text != null)
                {
                    text.text = string.IsNullOrEmpty(equipment.equipmentId)
                        ? $"{name} (Empty)"
                        : $"{name}: {equipment.equipmentId}";
                }
            }
        }

        private void RefreshPetEquipmentSlots()
        {
            if (petSlotsContainer == null) return;

            foreach (Transform child in petSlotsContainer)
                Destroy(child.gameObject);

            if (PetEquipmentCustomizer.Instance == null) return;

            var slots = new[]
            {
                ("Collar", PetEquipmentCustomizer.Instance.collar),
                ("Saddle", PetEquipmentCustomizer.Instance.saddle),
                ("Trinket 1", PetEquipmentCustomizer.Instance.trinket1),
                ("Trinket 2", PetEquipmentCustomizer.Instance.trinket2)
            };

            foreach (var (name, equipment) in slots)
            {
                var entry = Instantiate(slotEntryPrefab, petSlotsContainer);
                var text = entry.GetComponentInChildren<TextMeshProUGUI>();
                if (text != null)
                {
                    text.text = string.IsNullOrEmpty(equipment.equipmentId)
                        ? $"{name} (Empty)"
                        : $"{name}: {equipment.equipmentId}";
                }
            }
        }

        private void RefreshMaterialList()
        {
            if (materialListContainer == null) return;

            foreach (Transform child in materialListContainer)
                Destroy(child.gameObject);

            if (EquipmentDatabase.Instance == null || selectedPlayerEquipment == null) return;

            var equipmentData = EquipmentDatabase.Instance.GetEquipment(selectedPlayerEquipment.equipmentId);
            if (equipmentData == null) return;

            var materials = EquipmentDatabase.Instance.GetCompatibleMaterials(equipmentData);

            foreach (var material in materials)
            {
                var entry = Instantiate(materialEntryPrefab, materialListContainer);
                var text = entry.GetComponentInChildren<TextMeshProUGUI>();
                if (text != null)
                {
                    text.text = material.displayName;
                }

                var button = entry.GetComponent<Button>();
                if (button != null)
                {
                    var mat = material; // Capture for closure
                    button.onClick.AddListener(() => SelectMaterial(mat.materialId));
                }
            }
        }

        private void RefreshEnhancementList()
        {
            if (enhancementListContainer == null) return;

            foreach (Transform child in enhancementListContainer)
                Destroy(child.gameObject);

            if (EquipmentDatabase.Instance == null) return;

            List<EnhancementData> enhancements;

            if (isPlayerMode && selectedPlayerEquipment != null)
            {
                var equipmentData = EquipmentDatabase.Instance.GetEquipment(selectedPlayerEquipment.equipmentId);
                if (equipmentData == null) return;
                enhancements = EquipmentDatabase.Instance.GetCompatibleEnhancements(equipmentData);
            }
            else if (!isPlayerMode && selectedPetEquipment != null)
            {
                var petData = EquipmentDatabase.Instance.GetPetEquipment(selectedPetEquipment.equipmentId);
                if (petData == null) return;
                enhancements = EquipmentDatabase.Instance.GetCompatiblePetEnhancements(petData);
            }
            else
            {
                return;
            }

            foreach (var enhancement in enhancements)
            {
                var entry = Instantiate(enhancementEntryPrefab, enhancementListContainer);
                var text = entry.GetComponentInChildren<TextMeshProUGUI>();
                if (text != null)
                {
                    text.text = enhancement.displayName;
                }

                var button = entry.GetComponent<Button>();
                if (button != null)
                {
                    var enh = enhancement; // Capture for closure
                    button.onClick.AddListener(() => SelectEnhancement(enh.enhancementId));
                }
            }
        }

        private void RefreshStatsDisplay()
        {
            if (selectedPlayerEquipment == null) return;

            // Current stats
            if (currentStatsContainer != null)
            {
                foreach (Transform child in currentStatsContainer)
                    Destroy(child.gameObject);

                var currentStats = ItemStatResolver.GetCustomizedStats(
                    selectedPlayerEquipment.equipmentId,
                    selectedPlayerEquipment.qualityTier,
                    selectedPlayerEquipment.materialId,
                    selectedPlayerEquipment.enhancementIds
                );

                PopulateStats(currentStatsContainer, currentStats);
            }

            // Preview stats (with selected material/enhancement)
            if (previewStatsContainer != null)
            {
                foreach (Transform child in previewStatsContainer)
                    Destroy(child.gameObject);

                var previewMaterialId = selectedMaterialId ?? selectedPlayerEquipment.materialId;
                var previewEnhancements = new List<string>(selectedPlayerEquipment.enhancementIds);
                if (!string.IsNullOrEmpty(selectedEnhancementId) && !previewEnhancements.Contains(selectedEnhancementId))
                {
                    previewEnhancements.Add(selectedEnhancementId);
                }

                var previewStats = ItemStatResolver.GetCustomizedStats(
                    selectedPlayerEquipment.equipmentId,
                    selectedPlayerEquipment.qualityTier,
                    previewMaterialId,
                    previewEnhancements
                );

                PopulateStats(previewStatsContainer, previewStats);
            }
        }

        private void RefreshPetStatsDisplay()
        {
            if (selectedPetEquipment == null) return;

            if (currentStatsContainer != null)
            {
                foreach (Transform child in currentStatsContainer)
                    Destroy(child.gameObject);

                var currentStats = ItemStatResolver.GetPetEquipmentStats(
                    selectedPetEquipment.equipmentId,
                    selectedPetEquipment.enhancementIds
                );

                PopulateStats(currentStatsContainer, currentStats);
            }
        }

        private void PopulateStats(Transform container, EquipmentStats stats)
        {
            if (container == null || statRowPrefab == null) return;

            var statFields = new Dictionary<string, int>
            {
                {"Damage", stats.damage},
                {"Defense", stats.defense},
                {"Durability", stats.durability},
                {"Weight", stats.weight},
                {"Speed", stats.speed},
                {"Accuracy", stats.accuracy},
                {"Crit Chance", stats.critChance},
                {"Crit Damage", stats.critDamage},
                {"Range", stats.range},
                {"Handling", stats.handling}
            };

            foreach (var kvp in statFields)
            {
                if (kvp.Value == 0) continue;

                var row = Instantiate(statRowPrefab, container);
                var text = row.GetComponentInChildren<TextMeshProUGUI>();
                if (text != null)
                {
                    text.text = $"{kvp.Key}: {kvp.Value}";
                }
            }
        }

        private void UpdateSelectedItemDisplay()
        {
            if (selectedPlayerEquipment == null) return;

            var db = EquipmentDatabase.Instance;
            if (db == null) return;

            var data = db.GetEquipment(selectedPlayerEquipment.equipmentId);
            if (data == null) return;

            if (selectedItemName != null)
                selectedItemName.text = data.displayName;
            if (selectedItemDescription != null)
                selectedItemDescription.text = data.description;
            if (selectedItemIcon != null && data.icon != null)
                selectedItemIcon.sprite = data.icon;
        }

        private void UpdatePetSelectedItemDisplay()
        {
            if (selectedPetEquipment == null) return;

            var db = EquipmentDatabase.Instance;
            if (db == null) return;

            var data = db.GetPetEquipment(selectedPetEquipment.equipmentId);
            if (data == null) return;

            if (selectedItemName != null)
                selectedItemName.text = data.displayName;
            if (selectedItemDescription != null)
                selectedItemDescription.text = data.description;
            if (selectedItemIcon != null && data.icon != null)
                selectedItemIcon.sprite = data.icon;
        }

        #endregion

        #region Event Handlers

        private void OnModeToggled(bool isPetMode)
        {
            isPlayerMode = !isPetMode;
            RefreshEquipmentSlots();
            RefreshPetEquipmentSlots();
            RefreshMaterialList();
            RefreshEnhancementList();
        }

        private void SelectMaterial(string materialId)
        {
            selectedMaterialId = materialId;
            RefreshStatsDisplay();
        }

        private void SelectEnhancement(string enhancementId)
        {
            selectedEnhancementId = enhancementId;
            RefreshStatsDisplay();
        }

        private void OnApplyMaterialClicked()
        {
            if (selectedPlayerEquipment == null || string.IsNullOrEmpty(selectedMaterialId)) return;

            if (EquipmentCustomizer.Instance != null)
            {
                EquipmentCustomizer.Instance.ApplyMaterial(selectedPlayerEquipment, selectedMaterialId);
                RefreshStatsDisplay();
            }
        }

        private void OnRemoveMaterialClicked()
        {
            if (selectedPlayerEquipment == null) return;

            if (EquipmentCustomizer.Instance != null)
            {
                EquipmentCustomizer.Instance.RemoveMaterial(selectedPlayerEquipment);
                selectedMaterialId = null;
                RefreshStatsDisplay();
            }
        }

        private void OnApplyEnhancementClicked()
        {
            if (string.IsNullOrEmpty(selectedEnhancementId)) return;

            if (EquipmentCustomizer.Instance != null)
            {
                if (isPlayerMode && selectedPlayerEquipment != null)
                {
                    EquipmentCustomizer.Instance.ApplyEnhancement(selectedPlayerEquipment, selectedEnhancementId);
                }
                else if (!isPlayerMode && selectedPetEquipment != null)
                {
                    EquipmentCustomizer.Instance.ApplyPetEnhancement(selectedPetEquipment, selectedEnhancementId);
                }
                selectedEnhancementId = null;
                RefreshStatsDisplay();
            }
        }

        private void OnRemoveEnhancementClicked()
        {
            if (string.IsNullOrEmpty(selectedEnhancementId)) return;

            if (EquipmentCustomizer.Instance != null)
            {
                if (isPlayerMode && selectedPlayerEquipment != null)
                {
                    EquipmentCustomizer.Instance.RemoveEnhancement(selectedPlayerEquipment, selectedEnhancementId);
                }
                else if (!isPlayerMode && selectedPetEquipment != null)
                {
                    EquipmentCustomizer.Instance.RemovePetEnhancement(selectedPetEquipment, selectedEnhancementId);
                }
                selectedEnhancementId = null;
                RefreshStatsDisplay();
            }
        }

        private void OnConfirmClicked()
        {
            // Apply color changes
            if (colorRSlider != null && colorGSlider != null && colorBSlider != null)
            {
                var color = new Color(colorRSlider.value, colorGSlider.value, colorBSlider.value);

                if (isPlayerMode && selectedPlayerEquipment != null)
                {
                    selectedPlayerEquipment.customColor = color;
                }
                else if (!isPlayerMode && selectedPetEquipment != null)
                {
                    selectedPetEquipment.customColor = color;
                }
            }

            Close();
        }

        private void OnCancelClicked()
        {
            Close();
        }

        private void OnEquipmentUpdated(CustomizedEquipment equipment)
        {
            if (equipment == selectedPlayerEquipment)
            {
                RefreshStatsDisplay();
            }
        }

        #endregion
    }
}
