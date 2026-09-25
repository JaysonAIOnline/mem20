using UnityEngine;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Manages player equipment slots and equipped items.
    /// Attach to the player GameObject.
    /// </summary>
    public class PlayerEquipment : MonoBehaviour
    {
        public static PlayerEquipment Instance { get; private set; }

        [Header("Equipment Slots")]
        public CustomizedEquipment primaryWeapon;
        public CustomizedEquipment secondaryWeapon;
        public CustomizedEquipment armor;
        public CustomizedEquipment accessory1;
        public CustomizedEquipment accessory2;

        [Header("Inventory")]
        public List<CustomizedEquipment> inventory = new List<CustomizedEquipment>();

        [Header("Visual Attach Points")]
        public Transform primaryWeaponAttach;
        public Transform secondaryWeaponAttach;
        public Transform armorAttach;
        public Transform accessory1Attach;
        public Transform accessory2Attach;

        // Events
        public event System.Action<EquipmentSlot, CustomizedEquipment> OnEquipmentChanged;
        public event System.Action<CustomizedEquipment> OnEquipmentAdded;
        public event System.Action<CustomizedEquipment> OnEquipmentRemoved;

        // Visual instances
        private Dictionary<EquipmentSlot, GameObject> visualInstances = new Dictionary<EquipmentSlot, GameObject>();

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
        /// Add equipment to inventory.
        /// </summary>
        public void AddToInventory(CustomizedEquipment equipment)
        {
            inventory.Add(equipment);
            OnEquipmentAdded?.Invoke(equipment);
        }

        /// <summary>
        /// Remove equipment from inventory.
        /// </summary>
        public bool RemoveFromInventory(CustomizedEquipment equipment)
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
        public bool EquipItem(CustomizedEquipment equipment, EquipmentSlot slot)
        {
            // Unequip current item in slot
            UnequipSlot(slot);

            // Set new item
            switch (slot)
            {
                case EquipmentSlot.PrimaryWeapon:
                    primaryWeapon = equipment;
                    break;
                case EquipmentSlot.SecondaryWeapon:
                    secondaryWeapon = equipment;
                    break;
                case EquipmentSlot.Armor:
                    armor = equipment;
                    break;
                case EquipmentSlot.Accessory1:
                    accessory1 = equipment;
                    break;
                case EquipmentSlot.Accessory2:
                    accessory2 = equipment;
                    break;
            }

            inventory.Remove(equipment);
            UpdateVisual(slot, equipment);
            OnEquipmentChanged?.Invoke(slot, equipment);

            Debug.Log($"Equipped {equipment.equipmentId} to slot {slot}");
            return true;
        }

        /// <summary>
        /// Unequip an item from a slot back to inventory.
        /// </summary>
        public CustomizedEquipment UnequipSlot(EquipmentSlot slot)
        {
            CustomizedEquipment current = null;

            switch (slot)
            {
                case EquipmentSlot.PrimaryWeapon:
                    current = primaryWeapon;
                    primaryWeapon = null;
                    break;
                case EquipmentSlot.SecondaryWeapon:
                    current = secondaryWeapon;
                    secondaryWeapon = null;
                    break;
                case EquipmentSlot.Armor:
                    current = armor;
                    armor = null;
                    break;
                case EquipmentSlot.Accessory1:
                    current = accessory1;
                    accessory1 = null;
                    break;
                case EquipmentSlot.Accessory2:
                    current = accessory2;
                    accessory2 = null;
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
        public CustomizedEquipment GetEquippedItem(EquipmentSlot slot)
        {
            switch (slot)
            {
                case EquipmentSlot.PrimaryWeapon: return primaryWeapon;
                case EquipmentSlot.SecondaryWeapon: return secondaryWeapon;
                case EquipmentSlot.Armor: return armor;
                case EquipmentSlot.Accessory1: return accessory1;
                case EquipmentSlot.Accessory2: return accessory2;
                default: return null;
            }
        }

        /// <summary>
        /// Calculate total stats from all equipped items.
        /// </summary>
        public EquipmentStats GetTotalStats()
        {
            var total = new EquipmentStats();

            if (primaryWeapon != null)
                total = total + primaryWeapon.cachedStats;
            if (secondaryWeapon != null)
                total = total + secondaryWeapon.cachedStats;
            if (armor != null)
                total = total + armor.cachedStats;
            if (accessory1 != null)
                total = total + accessory1.cachedStats;
            if (accessory2 != null)
                total = total + accessory2.cachedStats;

            return total;
        }

        /// <summary>
        /// Update visual representation of equipped item.
        /// </summary>
        private void UpdateVisual(EquipmentSlot slot, CustomizedEquipment equipment)
        {
            ClearVisual(slot);

            if (equipment == null) return;

            var db = EquipmentDatabase.Instance;
            if (db == null) return;

            var data = db.GetEquipment(equipment.equipmentId);
            if (data == null || data.equipmentMesh == null) return;

            Transform attachPoint = GetAttachPoint(slot);
            if (attachPoint == null) return;

            var visual = new GameObject($"Equipment_{slot}_{equipment.equipmentId}");
            visual.transform.SetParent(attachPoint);
            visual.transform.localPosition = Vector3.zero;
            visual.transform.localRotation = Quaternion.identity;

            var filter = visual.AddComponent<MeshFilter>();
            filter.mesh = data.equipmentMesh;

            var renderer = visual.AddComponent<MeshRenderer>();
            if (data.equipmentMaterial != null)
            {
                renderer.material = new Material(data.equipmentMaterial);
                renderer.material.color = equipment.customColor;
            }

            visualInstances[slot] = visual;
        }

        /// <summary>
        /// Clear visual representation of a slot.
        /// </summary>
        private void ClearVisual(EquipmentSlot slot)
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
        private Transform GetAttachPoint(EquipmentSlot slot)
        {
            switch (slot)
            {
                case EquipmentSlot.PrimaryWeapon: return primaryWeaponAttach;
                case EquipmentSlot.SecondaryWeapon: return secondaryWeaponAttach;
                case EquipmentSlot.Armor: return armorAttach;
                case EquipmentSlot.Accessory1: return accessory1Attach;
                case EquipmentSlot.Accessory2: return accessory2Attach;
                default: return null;
            }
        }

        /// <summary>
        /// Get all equipped items.
        /// </summary>
        public List<CustomizedEquipment> GetAllEquipped()
        {
            var equipped = new List<CustomizedEquipment>();
            if (primaryWeapon != null) equipped.Add(primaryWeapon);
            if (secondaryWeapon != null) equipped.Add(secondaryWeapon);
            if (armor != null) equipped.Add(armor);
            if (accessory1 != null) equipped.Add(accessory1);
            if (accessory2 != null) equipped.Add(accessory2);
            return equipped;
        }

        /// <summary>
        /// Get all inventory items.
        /// </summary>
        public List<CustomizedEquipment> GetInventory()
        {
            return new List<CustomizedEquipment>(inventory);
        }

        /// <summary>
        /// Clear all equipment.
        /// </summary>
        public void Clear()
        {
            inventory.Clear();
            primaryWeapon = null;
            secondaryWeapon = null;
            armor = null;
            accessory1 = null;
            accessory2 = null;
            foreach (var kvp in visualInstances)
            {
                if (kvp.Value != null)
                    Destroy(kvp.Value);
            }
            visualInstances.Clear();
        }
    }
}
