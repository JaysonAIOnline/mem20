#!/usr/bin/env python3
"""
MCP Server for mem20

This server implements the Model Context Protocol (MCP) to provide
context, tools, and prompts to AI clients. It exposes:
- Memory management tools (store, recall, search)
- Cognitive thought processing tools
- Roadmap management tools
- File system access

The server runs as a JSON-RPC 2.0 service over stdio transport.
"""

import json
import os
import sys
import subprocess
import tempfile
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import MCP framework
try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: mcp package not installed. Please install with:")
    print("pip install mcp")
    sys.exit(1)

# Make the unified engine importable. `import memory` resolves (via the repo-root
# shim) to `memory_engine/memory.py`, so the live deployment, a clean clone, and the
# GitHub source all share one engine module. User data lives under MEM20_STORE_PATH
# (engine default ~/.mem20/store) — code and data are fully separated.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
try:
    from memory import remember, recall, status as mem_status, rebuild_index, ledger_view
    MEMORY_SYSTEM_AVAILABLE = True
except ImportError:
    MEMORY_SYSTEM_AVAILABLE = False
try:
    from memory import audit_contamination as _ENGINE_AUDIT
except ImportError:
    _ENGINE_AUDIT = None


from memory_tools import MemoryToolsMixin
from cognitive_tools import CognitiveToolsMixin
from roadmap_tools import RoadmapToolsMixin
from tools.world_tools import WorldToolsMixin
from tools.blender_tools import BlenderToolsMixin
from tools.unity_tools import UnityToolsMixin
from tools.integration_tools import IntegrationToolsMixin
from health import start_health_server

class Mem20MCPServer(MemoryToolsMixin, CognitiveToolsMixin, RoadmapToolsMixin,
                     WorldToolsMixin, BlenderToolsMixin, UnityToolsMixin,
                     IntegrationToolsMixin):
    def __init__(self):
        self.tools = {}
        self._start_time = time.time()
        self._request_count = 0
        self._request_errors = 0
        self._tool_calls = {}
        self._tool_errors = {}
        self._event_taxonomy = ["tool.call", "tool.success", "tool.error"]
        self._audit_cache = None
        self._audit_cache_ts = 0.0
        self._setup_tools()
        # Use the modern API with on_list_tools and on_call_tool
        self.server = Server(
            "mem20-mcp",
            on_list_tools=self._handle_list_tools,
            on_call_tool=self._handle_call_tool,
        )
    def _setup_tools(self):
        """Define all available tools for mem20."""
        self.register_memory_tools()
        self.register_cognitive_tools()
        self.register_roadmap_tools()
        self.register_world_tools()
        self.register_blender_tools()
        self.register_unity_tools()
        self.register_integration_tools()
    async def _handle_list_tools(self, context: ServerRequestContext, params: Optional[mt.PaginatedRequestParams]) -> mt.ListToolsResult:
        """Handle tools/list request."""
        return mt.ListToolsResult(
            tools=list(self.tools.values()),
            resultType="complete"
        )
    async def _handle_call_tool(self, context: ServerRequestContext, params: mt.CallToolRequestParams) -> mt.CallToolResult:
        """Handle tools/call request."""
        self._request_count += 1
        tool_name = params.name
        arguments = params.arguments or {}
        self._tool_calls[tool_name] = self._tool_calls.get(tool_name, 0) + 1
        
        if tool_name not in self.tools:
            self._request_errors += 1
            self._tool_errors[tool_name] = self._tool_errors.get(tool_name, 0) + 1
            return mt.CallToolResult(
                content=[mt.TextContent(type="text", text=f"Error: Unknown tool '{tool_name}'")],
                isError=True,
                resultType="complete"
            )
        
        try:
            result = await self._execute_tool(tool_name, arguments)
            return mt.CallToolResult(
                content=[mt.TextContent(type="text", text=result)],
                isError=False,
                resultType="complete"
            )
        except Exception as e:
            self._request_errors += 1
            self._tool_errors[tool_name] = self._tool_errors.get(tool_name, 0) + 1
            return mt.CallToolResult(
                content=[mt.TextContent(type="text", text=f"Error executing tool: {str(e)}")],
                isError=True,
                resultType="complete"
            )
    async def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool and return result as string."""
        
        # Memory tools
        if tool_name == "memory_store":
            return await self._memory_store(arguments)
        elif tool_name == "memory_recall":
            return await self._memory_recall(arguments)
        elif tool_name == "memory_probe":
            return await self._memory_probe(arguments)
        elif tool_name == "memory_reason":
            return await self._memory_reason(arguments)
        elif tool_name == "memory_status":
            return await self._memory_status()
        # Enhanced retrieval tools
        elif tool_name == "memory_recall_semantic":
            return await self._memory_recall_semantic(arguments)
        elif tool_name == "memory_recall_hybrid":
            return await self._memory_recall_hybrid(arguments)
        elif tool_name == "memory_recall_graph":
            return await self._memory_recall_graph(arguments)
        elif tool_name == "memory_entity_extract":
            return await self._memory_entity_extract(arguments)
        elif tool_name == "memory_auto_consolidate":
            return await self._memory_auto_consolidate(arguments)
        # Procedural Memory tools
        elif tool_name == "procedural_add_skill":
            return await self._procedural_add_skill(arguments)
        elif tool_name == "procedural_get_skill":
            return await self._procedural_get_skill(arguments)
        elif tool_name == "procedural_find_skills":
            return await self._procedural_find_skills(arguments)
        elif tool_name == "procedural_execute_skill":
            return await self._procedural_execute_skill(arguments)
        elif tool_name == "procedural_learn":
            return await self._procedural_learn(arguments)
        elif tool_name == "procedural_list_skills":
            return await self._procedural_list_skills(arguments)
        # World Model tools
        elif tool_name == "world_model_add_variable":
            return await self._world_model_add_variable(arguments)
        elif tool_name == "world_model_add_rule":
            return await self._world_model_add_rule(arguments)
        elif tool_name == "world_model_simulate":
            return await self._world_model_simulate(arguments)
        elif tool_name == "world_model_predict":
            return await self._world_model_predict(arguments)
        elif tool_name == "world_model_get_state":
            return await self._world_model_get_state(arguments)
        elif tool_name == "world_model_reset":
            return await self._world_model_reset(arguments)
        elif tool_name == "world_model_record_prediction":
            return await self._world_model_record_prediction(arguments)
        elif tool_name == "world_model_resolve_prediction":
            return await self._world_model_resolve_prediction(arguments)
        # Affective/Value tools
        elif tool_name == "affective_set_value":
            return await self._affective_set_value(arguments)
        elif tool_name == "affective_set_emotion":
            return await self._affective_set_emotion(arguments)
        elif tool_name == "affective_add_goal":
            return await self._affective_add_goal(arguments)
        elif tool_name == "affective_update_preference":
            return await self._affective_update_preference(arguments)
        elif tool_name == "affective_evaluate":
            return await self._affective_evaluate(arguments)
        elif tool_name == "affective_get_state":
            return await self._affective_get_state(arguments)
        # Metacognitive/Epistemic tools
        elif tool_name == "memory_assess_confidence":
            return await self._memory_assess_confidence(arguments)
        elif tool_name == "memory_set_epistemic_status":
            return await self._memory_set_epistemic_status(arguments)
        elif tool_name == "memory_detect_gaps":
            return await self._memory_detect_gaps(arguments)
        elif tool_name == "memory_self_audit":
            return await self._memory_self_audit(arguments)
        # Step 7.4 — Memory / Simulation Contamination Controls
        elif tool_name == "memory_simulate_store":
            return await self._memory_simulate_store(arguments)
        elif tool_name == "memory_promote":
            return await self._memory_promote(arguments)
        elif tool_name == "memory_list_simulated":
            return await self._memory_list_simulated(arguments)
        elif tool_name == "memory_quarantine_simulated":
            return await self._memory_quarantine_simulated(arguments)
        elif tool_name == "memory_audit_contamination":
            return await self._memory_audit_contamination(arguments)
        elif tool_name == "memory_epistemic_veto":
            return await self._memory_epistemic_veto(arguments)
        # Pinned Blocks tools
        elif tool_name == "memory_pin_block":
            return await self._memory_pin_block(arguments)
        elif tool_name == "memory_unpin_block":
            return await self._memory_unpin_block(arguments)
        elif tool_name == "memory_list_pinned_blocks":
            return await self._memory_list_pinned_blocks(arguments)
        elif tool_name == "memory_get_pinned_block":
            return await self._memory_get_pinned_block(arguments)
        # Multi-modal Ingestion tools
        elif tool_name == "memory_ingest_pdf":
            return await self._memory_ingest_pdf(arguments)
        elif tool_name == "memory_ingest_image":
            return await self._memory_ingest_image(arguments)
        elif tool_name == "memory_ingest_audio":
            return await self._memory_ingest_audio(arguments)
        elif tool_name == "memory_ingest_code":
            return await self._memory_ingest_code(arguments)
        # Multi-agent Shared Memory tools
        elif tool_name == "memory_namespace_create":
            return await self._memory_namespace_create(arguments)
        elif tool_name == "memory_namespace_list":
            return await self._memory_namespace_list(arguments)
        elif tool_name == "memory_shared_store":
            return await self._memory_shared_store(arguments)
        elif tool_name == "memory_shared_recall":
            return await self._memory_shared_recall(arguments)
        # PII/Secret Detection tools
        elif tool_name == "memory_scan_pii":
            return await self._memory_scan_pii(arguments)
        # Self-Model/Identity tools
        elif tool_name == "self_model_create":
            return await self._self_model_create(arguments)
        elif tool_name == "self_model_get":
            return await self._self_model_get(arguments)
        elif tool_name == "self_model_reflect":
            return await self._self_model_reflect(arguments)
        # Theory of Mind tools
        elif tool_name == "theory_of_mind_simulate":
            return await self._theory_of_mind_simulate(arguments)
        elif tool_name == "theory_of_mind_perspective":
            return await self._theory_of_mind_perspective(arguments)
        # Corrigibility/Shutdown tools
        elif tool_name == "corrigibility_shutdown":
            return await self._corrigibility_shutdown(arguments)
        elif tool_name == "corrigibility_capability_tier":
            return await self._corrigibility_capability_tier(arguments)
        
        # Cognitive tools
        elif tool_name == "cog_process":
            return await self._cog_process(arguments)
        elif tool_name == "cog_chain":
            return await self._cog_chain(arguments)
        elif tool_name == "cog_reason":
            return await self._cog_reason(arguments)
        elif tool_name == "cog_plan":
            return await self._cog_plan(arguments)
        elif tool_name == "cog_reflect":
            return await self._cog_reflect(arguments)
        elif tool_name == "cog_working_memory":
            return await self._cog_working_memory(arguments)
        
        # Roadmap tools
        elif tool_name == "roadmap_create":
            return await self._roadmap_create(arguments)
        elif tool_name == "roadmap_list":
            return await self._roadmap_list()
        elif tool_name == "roadmap_get":
            return await self._roadmap_get(arguments)
        elif tool_name == "roadmap_update_phase":
            return await self._roadmap_update_phase(arguments)
        
        # File system tools
        elif tool_name == "fs_read":
            return await self._fs_read(arguments)
        elif tool_name == "fs_write":
            return await self._fs_write(arguments)
        elif tool_name == "fs_list":
            return await self._fs_list(arguments)
        
        # Holographic memory tools (deep memory queries)
        elif tool_name == "memory_contradict":
            return await self._memory_contradict(arguments)
        elif tool_name == "memory_related":
            return await self._memory_related(arguments)
        elif tool_name == "memory_feedback":
            return await self._memory_feedback(arguments)
        
        # Blender tools
        elif tool_name == "blender_create_object":
            return await self._blender_create_object(arguments)
        elif tool_name == "blender_add_material":
            return await self._blender_add_material(arguments)
        elif tool_name == "blender_set_camera":
            return await self._blender_set_camera(arguments)
        elif tool_name == "blender_render":
            return await self._blender_render(arguments)
        elif tool_name == "blender_export_glb":
            return await self._blender_export_glb(arguments)
        elif tool_name == "blender_run_bpy":
            return await self._blender_run_bpy(arguments)
        elif tool_name == "blender_clear_scene":
            return await self._blender_clear_scene(arguments)
        
        # Imagination tools
        elif tool_name == "imagination_concept":
            return await self._imagination_concept(arguments)
        elif tool_name == "imagination_visualize":
            return await self._imagination_visualize(arguments)
        elif tool_name == "imagination_prototype":
            return await self._imagination_prototype(arguments)
        elif tool_name == "imagination_dream":
            return await self._imagination_dream(arguments)
        elif tool_name == "imagination_critique":
            return await self._imagination_critique(arguments)
        elif tool_name == "imagination_simulate":
            return await self._imagination_simulate(arguments)
        elif tool_name == "imagination_counterfactual":
            return await self._imagination_counterfactual(arguments)
        elif tool_name == "imagination_recombine":
            return await self._imagination_recombine(arguments)
        elif tool_name == "imagination_model":
            return await self._imagination_model(arguments)
        
        # Unity tools
        elif tool_name == "unity_create_script":
            return await self._unity_create_script(arguments)
        elif tool_name == "unity_build_project":
            return await self._unity_build_project(arguments)
        elif tool_name == "unity_run_test":
            return await self._unity_run_test(arguments)
        elif tool_name == "unity_generate_asmdef":
            return await self._unity_generate_asmdef(arguments)
        elif tool_name == "unity_validate_project":
            return await self._unity_validate_project(arguments)
        
        return f"Unknown tool: {tool_name}"
    def _persist_simulated(self, args: Dict, out, sim_type: str):
        """Route any persisted simulation output into the SEPARATE simulated partition.

        Grounded memory is never touched here (Step 7.4 hard separation)."""
        if not MEMORY_SYSTEM_AVAILABLE or not out:
            return
        try:
            from memory import remember_simulated
            remember_simulated(
                topic=args.get("topic", "simulation"),
                content=str(out)[:1500],
                tags=["simulation", sim_type],
                sim_type=sim_type,
                scenario=str(args)[:300],
            )
        except Exception:
            pass
    async def _run_blender_script(self, script: str, timeout: int = 180) -> str:
        import tempfile
        import subprocess
        import os
        import shutil

        exe = os.environ.get("MEM20_BLENDER_EXECUTABLE")
        if not exe:
            exe = shutil.which("blender") or "blender"
        if exe == "blender" and shutil.which("blender") is None:
            return ("Blender is an OPTIONAL integration and is not installed. Install Blender and ensure "
                    "'blender' is on PATH, or set MEM20_BLENDER_EXECUTABLE to its path, to use Blender tools.")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            path = f.name

        try:
            result = subprocess.run(
                [exe, "--background", "--python", path],
                capture_output=True, text=True, timeout=timeout
            )
            if result.returncode == 0:
                return f"Success:\n{result.stdout[-3000:]}"
            else:
                return f"Error (code {result.returncode}):\n{result.stderr[-2000:]}"
        except subprocess.TimeoutExpired:
            return f"Error: Blender timed out after {timeout}s"
        except Exception as e:
            return f"Error: {str(e)}"
        finally:
            try:
                os.unlink(path)
            except:
                pass
    def _generate_physics_script(self, concept: str) -> str:
        """Generate a physics-based Unity script using template approach."""
        template = """using UnityEngine;

namespace {concept}.Physics
{{
    public class {concept}Physics : MonoBehaviour
    {{
        [Header("{concept} Physics")]
        [SerializeField, Range(0.1f, 10f)] float forceMultiplier = 1f;
        [SerializeField, Range(0f, 5f)] float drag = 0.5f;
        [SerializeField] bool applyGravity = true;

        Rigidbody rb;

        void Awake() => rb = GetComponent<Rigidbody>();

        void FixedUpdate()
        {{
            if (!applyGravity) rb.useGravity = false;
            rb.drag = drag;
            
            // Core {concept} physics behavior
            Vector3 force = Calculate{concept}Force() * forceMultiplier;
            rb.AddForce(force, ForceMode.Acceleration);
        }}

        Vector3 Calculate{concept}Force()
        {{
            // Implement core {concept} physics
            return Vector3.up * 9.81f * forceMultiplier; // default buoyant force (tune via Inspector)
        }}

        void OnDrawGizmosSelected()
        {{
            Gizmos.color = Color.cyan;
            Gizmos.DrawWireSphere(transform.position, 2f);
        }}
    }}
}}"""
        return template.format(concept=concept.replace(' ', ''))
    def _generate_puzzle_script(self, concept: str) -> str:
        """Generate a puzzle-based Unity script using template approach."""
        template = """using UnityEngine;
using System.Collections.Generic;

namespace {concept}.Puzzle
{{
    public class {concept}Puzzle : MonoBehaviour
    {{
        [Header("{concept} Puzzle")]
        [SerializeField] List<PuzzlePiece> pieces = new();
        [SerializeField] PuzzleState targetState;

        enum PuzzleState {{ Locked, Solving, Solved }}
        PuzzleState currentState = PuzzleState.Locked;

        void Start() => InitializePuzzle();

        void InitializePuzzle()
        {{
            // Setup {concept} puzzle
            foreach (var piece in pieces)
                piece.Initialize(this);
        }}

        public void OnPieceActivated(PuzzlePiece piece)
        {{
            if (currentState == PuzzleState.Solving)
                CheckSolution();
        }}

        void CheckSolution()
        {{
            // Check if {concept} puzzle is solved
            if (IsSolved())
            {{
                currentState = PuzzleState.Solved;
                OnSolved();
            }}
        }}

        bool IsSolved() => true; // Implement {concept} logic

        void OnSolved()
        {{
            Debug.Log("{concept} puzzle solved!");
        }}
    }}

    [System.Serializable]
    public class PuzzlePiece
    {{
        public int id;
        public bool isActive;
        public void Initialize({concept}Puzzle puzzle) {{ }}
    }}
}}"""
        return template.format(concept=concept.replace(' ', ''))
    def _generate_simulation_script(self, concept: str) -> str:
        """Generate a simulation-based Unity script using template approach."""
        template = """using UnityEngine;
using System.Collections.Generic;

namespace {concept}.Simulation
{{
    public class {concept}Simulation : MonoBehaviour
    {{
        [Header("{concept} Simulation")]
        [SerializeField, Range(1, 1000)] int agentCount = 50;
        [SerializeField, Range(0.1f, 10f)] float tickRate = 1f;
        [SerializeField] bool enableVisualization = true;

        List<Agent> agents = new();
        float tickTimer;

        void Start()
        {{
            InitializeSimulation();
        }}

        void InitializeSimulation()
        {{
            for (int i = 0; i < agentCount; i++)
            {{
                var agent = new Agent();
                agent.id = i;
                agent.position = Random.insideUnitSphere * 10f;
                agent.velocity = Vector3.zero;
                agents.Add(agent);
            }}
        }}

        void Update()
        {{
            tickTimer += Time.deltaTime;
            if (tickTimer >= 1f / tickRate)
            {{
                tickTimer = 0f;
                RunSimulationTick();
            }}
        }}

        void RunSimulationTick()
        {{
            foreach (var agent in agents)
            {{
                // Apply {concept} simulation rules
                agent.velocity += CalculateForce(agent) * Time.deltaTime;
                agent.position += agent.velocity * Time.deltaTime;
            }}

            if (enableVisualization)
                UpdateVisualization();
        }}

        Vector3 CalculateForce(Agent agent)
        {{
            // Implement {concept} simulation physics
            return Vector3.up * 9.81f; // default upward force (replace with {concept}-specific dynamics)
        }}

        void UpdateVisualization()
        {{
            // Render hook: surface a frame tick so the simulation is observable
            Debug.Log("Visualization frame updated");
        }}

        void OnDrawGizmos()
        {{
            Gizmos.color = Color.green;
            foreach (var a in agents)
                Gizmos.DrawSphere(a.position, 0.1f);
        }}
    }}

    [System.Serializable]
    public class Agent {{ public int id; public Vector3 position; public Vector3 velocity; }}

    [System.Serializable]
    public class SimulationRules
    {{
        public float separationRadius = 2f;
        public float alignmentWeight = 1f;
        public float cohesionWeight = 1f;
        public void Apply(Agent agent, List<Agent> all) {{ }}
    }}
}}"""
        return template.format(concept=concept.replace(' ', ''))
    def _generate_narrative_script(self, concept: str) -> str:
        """Generate a narrative-based Unity script using template approach."""
        template = """using UnityEngine;
using System.Collections.Generic;

namespace {concept}.Narrative
{{
    public class {concept}Narrative : MonoBehaviour
    {{
        [Header("{concept} Narrative")]
        [SerializeField] StoryBeat[] beats;
        [SerializeField] int currentBeat = 0;

        [System.Serializable]
        public class StoryBeat
        {{
            public string id;
            public string text;
            public Choice[] choices;
            public string nextBeatId;
        }}

        [System.Serializable]
        public class Choice
        {{
            public string text;
            public string resultBeatId;
            public Condition[] conditions;
        }}

        [System.Serializable]
        public class Condition
        {{
            public string flag;
            public bool required;
        }}

        void Start() => PlayBeat(beats[0].id);

        public void PlayBeat(string beatId)
        {{
            StoryBeat beat = System.Array.Find(beats, b => b.id == beatId);
            if (beat == null) return;

            currentBeat = System.Array.IndexOf(beats, beat);
            Debug.Log($"<b>{{beat.id}}</b>: {{beat.text}}");

            // Display choices for {concept}
            foreach (var choice in beat.choices)
                Debug.Log($"  > {{choice.text}}");
        }}

        public void MakeChoice(int choiceIndex)
        {{
            StoryBeat beat = beats[currentBeat];
            if (choiceIndex >= beat.choices.Length) return;

            var choice = beat.choices[choiceIndex];
            if (CheckConditions(choice.conditions))
                PlayBeat(choice.resultBeatId);
        }}

        bool CheckConditions(Condition[] conditions)
        {{
            // Check {concept} narrative conditions
            return true;
        }}
    }}
}}"""
        return template.format(concept=concept.replace(' ', ''))
    def _generate_ai_agent_script(self, concept: str) -> str:
        """Generate an AI agent Unity script using template approach."""
        template = """using UnityEngine;
using System.Collections.Generic;

namespace {concept}.AI
{{
    public class {concept}AIAgent : MonoBehaviour
    {{
        [Header("{concept} AI Agent")]
        [SerializeField] BehaviorTree behaviorTree;
        [SerializeField] Blackboard blackboard;
        [SerializeField] Sensor[] sensors;
        [SerializeField] Actuator[] actuators;

        void Awake()
        {{
            blackboard = new Blackboard();
            foreach (var s in sensors) s.Initialize(this);
            foreach (var a in actuators) a.Initialize(this);
        }}

        void Update()
        {{
            // Perceive
            foreach (var s in sensors) s.Sense(blackboard);

            // Decide
            if (behaviorTree != null)
                behaviorTree.Tick(blackboard);

            // Act
            foreach (var a in actuators) a.Act(blackboard);
        }}
    }}

    [System.Serializable]
    public class Blackboard
    {{
        Dictionary<string, object> data = new();
        public void Set(string key, object value) => data[key] = value;
        public T Get<T>(string key) => data.TryGetValue(key, out var v) ? (T)v : default;
    }}

    [System.Serializable]
    public abstract class Sensor
    {{
        public abstract void Initialize({concept}AIAgent agent);
        public abstract void Sense(Blackboard blackboard);
    }}

    [System.Serializable]
    public abstract class Actuator
    {{
        public abstract void Initialize({concept}AIAgent agent);
        public abstract void Act(Blackboard blackboard);
    }}

    [System.Serializable]
    public class BehaviorTree
    {{
        public Node root;
        public void Tick(Blackboard blackboard) => root?.Execute(blackboard);
    }}

    [System.Serializable]
    public abstract class Node
    {{
        public abstract NodeStatus Execute(Blackboard blackboard);
    }}

    public enum NodeStatus {{ Running, Success, Failure }}
}}"""
        return template.format(concept=concept.replace(' ', ''))
    def _refresh_audit(self) -> None:
        """Cache engine contamination/grounding audit for 30s (Step 16 §1)."""
        now = time.time()
        if self._audit_cache is not None and now - self._audit_cache_ts < 30:
            return
        if _ENGINE_AUDIT is None:
            self._audit_cache = {"available": False}
        else:
            try:
                a = dict(_ENGINE_AUDIT())
                g = a.get("grounded_facts", 0) or 0
                s = a.get("simulated_facts", 0) or 0
                a["grounding_coverage"] = (g / (g + s)) if (g + s) else None
                self._audit_cache = a
            except Exception:
                self._audit_cache = {"available": False, "error": True}
        self._audit_cache_ts = now

    def metrics(self) -> Dict[str, Any]:
        """Operational metrics for the /metrics endpoint (event taxonomy + counters)."""
        m = {
            "service": "mem20-mcp",
            "uptime_seconds": round(time.time() - self._start_time, 3),
            "tools_registered": len(self.tools),
            "request_count": self._request_count,
            "request_errors": self._request_errors,
            "memory_system_available": MEMORY_SYSTEM_AVAILABLE,
            "event_taxonomy": self._event_taxonomy,
            "tool_calls": self._tool_calls,
            "tool_errors": self._tool_errors,
            "tool_calls_total": sum(self._tool_calls.values()),
            "tool_errors_total": sum(self._tool_errors.values()),
            "contamination_rate": None,
            "grounding_coverage": None,
            "grounded_facts": None,
            "simulated_facts": None,
            "engine_audit_available": None,
        }
        if MEMORY_SYSTEM_AVAILABLE and _ENGINE_AUDIT is not None:
            self._refresh_audit()
            audit = self._audit_cache or {}
            m["contamination_rate"] = audit.get("contamination_rate")
            m["grounding_coverage"] = audit.get("grounding_coverage")
            m["grounded_facts"] = audit.get("grounded_facts")
            m["simulated_facts"] = audit.get("simulated_facts")
            m["engine_audit_available"] = audit.get("available", True)
        return m

    def run(self):
        """Start the MCP server."""
        import anyio
        from mcp.server.stdio import stdio_server

        logging.basicConfig(
            level=os.environ.get("MEM20_LOG_LEVEL", "INFO").upper(),
            format='%(asctime)s %(levelname)s %(name)s %(message)s',
        )

        # Operational HTTP endpoint (non-blocking; failures are non-fatal).
        port = int(os.environ.get("MEM20_HEALTH_PORT", "8080"))
        if os.environ.get("MEM20_HEALTH_DISABLE") not in ("1", "true", "yes"):
            start_health_server(self, port)

        async def main():
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options()
                )
        
        anyio.run(main)


def main():
    server = Mem20MCPServer()
    server.run()


if __name__ == "__main__":
    main()