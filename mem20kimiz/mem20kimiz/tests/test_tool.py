"""Hermetic tests for the mem20kimiz AgentSwarm tool contract."""

import unittest

from mem20kimiz.tool import AgentSwarmError, AgentSwarmTool, AgentSwarmSpecs


class AgentSwarmToolValidationTests(unittest.TestCase):
    def make(self, **kw) -> AgentSwarmTool:
        base = dict(
            description="d",
            subagent_type="coder",
            prompt_template="handle {{item}}",
            items=["a", "b"],
        )
        base.update(kw)
        return AgentSwarmTool(**base)

    def test_requires_at_least_two_items_without_resume(self):
        tool = self.make(items=["a"])
        with self.assertRaises(AgentSwarmError):
            tool.validate_specs()
        tool = self.make(items=[])
        with self.assertRaises(AgentSwarmError):
            tool.validate_specs()

    def test_resume_only_allows_single_resume(self):
        tool = self.make(items=[], resume_agent_ids={"aid1": "continue one"}, prompt_template=None)
        specs = tool.validate_specs(get_resume_item=lambda aid: "x")
        self.assertEqual(specs.total, 1)
        self.assertEqual(specs.resume[0].agentId, "aid1")

    def test_prompt_template_required_for_items(self):
        tool = self.make(prompt_template=None)
        with self.assertRaises(AgentSwarmError):
            tool.validate_specs()

    def test_template_must_contain_placeholder(self):
        tool = self.make(prompt_template="no placeholder here")
        with self.assertRaises(AgentSwarmError):
            tool.validate_specs()

    def test_cap_at_128(self):
        items = [f"item{i}" for i in range(129)]
        tool = self.make(items=items)
        with self.assertRaises(AgentSwarmError):
            tool.validate_specs()

    def test_duplicate_prompts_rejected(self):
        tool = self.make(prompt_template="t {{item}}", items=["x", "x"])
        with self.assertRaises(AgentSwarmError):
            tool.validate_specs()

    def test_fork_requires_items_and_no_resume(self):
        tool = self.make(fork=True, items=["a"], resume_agent_ids={"k": "p"})
        with self.assertRaises(AgentSwarmError):
            tool.validate_specs()
        tool = self.make(fork=True, items=[])
        with self.assertRaises(AgentSwarmError):
            tool.validate_specs()
        tool = self.make(fork=True, items=["a", "b"])
        specs = tool.validate_specs()
        self.assertEqual(specs.total, 2)

    def test_distinct_prompts_accepted_and_items_stripped(self):
        tool = self.make(items=[" one ", "", " two "])
        specs = tool.validate_specs()
        self.assertEqual([s.item for s in specs.spawn if s.kind == "spawn"], ["one", "two"])

    def test_resume_predates_spawn_in_order(self):
        tool = self.make(resume_agent_ids={"aid9": "resume me"}, prompt_template="t {{item}}")
        specs = tool.validate_specs(get_resume_item=lambda aid: "item0")
        self.assertTrue(specs.total >= 3)
        self.assertEqual(specs.resume[0].index, 1)
        self.assertEqual([s.kind for s in specs.spawn], ["spawn", "spawn"])

    def test_spawn_and_resume_total_is_spawn_plus_resume(self):
        tool = self.make(resume_agent_ids={"aid1": "r1", "aid2": "r2"})
        specs = tool.validate_specs()
        self.assertEqual(specs.total, 4)


class AgentSwarmRenderingTests(unittest.TestCase):
    def setUp(self):
        self.tool = AgentSwarmTool(
            description="go",
            subagent_type="coder",
            prompt_template="t {{item}}",
            items=["a", "b"],
        )

    def _specs_and_results(self):
        from mem20kimiz.types import SessionSwarmRunResult

        specs = self.tool.validate_specs()
        results = [
            SessionSwarmRunResult(task=None, agentId="sa1", status="completed", state="started", result="hi", stopReason=None),
            SessionSwarmRunResult(task=None, agentId="sa2", status="failed", state="started", error="boom", stopReason=None),
        ]
        return specs, results

    def test_render_ordered_xml_with_summary(self):
        specs, results = self._specs_and_results()
        xml = self.tool.render_results(results, specs)
        self.assertIn("<agent_swarm_result>", xml)
        self.assertIn("<summary>completed: 1, failed: 1</summary>", xml)
        self.assertIn('agent_id="sa1" item="a" state="started" outcome="completed"', xml)
        self.assertIn('agent_id="sa2" item="b" state="started" outcome="failed"', xml)
        self.assertTrue(xml.index('item="a"') < xml.index('item="b"'))

    def test_resume_hint_when_incomplete_with_agent_id(self):
        specs, results = self._specs_and_results()
        xml = self.tool.render_results(results, specs)
        self.assertTrue(xml.startswith("<agent_swarm_result>"), xml)
        self.assertIn("resume_agent_ids", xml)

    def test_no_resume_hint_when_all_completed(self):
        from mem20kimiz.types import SessionSwarmRunResult

        specs = self.tool.validate_specs()
        results = [
            SessionSwarmRunResult(task=None, agentId="sa1", status="completed", state="started", result="ok", stopReason=None),
            SessionSwarmRunResult(task=None, agentId="sa2", status="completed", state="started", result="ok", stopReason=None),
        ]
        xml = self.tool.render_results(results, specs)
        self.assertNotIn("resume_hint", xml)

    def test_xml_escaping(self):
        from mem20kimiz.types import SessionSwarmRunResult

        specs = self.tool.validate_specs()
        results = [
            SessionSwarmRunResult(task=None, agentId="a<&\"", status="completed", state="started", result='r <&" >', stopReason=None),
            SessionSwarmRunResult(task=None, agentId="sa2", status="completed", state="started", result="ok", stopReason=None),
        ]
        xml = self.tool.render_results(results, specs)
        self.assertIn("&lt;", xml)
        self.assertIn("&amp;", xml)

    def test_to_tasks_ordering_and_swarm_item(self):
        tasks = self.tool.to_tasks(caller_agent_id="coord", parent_tool_call_id="swarm_1", spec_source=self.tool.validate_specs())
        self.assertEqual([t.kind for t in tasks], ["spawn", "spawn"])
        self.assertEqual([t.swarmIndex for t in tasks], [1, 2])
        self.assertEqual([t.swarmItem for t in tasks], ["a", "b"])
        self.assertEqual([t.parentToolCallId for t in tasks], ["swarm_1"] * 2)


class AgentSwarmSpecHygieneTests(unittest.TestCase):
    def test_specs_dataclass_defaults(self):
        specs = AgentSwarmSpecs()
        self.assertEqual(specs.total, 0)


if __name__ == "__main__":
    unittest.main()