using UnityEngine;
using UnityEngine.SceneManagement;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Central registry for all game scenes. Maps scene identifiers to their load modes
    /// and provides a single point of truth for scene management.
    /// </summary>
    public static class SceneRegistry
    {
        public enum SceneIdentifier
        {
            Boot,
            MainMenu,
            Quietvale,
            BureaucracyHills,
            Forest,
            CityOfForms,
            Archives,
            Ruins,
            FinalZone,
            CombatTest
        }

        public enum LoadMode
        {
            Single,
            Additive
        }

        private static readonly Dictionary<SceneIdentifier, SceneEntry> _scenes = new Dictionary<SceneIdentifier, SceneEntry>
        {
            { SceneIdentifier.Boot, new SceneEntry("Boot", LoadMode.Single, null) },
            { SceneIdentifier.MainMenu, new SceneEntry("MainMenu", LoadMode.Single, null) },
            { SceneIdentifier.Quietvale, new SceneEntry("Quietvale", LoadMode.Additive, "R1") },
            { SceneIdentifier.BureaucracyHills, new SceneEntry("BureaucracyHills", LoadMode.Additive, "R2") },
            { SceneIdentifier.Forest, new SceneEntry("Forest", LoadMode.Additive, "R3") },
            { SceneIdentifier.CityOfForms, new SceneEntry("CityOfForms", LoadMode.Additive, "R4") },
            { SceneIdentifier.Archives, new SceneEntry("Archives", LoadMode.Additive, "R5") },
            { SceneIdentifier.Ruins, new SceneEntry("Ruins", LoadMode.Additive, "R6") },
            { SceneIdentifier.FinalZone, new SceneEntry("FinalZone", LoadMode.Additive, "R7") },
            { SceneIdentifier.CombatTest, new SceneEntry("CombatTest", LoadMode.Single, null) }
        };

        public struct SceneEntry
        {
            public string SceneName;
            public LoadMode Mode;
            public string RegionId;

            public SceneEntry(string name, LoadMode mode, string regionId)
            {
                SceneName = name;
                Mode = mode;
                RegionId = regionId;
            }
        }

        public static SceneEntry GetScene(SceneIdentifier id)
        {
            return _scenes[id];
        }

        public static string GetSceneName(SceneIdentifier id)
        {
            return _scenes[id].SceneName;
        }

        public static LoadMode GetLoadMode(SceneIdentifier id)
        {
            return _scenes[id].Mode;
        }

        public static string GetRegionId(SceneIdentifier id)
        {
            return _scenes[id].RegionId;
        }

        public static bool IsRegionScene(SceneIdentifier id)
        {
            return _scenes[id].RegionId != null;
        }

        public static IEnumerable<SceneIdentifier> GetAllScenes()
        {
            return _scenes.Keys;
        }

        public static IEnumerable<SceneIdentifier> GetRegionScenes()
        {
            foreach (var kvp in _scenes)
            {
                if (kvp.Value.RegionId != null)
                    yield return kvp.Key;
            }
        }

        public static SceneIdentifier? GetIdentifierByName(string sceneName)
        {
            foreach (var kvp in _scenes)
            {
                if (kvp.Value.SceneName == sceneName)
                    return kvp.Key;
            }
            return null;
        }
    }
}
