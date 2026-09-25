using UnityEngine;
using UnityEngine.SceneManagement;

namespace UnreliableProphecy
{
    /// <summary>
    /// Boot Scene - Initializes all managers before loading MainMenu.
    /// Matches production package: Boot scene for managers initialization.
    /// </summary>
    public class BootManager : MonoBehaviour
    {
        [Header("Scene Names")]
        public string mainMenuScene = "MainMenu";
        
        void Awake()
        {
            // Ensure managers exist (they self-initialize via Awake)
            _ = QuestManager.Instance;
            _ = SaveManager.Instance;
            _ = InventoryManager.Instance;
            _ = BinderManager.Instance;
            _ = CompanionManager.Instance;
            
            // Load MainMenu
            SceneManager.LoadScene(mainMenuScene);
        }
    }
}