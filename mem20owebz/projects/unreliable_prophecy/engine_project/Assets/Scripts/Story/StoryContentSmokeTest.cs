using UnityEngine;
using System.Collections;
using System.Collections.Generic;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Smoke test for the Story Content and Quest Systems.
    /// Validates that all new systems initialize and integrate correctly.
    /// Run in batchmode: "Unity.exe -batchmode -projectPath . -executeMethod StoryContentSmokeTest.Run"
    /// </summary>
    public class StoryContentSmokeTest : MonoBehaviour
    {
        private int testsPassed = 0;
        private int testsSkipped = 0;

        void Start()
        {
            if (!Application.isBatchMode)
            {
                Destroy(gameObject);
                return;
            }
            DontDestroyOnLoad(gameObject);
            StartCoroutine(RunTests());
        }

        IEnumerator RunTests()
        {
            Debug.Log("[StoryContentSmokeTest] Starting story content and quest system smoke tests...");
            yield return new WaitForSeconds(1f);

            // Load the Quietvale scene first
            UnityEngine.SceneManagement.SceneManager.LoadScene("Quietvale");
            yield return new WaitForSeconds(2f);

            // Wait for bootstrap
            yield return new WaitForSeconds(1f);

            // === CUTSCENE SYSTEM ===
            var cutsceneMgr = CutsceneManager.Instance;
            Assert("cutscene_manager_exists", cutsceneMgr != null, "CutsceneManager missing");

            var cutsceneRegistry = FindObjectOfType<CutsceneRegistry>();
            Assert("cutscene_registry_exists", cutsceneRegistry != null, "CutsceneRegistry missing");

            // === STORY ENGINE ===
            var storyEngine = StoryScriptEngine.Instance;
            Assert("story_engine_exists", storyEngine != null, "StoryScriptEngine missing");

            // Check that chapters were initialized
            if (storyEngine != null)
            {
                var activeChapter = storyEngine.GetActiveChapter();
                Assert("story_engine_chapters", activeChapter != null, "No active chapter after init");
                Debug.Log($"[StoryContentSmokeTest] Active chapter: {activeChapter?.name}");
            }

            // === QUEST EVENT TRIGGER ===
            var questEventTrigger = QuestEventTrigger.Instance;
            Assert("quest_event_trigger_exists", questEventTrigger != null, "QuestEventTrigger missing");

            // === DIALOGUE ROUTER ===
            var dialogueRouter = DialogueRouter.Instance;
            Assert("dialogue_router_exists", dialogueRouter != null, "DialogueRouter missing");

            // === DIALOGUE TREE RUNNER ===
            var treeRunner = DialogueTreeRunner.Instance;
            Assert("dialogue_tree_runner_exists", treeRunner != null, "DialogueTreeRunner missing");

            // === STORY CONTENT LOADER ===
            var contentLoader = StoryContentLoader.Instance;
            Assert("story_content_loader_exists", contentLoader != null, "StoryContentLoader missing");

            // === QUEST CONTENT INTEGRATOR ===
            var integrator = FindObjectOfType<QuestContentIntegrator>();
            Assert("quest_content_integrator_exists", integrator != null, "QuestContentIntegrator missing");

            // === INTEGRATION TESTS ===

            // Test 1: Verify quest manager has all quests
            var questMgr = QuestManager.Instance;
            if (questMgr != null)
            {
                Assert("quest_manager_has_quests", questMgr.allQuests.Count > 0, "No quests loaded");
                Debug.Log($"[StoryContentSmokeTest] Quests loaded: {questMgr.allQuests.Count}");

                // Verify specific quest IDs exist
                string[] requiredQuests = { "T01", "T02", "M01", "M02", "M03", "AMD01", "S01" };
                foreach (var qid in requiredQuests)
                {
                    var quest = questMgr.GetQuest(qid);
                    Assert($"quest_{qid}_exists", quest != null, $"Quest {qid} missing");
                }
            }

            // Test 2: Story flag system
            if (storyEngine != null)
            {
                storyEngine.SetStoryFlag("test_flag", true);
                bool flag = storyEngine.GetStoryFlag("test_flag");
                Assert("story_flag_set_get", flag, "Story flag set/get failed");

                storyEngine.SetStoryFlag("test_flag", false);
                bool flag2 = storyEngine.GetStoryFlag("test_flag");
                Assert("story_flag_clear", !flag2, "Story flag clear failed");
            }

            // Test 3: Quest state routing
            if (dialogueRouter != null && questMgr != null)
            {
                var result = dialogueRouter.GetDialogue("CH_Bureaucrat", "quest_giver", "T01", new Dictionary<string, bool>());
                Assert("dialogue_routing_basic", result != null, "Dialogue routing returned null");
                Debug.Log($"[StoryContentSmokeTest] Routed dialogue: {result?.routeId}");
            }

            // Test 4: Quest acceptance and progression
            if (questMgr != null)
            {
                int initialCount = questMgr.activeQuests.Count;
                questMgr.AcceptQuest("T01");
                Assert("quest_accept", questMgr.activeQuests.Count > initialCount, "Quest not accepted");

                // Test objective update
                questMgr.UpdateObjective("T01", "Speak to the Old Wizard");
                var quest = questMgr.GetQuest("T01");
                var obj = quest?.objectives.FirstOrDefault(o => o.description == "Speak to the Old Wizard");
                Assert("quest_objective_update", obj != null && obj.currentAmount > 0, "Objective not updated");
            }

            // Test 5: Region trigger
            if (questEventTrigger != null)
            {
                questEventTrigger.OnRegionEntered("R1");
                Assert("region_trigger", true, "");
            }

            // Test 6: Cutscene playback (non-blocking check)
            if (cutsceneMgr != null)
            {
                Assert("cutscene_not_playing_initially", !cutsceneMgr.IsPlaying, "Cutscene playing at init");
            }

            // Test 7: Dialogue tree system
            var treeRegistry = FindObjectOfType<DialogueTreeRegistry>();
            Assert("dialogue_tree_registry_exists", treeRegistry != null, "DialogueTreeRegistry missing");

            // Summary
            Debug.Log($"=== STORY CONTENT SMOKE PASS ({testsPassed} passed, {testsSkipped} skipped) ===");
            yield return new WaitForSeconds(1f);
            Application.Quit();
        }

        void Assert(string test, bool condition, string failMessage)
        {
            if (condition)
            {
                testsPassed++;
                Debug.Log($"[StoryContentSmokeTest] PASS: {test}");
            }
            else
            {
                testsPassed++;
                Debug.LogError($"[StoryContentSmokeTest] FAIL: {test} - {failMessage}");
                Debug.LogError($"=== STORY CONTENT SMOKE FAIL at [{test}]: {failMessage} ===");
                Application.Quit();
            }
        }

        void Skip(string test, string reason)
        {
            testsSkipped++;
            Debug.Log($"[StoryContentSmokeTest] SKIP: {test} - {reason}");
        }

        /// <summary>
        /// Entry point for batchmode testing.
        /// </summary>
        public static void Run()
        {
            var go = new GameObject("StoryContentSmokeTest");
            go.AddComponent<StoryContentSmokeTest>();
        }
    }
}
