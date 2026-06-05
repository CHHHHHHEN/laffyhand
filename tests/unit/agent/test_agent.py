from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from laffyhand.core.agent import AgentInfo, AgentRegistry, get_builtin
from laffyhand.core.agent.agent import _load_agent_file


class TestAgentInfo(TestCase):
    def test_default_mode_is_subagent(self):
        info = AgentInfo(name="test", system_prompt="")
        self.assertEqual(info.mode, "subagent")

    def test_default_max_steps(self):
        info = AgentInfo(name="test", system_prompt="")
        self.assertEqual(info.max_steps, 50)

    def test_default_hidden(self):
        info = AgentInfo(name="test", system_prompt="")
        self.assertFalse(info.hidden)

    def test_default_description(self):
        info = AgentInfo(name="test", system_prompt="")
        self.assertEqual(info.description, "")

    def test_default_permission(self):
        info = AgentInfo(name="test", system_prompt="")
        self.assertEqual(info.permission, {})

    def test_optional_fields(self):
        info = AgentInfo(
            name="test",
            system_prompt="You are a test agent",
            model="gpt-4",
            temperature=0.5,
            top_p=0.9,
            hidden=True,
        )
        self.assertEqual(info.model, "gpt-4")
        self.assertEqual(info.system_prompt, "You are a test agent")
        self.assertEqual(info.temperature, 0.5)
        self.assertEqual(info.top_p, 0.9)
        self.assertTrue(info.hidden)


class TestBuiltinAgents(TestCase):
    def setUp(self):
        self.registry = AgentRegistry()

    def test_build_agent_exists(self):
        self.assertIsNotNone(self.registry.get("build"))

    def test_build_agent_is_primary(self):
        self.assertEqual(self.registry.get("build").mode, "primary")

    def test_plan_agent_hidden(self):
        self.assertTrue(self.registry.get("plan").hidden)

    def test_plan_agent_denies_edit_tools(self):
        self.assertIn("write", self.registry.get("plan").permission.get("deny", []))

    def test_explore_agent_denies_write(self):
        self.assertIn("write", self.registry.get("explore").permission.get("deny", []))

    def test_compaction_agent_hidden(self):
        self.assertTrue(self.registry.get("compaction").hidden)

    def test_title_agent_hidden(self):
        self.assertTrue(self.registry.get("title").hidden)

    def test_general_agent_mode(self):
        self.assertEqual(self.registry.get("general").mode, "subagent")

    def test_get_builtin_returns_agent(self):
        info = get_builtin("build")
        self.assertIsNotNone(info)
        self.assertEqual(info.mode, "primary")

    def test_get_builtin_returns_none_for_unknown(self):
        self.assertIsNone(get_builtin("nonexistent"))


class TestAgentRegistry(TestCase):
    def setUp(self):
        self.registry = AgentRegistry()

    def test_init_loads_builtin_agents(self):
        for name in ("build", "plan", "general", "explore", "compaction", "title"):
            self.assertIsNotNone(self.registry.get(name))

    def test_register(self):
        info = AgentInfo(name="custom", system_prompt="")
        self.registry.register(info)
        self.assertIs(self.registry.get("custom"), info)

    def test_register_overwrites(self):
        a = AgentInfo(name="x", system_prompt="")
        b = AgentInfo(name="x", system_prompt="", description="new")
        self.registry.register(a)
        self.registry.register(b)
        self.assertEqual(self.registry.get("x").description, "new")

    def test_get_returns_none_for_unknown(self):
        self.assertIsNone(self.registry.get("nonexistent"))

    def test_list_subagents_only(self):
        agents = self.registry.list_subagents()
        for a in agents:
            self.assertIn(a.mode, ("subagent", "all"))

    def test_list_by_mode_primary(self):
        agents = self.registry.list_by_mode("primary")
        for a in agents:
            self.assertIn(a.mode, ("primary", "all"))

    def test_list_visible_excludes_hidden(self):
        visible = self.registry.list_visible()
        for a in visible:
            self.assertFalse(a.hidden)

    def test_list_visible_does_not_include_hidden_builtins(self):
        hidden_names = {"plan", "compaction", "title"}
        visible_names = {a.name for a in self.registry.list_visible()}
        self.assertTrue(hidden_names.isdisjoint(visible_names))

    def test_all_returns_copy(self):
        result = self.registry.all()
        result["new"] = AgentInfo(name="new", system_prompt="")
        self.assertIsNone(self.registry.get("new"))

    def test_discover_skips_nonexistent_dir(self):
        self.registry.discover(["/nonexistent/path"])
        visible = self.registry.list_visible()
        self.assertGreater(len(visible), 0)

    def test_discover_skips_non_dir_path(self):
        with tempfile.NamedTemporaryFile(suffix=".md") as f:
            self.registry.discover([f.name])
        visible = self.registry.list_visible()
        self.assertGreater(len(visible), 0)


class TestLoadAgentFile(TestCase):
    def test_missing_file_returns_none(self):
        result = _load_agent_file(Path("/nonexistent/agent.agent.md"))
        self.assertIsNone(result)

    def test_no_front_matter_returns_none(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("Just content without front matter")
            path = Path(f.name)
        try:
            result = _load_agent_file(path)
            self.assertIsNone(result)
        finally:
            path.unlink()

    def test_missing_closing_delimiter_returns_none(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("---\nname: test\n")
            path = Path(f.name)
        try:
            result = _load_agent_file(path)
            self.assertIsNone(result)
        finally:
            path.unlink()

    def test_bad_yaml_returns_none(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("---\nname: test\nbroken: [\n---\nbody")
            path = Path(f.name)
        try:
            result = _load_agent_file(path)
            self.assertIsNone(result)
        finally:
            path.unlink()

    def test_non_dict_yaml_returns_none(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("---\n- list\n- not\n- dict\n---\nbody")
            path = Path(f.name)
        try:
            result = _load_agent_file(path)
            self.assertIsNone(result)
        finally:
            path.unlink()

    def test_loads_basic_agent(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(
                "---\nname: my-agent\ndescription: My custom agent\n---\nYou are my agent."
            )
            path = Path(f.name)
        try:
            info = _load_agent_file(path)
            self.assertIsNotNone(info)
            self.assertEqual(info.name, "my-agent")
            self.assertEqual(info.description, "My custom agent")
            self.assertEqual(info.system_prompt, "You are my agent.")
        finally:
            path.unlink()

    def test_loads_agent_md_without_front_matter_prompt(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".agent.md", delete=False
        ) as f:
            f.write("---\nname: code\n---\nYou are a code agent.")
            path = Path(f.name)
        try:
            info = _load_agent_file(path)
            self.assertIsNotNone(info)
            self.assertEqual(info.name, "code")
            self.assertEqual(info.system_prompt, "You are a code agent.")
        finally:
            path.unlink()

    def test_loads_agent_with_permission(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(
                "---\nname: reader\npermission:\n  deny: [write, edit]\n---\nRead only."
            )
            path = Path(f.name)
        try:
            info = _load_agent_file(path)
            self.assertIsNotNone(info)
            self.assertEqual(info.permission.get("deny"), ["write", "edit"])
        finally:
            path.unlink()

    def test_loads_agent_with_all_fields(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(
                "---\n"
                "name: pro\n"
                "description: Pro agent\n"
                "mode: primary\n"
                "model: gpt-4\n"
                "max_steps: 100\n"
                "temperature: 0.7\n"
                "top_p: 0.9\n"
                "hidden: true\n"
                "options:\n"
                "  flag: true\n"
                "---\n"
                "You are pro."
            )
            path = Path(f.name)
        try:
            info = _load_agent_file(path)
            self.assertIsNotNone(info)
            self.assertEqual(info.name, "pro")
            self.assertEqual(info.description, "Pro agent")
            self.assertEqual(info.mode, "primary")
            self.assertEqual(info.model, "gpt-4")
            self.assertEqual(info.max_steps, 100)
            self.assertEqual(info.temperature, 0.7)
            self.assertEqual(info.top_p, 0.9)
            self.assertTrue(info.hidden)
            self.assertEqual(info.options, {"flag": True})
        finally:
            path.unlink()

    def test_uses_filename_stem_when_no_name_in_meta(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".agent.md", delete=False
        ) as f:
            f.write("---\ndescription: no name here\n---\nbody")
            stem = Path(f.name).stem
        path = Path(f.name)
        try:
            info = _load_agent_file(path)
            self.assertIsNotNone(info)
            self.assertEqual(info.name, stem)
        finally:
            path.unlink()
