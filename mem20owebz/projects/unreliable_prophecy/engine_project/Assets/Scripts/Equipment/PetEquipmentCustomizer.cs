using UnityEngine;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Manages pet equipment slots and equipped items for companion pets.
    /// Attach to the pet GameObject.
    /// </summary>
    public class PetEquipmentCustomizer : MonoBehaviour
    {
        public static PetEquipmentCustomizer Instance { get; private set; }

        [Header("Pet Info")]
        public string speciesId = "species_wolf";
        public string petName = "Companion";

        [Header("Equipment Slots")]
        public CustomizedPetEquipment collar;
        public CustomizedPetEquipment saddle;
        public CustomizedPetEquipment trinket1;
        public CustomizedPetEquipment trinket2;

        [Header("Inventory")]
        public List<CustomizedPetEquipment> inventory = new List<CustomizedPetEquipment>();

        [Header("Visual Attach Points")]
        public Transform collarAttach;
        public Transform saddleAttach;
        public Transform trinket1Attach;
        public Transform trinket2Attach;

        // Events
        public event System.Action<PetEquipmentSlot, CustomizedPetEquipment> OnEquipmentChanged;
        public event System.Action<CustomizedPetEquipment> OnEquipmentAdded;
        public event System.Action<CustomizedPetEquipment> OnEquipmentRemoved;

        // Visual instances
        private Dictionary<PetEquipmentSlot, GameObject> visualInstances = new Dictionary<PetEquipmentSlot, GameObject>();

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
        }

        /// <summary>
        /// Add equipment to pet inventory.
        /// </summary>
        public void AddToInventory(CustomizedPetEquipment equipment)
        {
            inventory.Add(equipment);
            OnEquipmentAdded?.Invoke(equipment);
        }

        /// <summary>
        /// Remove equipment from pet inventory.
        /// </summary>
        public bool RemoveFromInventory(CustomizedPetEquipment equipment)
        {
            bool removed = inventory.Remove(equipment);
            if (removed)
            {
                OnEquipmentRemoved?.Invoke(equipment);
            }
            return removed;
        }

        /// <summary>
        /// Equip an item from inventory to a slot.
        /// </summary>
        public bool EquipItem(CustomizedPetEquipment equipment, PetEquipmentSlot slot)
        {
            // Unequip current item in slot
            UnequipSlot(slot);

            // Set new item
            switch (slot)
            {
                case PetEquipmentSlot.Collar:
                    collar = equipment;
                    break;
                case PetEquipmentSlot.Saddle:
                    saddle = equipment;
                    break;
                case PetEquipmentSlot.Trinket1:
                    trinket1 = equipment;
                    break;
                case PetEquipmentSlot.Trinket2:
                    trinket2 = equipment;
                    break;
            }

            inventory.Remove(equipment);
            UpdateVisual(slot, equipment);
            OnEquipmentChanged?.Invoke(slot, equipment);

            Debug.Log($"Equipped {equipment.equipmentId} to pet slot {slot}");
            return true;
        }

        /// <summary>
        /// Unequip an item from a slot back to inventory.
        /// </summary>
        public CustomizedPetEquipment UnequipSlot(PetEquipmentSlot slot)
        {
            CustomizedPetEquipment current = null;

            switch (slot)
            {
                case PetEquipmentSlot.Collar:
                    current = collar;
                    collar = null;
                    break;
                case PetEquipmentSlot.Saddle:
                    current = saddle;
                    saddle = null;
                    break;
                case PetEquipmentSlot.Trinket1:
                    current = trinket1;
                    trinket1 = null;
                    break;
                case PetEquipmentSlot.Trinket2:
                    current = trinket2;
                    trinket2 = null;
                    break;
            }

            if (current != null)
            {
                inventory.Add(current);
                ClearVisual(slot);
                OnEquipmentChanged?.Invoke(slot, null);
            }

            return current;
        }

        /// <summary>
        /// Get the currently equipped item in a slot.
        /// </summary>
        public CustomizedPetEquipment GetEquippedItem(PetEquipmentSlot slot)
        {
            switch (slot)
            {
                case PetEquipmentSlot.Collar: return collar;
                case PetEquipmentSlot.Saddle: return saddle;
                case PetEquipmentSlot.Trinket1: return trinket1;
                case PetEquipmentSlot.Trinket2: return trinket2;
                default: return null;
            }
        }

        /// <summary>
        /// Calculate total stats from all equipped pet items.
        /// </summary>
        public EquipmentStats GetTotalStats()
        {
            var total = new EquipmentStats();

            if (collar != null)
                total = total + collar.cachedStats;
            if (saddle != null)
                total = total + saddle.cachedStats;
            if (trinket1 != null)
                total = total + trinket1.cachedStats;
            if (trinket2 != null)
                total = total + trinket2.cachedStats;

            return total;
        }

        /// <summary>
        /// Update visual representation of equipped pet item.
        /// </summary>
        private void UpdateVisual(PetEquipmentSlot slot, CustomizedPetEquipment equipment)
        {
            ClearVisual(slot);

            if (equipment == null) return;

            var db = EquipmentDatabase.Instance;
            if (db == null) return;

            var data = db.GetPetEquipment(equipment.equipmentId);
            if (data == null) return;

            Transform attachPoint = GetAttachPoint(slot);
            if (attachPoint == null) return;

            var visual = new GameObject($"PetEquipment_{slot}_{equipment.equipmentId}");
            visual.transform.SetParent(attachPoint);
            visual.transform.localPosition = Vector3.zero;
            visual.transform.localRotation = Quaternion.identity;

            // Note: Pet equipment visuals would use the same mesh/material system
            // as player equipment, but with pet-specific attach points and scaling.
            // For now, we create a placeholder that can be expanded with actual assets.

            visualInstances[slot] = visual;
        }

        /// <summary>
        /// Clear visual representation of a slot.
        /// </summary>
        private void ClearVisual(PetEquipmentSlot slot)
        {
            if (visualInstances.TryGetValue(slot, out var visual) && visual != null)
            {
                Destroy(visual);
                visualInstances.Remove(slot);
            }
        }

        /// <summary>
        /// Get the attach point transform for a slot.
        /// </summary>
        private Transform GetAttachPoint(PetEquipmentSlot slot)
        {
            switch (slot)
            {
                case PetEquipmentSlot.Collar: return collarAttach;
                case PetEquipmentSlot.Saddle: return saddleAttach;
                case PetEquipmentSlot.Trinket1: return trinket1Attach;
                case PetEquipmentSlot.Trinket2: return trinket2Attach;
                default: return null;
            }
        }

        /// <summary>
        /// Get all equipped items.
        /// </summary>
        public List<CustomizedPetEquipment> GetAllEquipped()
        {
            var equipped = new List<CustomizedPetEquipment>();
            if (collar != null) equipped.Add(collar);
            if (saddle != null) equipped.Add(saddle);
            if (trinket1 != null) equipped.Add(trinket1);
            if (trinket2 != null) equipped.Add(trinket2);
            return equipped;
        }

        /// <summary>
        /// Get all inventory items.
        /// </summary>
        public List<CustomizedPetEquipment> GetInventory()
        {
            return new List<CustomizedPetEquipment>(inventory);
        }

        /// <summary>
        /// Check if a species can use this equipment.
        /// </summary>
        public bool IsSpeciesCompatible(string equipmentId, string species)
        {
            var db = EquipmentDatabase.Instance;
            if (db == null) return false;

            var data = db.GetPetEquipment(equipmentId);
            if (data == null) return false;

            return data.compatibleSpecies.Contains(species);
        }
    }
}
