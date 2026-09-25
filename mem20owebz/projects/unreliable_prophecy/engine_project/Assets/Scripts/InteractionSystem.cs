using UnityEngine;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Interaction system for objects in the world.
    /// Bureaucrat, Binder, Filing Cabinets, Desks, Forms, etc.
    /// </summary>
    public interface IInteractable
    {
        void Interact(PlayerController player);
        string GetInteractionText();
    }

    /// <summary>
    /// Base world interactable - Bureaucrat, Binder, Filing Cabinets, Desks, Forms, etc.
    /// </summary>
    public class WorldInteractable : MonoBehaviour, IInteractable
    {
        [Header("Interaction")]
        public string interactableName;
        public string interactionText = "Press E to interact";
        public InteractionType type = InteractionType.Generic;

        protected bool playerInRange;

        public virtual void Interact(PlayerController player)
        {
            Debug.Log($"Interacted with {interactableName}");
        }

        public virtual string GetInteractionText() => interactionText;

        void OnTriggerEnter(Collider other)
        {
            if (other.CompareTag("Player"))
                playerInRange = true;
        }

        void OnTriggerExit(Collider other)
        {
            if (other.CompareTag("Player"))
                playerInRange = false;
        }
    }

    public enum InteractionType { Generic, Bureaucrat, Binder, FilingCabinet, Desk, Form, Amendment, Companion, CraftingStation, CustomizationStation }

    /// <summary>
    /// Bureaucrat NPC - gives quests, dialogue, stamps.
    /// </summary>
    public class BureaucratNPC : WorldInteractable
    {
        [Header("Dialogue")]
        public List<string> dialogueLines = new List<string>();
        public List<string> postQuestLines = new List<string>();
        int currentLineIndex = 0;
        bool questGiven = false;

        [Header("Quest")]
        public string questIdToGive;

        public override void Interact(PlayerController player)
        {
            if (!questGiven && !string.IsNullOrEmpty(questIdToGive))
            {
                QuestManager.Instance.AcceptQuest(questIdToGive);
                questGiven = true;
            }

            var lines = questGiven ? postQuestLines : dialogueLines;
            if (lines.Count > 0)
            {
                string line = lines[currentLineIndex % lines.Count];
                Debug.Log($"[{interactableName}]: {line}");
                currentLineIndex++;
            }
        }
    }

    /// <summary>
    /// Filing Cabinet - stores forms, amendments, loot.
    /// </summary>
    public class FilingCabinet : WorldInteractable
    {
        [Header("Contents")]
        public List<string> containedItems = new List<string>();
        public bool isLocked = false;
        public string requiredKey;

        public override void Interact(PlayerController player)
        {
            if (isLocked)
            {
                if (InventoryManager.Instance.HasItem(requiredKey))
                {
                    isLocked = false;
                    Debug.Log($"{interactableName} unlocked!");
                    GiveContents(player);
                }
                else
                {
                    Debug.Log($"{interactableName} is locked. Need {requiredKey}");
                }
            }
            else
            {
                GiveContents(player);
            }
        }

        void GiveContents(PlayerController player)
        {
            foreach (var item in containedItems)
            {
                InventoryManager.Instance.AddItem(item);
                Debug.Log($"Found {item} in {interactableName}");
            }
            containedItems.Clear();
        }
    }

    /// <summary>
    /// Desk - submit forms, get stamps.
    /// </summary>
    public class DeskInteractable : WorldInteractable
    {
        [Header("Form Processing")]
        public string requiredFormId;
        public string outputStampId;
        public bool consumesForm = true;

        public override void Interact(PlayerController player)
        {
            if (InventoryManager.Instance.HasItem(requiredFormId))
            {
                if (consumesForm)
                    InventoryManager.Instance.RemoveItem(requiredFormId);

                InventoryManager.Instance.AddItem(outputStampId);
                Debug.Log($"Submitted {requiredFormId}, received {outputStampId}");

                // Update quest objectives
                QuestManager.Instance.UpdateObjective("T01", "Stamp the form");
                QuestManager.Instance.UpdateObjective("M01", "Submit Form 47-B");
            }
            else
            {
                Debug.Log($"Need {requiredFormId} to use this desk");
            }
        }
    }

    /// <summary>
    /// Form Item - collectible form for quests.
    /// </summary>
    public class FormItem : WorldInteractable
    {
        [Header("Form Data")]
        public string formId;
        public string formName;

        public override void Interact(PlayerController player)
        {
            InventoryManager.Instance.AddItem(formId);
            Debug.Log($"Picked up {formName} ({formId})");
            Destroy(gameObject);
        }
    }
}