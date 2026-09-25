using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using System.Collections;

namespace UnreliableProphecy
{
    /// <summary>
    /// Headless smoke-test harness. Inert during normal play (isBatchMode == false).
    /// When run in a -batchmode player it simulates a human playing the main menu:
    /// open Load, open Options, verify managers exist, click New Game, then quit.
    /// Logs "SMOKE PASS" on success or "SMOKE FAIL" with the failing step.
    /// </summary>
    public class SmokeTest : MonoBehaviour
    {
        void Start()
        {
            if (!Application.isBatchMode)
            {
                Destroy(gameObject);
                return;
            }
            DontDestroyOnLoad(gameObject);
            StartCoroutine(Run());
        }

        IEnumerator Run()
        {
            yield return null; yield return null; yield return null;

            string step = "init";
            var mm = FindObjectOfType<MainMenuManager>();
            if (mm == null) { Debug.LogError("SMOKE FAIL at [init]: MainMenuManager missing"); yield return null; Application.Quit(); yield break; }
            if (mm.mainPanel == null || !mm.mainPanel.activeSelf) { Debug.LogError("SMOKE FAIL at [init]: Main panel not active"); yield return null; Application.Quit(); yield break; }
            var newGame = FindButton("New Game");
            var load = FindButton("Load");
            var options = FindButton("Options");
            if (newGame == null || load == null || options == null) { Debug.LogError("SMOKE FAIL at [init]: Main menu buttons missing"); yield return null; Application.Quit(); yield break; }

            step = "Load panel";
            load.onClick.Invoke();
            yield return null; yield return null;
            if (mm.loadPanel == null || !mm.loadPanel.activeSelf) { Debug.LogError($"SMOKE FAIL at [{step}]: Load panel did not open"); yield return null; Application.Quit(); yield break; }
            int slots = mm.saveSlotContainer != null ? mm.saveSlotContainer.childCount : 0;
            if (slots != 3) Debug.LogWarning($"SMOKE NOTE: expected 3 save slots, got {slots}");
            var loadBack = FindButtonIn(mm.loadPanel, "Back");
            if (loadBack == null) { Debug.LogError($"SMOKE FAIL at [{step}]: Load 'Back' button missing"); yield return null; Application.Quit(); yield break; }
            loadBack.onClick.Invoke();
            yield return null; yield return null;
            if (!mm.mainPanel.activeSelf) { Debug.LogError($"SMOKE FAIL at [{step}]: Did not return to main panel"); yield return null; Application.Quit(); yield break; }

            step = "Options panel";
            options.onClick.Invoke();
            yield return null; yield return null;
            if (mm.optionsPanel == null || !mm.optionsPanel.activeSelf) { Debug.LogError($"SMOKE FAIL at [{step}]: Options panel did not open"); yield return null; Application.Quit(); yield break; }
            if (mm.qualityDropdown == null) { Debug.LogError($"SMOKE FAIL at [{step}]: Quality dropdown missing"); yield return null; Application.Quit(); yield break; }
            if (mm.fullscreenToggle == null) { Debug.LogError($"SMOKE FAIL at [{step}]: Fullscreen toggle missing"); yield return null; Application.Quit(); yield break; }
            mm.fullscreenToggle.isOn = !mm.fullscreenToggle.isOn;
            mm.qualityDropdown.value = (mm.qualityDropdown.value + 1) % mm.qualityDropdown.options.Count;
            var optBack = FindButtonIn(mm.optionsPanel, "Back");
            if (optBack == null) { Debug.LogError($"SMOKE FAIL at [{step}]: Options 'Back' button missing"); yield return null; Application.Quit(); yield break; }
            optBack.onClick.Invoke();
            yield return null; yield return null;
            if (!mm.mainPanel.activeSelf) { Debug.LogError($"SMOKE FAIL at [{step}]: Options did not close"); yield return null; Application.Quit(); yield break; }

            step = "Managers";
            if (QuestManager.Instance == null) { Debug.LogError($"SMOKE FAIL at [{step}]: QuestManager not instantiated"); yield return null; Application.Quit(); yield break; }
            if (SaveManager.Instance == null) { Debug.LogError($"SMOKE FAIL at [{step}]: SaveManager not instantiated"); yield return null; Application.Quit(); yield break; }
            if (InventoryManager.Instance == null) { Debug.LogError($"SMOKE FAIL at [{step}]: InventoryManager not instantiated"); yield return null; Application.Quit(); yield break; }
            if (BinderManager.Instance == null) { Debug.LogError($"SMOKE FAIL at [{step}]: BinderManager not instantiated"); yield return null; Application.Quit(); yield break; }
            if (CompanionManager.Instance == null) { Debug.LogError($"SMOKE FAIL at [{step}]: CompanionManager not instantiated"); yield return null; Application.Quit(); yield break; }

            step = "New Game";
            newGame.onClick.Invoke();
            yield return null; yield return null; yield return null; yield return null;
            string scene = SceneManager.GetActiveScene().name;
            if (scene != "Quietvale") { Debug.LogError($"SMOKE FAIL at [{step}]: New Game did not load Quietvale (got '{scene}')"); yield return null; Application.Quit(); yield break; }

            Debug.Log("SMOKE PASS: menu navigation + managers + New Game -> Quietvale OK");
            yield return null;
            Application.Quit();
        }

        static Button FindButton(string label)
        {
            var go = GameObject.Find(label);
            return go != null ? go.GetComponent<Button>() : null;
        }

        static Button FindButtonIn(GameObject parent, string label)
        {
            if (parent == null) return null;
            foreach (var b in parent.GetComponentsInChildren<Button>(true))
            {
                var t = b.GetComponentInChildren<Text>();
                if (t != null && t.text == label) return b;
            }
            return null;
        }
    }
}
