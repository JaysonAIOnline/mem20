using UnityEngine;
using UnityEditor;

public class BuildScript 
{
    static void Build() 
    {
        string[] scenes = new string[] {
            "Assets/Scenes/Boot.unity",
            "Assets/Scenes/MainMenu.unity",
            "Assets/Scenes/Quietvale.unity",
            "Assets/Scenes/BureaucracyHills.unity"
        };
        
        BuildPlayerBuild build = new BuildPlayerBuild();
        build.scenes = scenes;
        build.locationPathName = "/home/jayson/Desktop/jayson-openwebui/projects/unreliable_prophecy/release/build/unreliable_prophecy.exe";
        build.defaultTarget = BuildTarget.StandaloneWindows64;
        build.options = BuildOptions.None;
        
        var report = BuildPipeline.BuildPlayer(build);
        Debug.Log("Build Result: " + report.summary.result);
    }
}