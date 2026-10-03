import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import skill_zh as z  # noqa: E402

try:
    import yaml  # noqa: F401
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

BODY = "\n# Title\n\nBody line with description: not a key\n"

VARIANTS = {
    "plain": "---\nname: a\ndescription: Do the thing. Use when asked.\n---" + BODY,
    "double": '---\nname: a\ndescription: "Do the thing: now. Use when asked."\n---' + BODY,
    "single": "---\nname: a\ndescription: 'Don''t stop. Use when asked.'\n---" + BODY,
    "folded": "---\nname: a\ndescription: >\n  Do the thing.\n  Use when asked.\nmetadata:\n  k: v\n---" + BODY,
    "literal": "---\nname: a\ndescription: |\n  Do the thing.\n  Use when asked.\nlicense: MIT\n---" + BODY,
    "multiline": "---\nname: a\ndescription: Do the thing.\n  Use when asked.\ndisable-model-invocation: true\n---" + BODY,
    "crlf": "---\r\nname: a\r\ndescription: Do the thing. Use when asked.\r\n---\r\n# Title\r\n",
}


class NoYaml:
    """让 `import yaml` 失败，走简易解析。"""

    def __enter__(self):
        self.saved = sys.modules.get("yaml")
        sys.modules["yaml"] = None

    def __exit__(self, *exc):
        if self.saved is None:
            sys.modules.pop("yaml", None)
        else:
            sys.modules["yaml"] = self.saved


def body(text):
    return text.split("---", 2)[2]


class FrontmatterTest(unittest.TestCase):
    def check_variants(self):
        for kind, text in VARIANTS.items():
            with self.subTest(kind=kind):
                desc = z.get_desc(text)
                self.assertTrue(desc and desc.startswith(("Do", "Don't")), desc)
                self.assertIn("Use when asked.", desc)
                new = "中文说明" + z.SEP + " ".join(desc.split())
                out = z.set_desc(text, new)
                self.assertIsNotNone(out)
                self.assertEqual(z.get_desc(out), new)
                self.assertEqual(body(out), body(text))

    @unittest.skipUnless(HAS_YAML, "需要 PyYAML")
    def test_variants_with_yaml(self):
        self.check_variants()

    def test_variants_without_yaml(self):
        with NoYaml():
            self.check_variants()

    @unittest.skipUnless(HAS_YAML, "需要 PyYAML")
    def test_other_fields_untouched(self):
        import yaml
        text = VARIANTS["folded"]
        out = z.set_desc(text, "新简介 ｜ EN: x")
        old = yaml.safe_load(text.split("---")[1])
        new = yaml.safe_load(out.split("---")[1])
        old.pop("description")
        new.pop("description")
        self.assertEqual(old, new)

    def test_no_frontmatter_or_description(self):
        self.assertIsNone(z.get_desc("# just markdown\n"))
        self.assertIsNone(z.set_desc("# just markdown\n", "x"))
        self.assertIsNone(z.set_desc("---\nname: a\n---\nbody\n", "x"))

    def test_quotes_and_backslashes_survive(self):
        text = VARIANTS["plain"]
        new = '中文 "引号" 和 \\ 反斜杠 ｜ EN: say "hi"'
        self.assertEqual(z.get_desc(z.set_desc(text, new)), new)


class HelpersTest(unittest.TestCase):
    def test_mostly_zh(self):
        self.assertTrue(z.mostly_zh("把当前会话总结并存到飞书知识库。当用户说「总结会话」时使用。"))
        self.assertTrue(z.mostly_zh("阅读当前项目或指定 GitHub 仓库的代码，生成文档"))
        self.assertFalse(z.mostly_zh('Use ChatGPT as the planning brain. Use when the user says "用 ChatGPT 规划".'))
        self.assertFalse(z.mostly_zh("Diagnose hard bugs."))

    def test_compose_fits_limit(self):
        self.assertEqual(z.compose("中文", "a  b\n c"), "中文" + z.SEP + "a b c")
        en = "x" * 1000
        out = z.compose("长" * 100, en)
        self.assertEqual(len(out), z.MAX_LEN)
        self.assertTrue(out.endswith(z.SEP + en))
        self.assertIn("…", out)
        self.assertIsNone(z.compose("中文", "x" * 1010))

    def test_install_cmd(self):
        hits = ["npx skills add owner/repo -g", "npx skills update", "bunx skills install x",
                "cp -r foo ~/.agents/skills/", "git clone https://x/y ~/.claude/skills/y"]
        misses = ["ls -la", "git status", "npm install", "python3 run.py --update"]
        for c in hits:
            self.assertTrue(z.INSTALL_CMD.search(c), c)
        for c in misses:
            self.assertFalse(z.INSTALL_CMD.search(c), c)


class CommandsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.skills = os.path.join(self.tmp, "skills")
        self.state = os.path.join(self.tmp, "state")
        self.env = mock.patch.dict(os.environ, {"SKILL_ZH_DIRS": self.skills, "SKILL_ZH_STATE": self.state})
        self.env.start()
        os.environ.pop("SKILL_ZH_CHILD", None)
        self.add("alpha", VARIANTS["folded"])
        self.add("beta", VARIANTS["double"])
        self.add("gamma", "---\nname: gamma\ndescription: 把会话存到飞书知识库。\n---\nbody\n")

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp)

    def add(self, name, text):
        os.makedirs(os.path.join(self.skills, name), exist_ok=True)
        with open(self.path(name), "w", encoding="utf-8") as f:
            f.write(text)

    def path(self, name):
        return os.path.join(self.skills, name, "SKILL.md")

    def read(self, name):
        with open(self.path(name), encoding="utf-8") as f:
            return f.read()

    def states(self):
        return {name: state for name, state, _ in z.scan()[1]}

    def fake_translate(self, items):
        return {k: "中文说明" for k in items}

    def test_run_then_restore(self):
        before = {n: self.read(n) for n in ("alpha", "beta", "gamma")}
        self.assertEqual(self.states(), {"alpha": "待翻译", "beta": "待翻译", "gamma": "本来就是中文"})
        with mock.patch.object(z, "translate", self.fake_translate):
            z.cmd_run(quiet=True)
        self.assertEqual(self.states(), {"alpha": "已汉化", "beta": "已汉化", "gamma": "本来就是中文"})
        self.assertTrue(z.get_desc(self.read("alpha")).startswith("中文说明" + z.SEP + "Do the thing."))
        self.assertEqual(self.read("gamma"), before["gamma"])
        self.assertFalse(os.path.exists(os.path.join(self.state, "lock")))

        with mock.patch("sys.stdout", io.StringIO()):
            z.cmd_restore()
        for n in ("alpha", "beta"):
            self.assertEqual(z.get_desc(self.read(n)), z.get_desc(before[n]))
            self.assertEqual(body(self.read(n)), body(before[n]))

    def test_failed_translation_leaves_files(self):
        before = self.read("alpha")
        with mock.patch.object(z, "translate", lambda items: {}):
            z.cmd_run(quiet=True)
        self.assertEqual(self.read("alpha"), before)
        self.assertEqual(self.states()["alpha"], "待翻译")

    def test_symlinked_skill_counted_once(self):
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        os.symlink(os.path.join(self.skills, "alpha"), os.path.join(other, "alpha"))
        os.environ["SKILL_ZH_DIRS"] = os.pathsep.join([self.skills, other])
        names = [n for n, _ in z.skill_files()]
        self.assertEqual(names.count("alpha"), 1)

    def test_exclude_config(self):
        os.makedirs(self.state)
        with open(os.path.join(self.state, "config.json"), "w") as f:
            json.dump({"exclude": ["beta"]}, f)
        self.assertNotIn("beta", self.states())

    def test_busy_lock_skips_run(self):
        os.makedirs(os.path.join(self.state, "lock"))
        with mock.patch.object(z, "translate", self.fake_translate):
            z.cmd_run(quiet=True)
        self.assertEqual(self.states()["alpha"], "待翻译")

    def hook(self, payload):
        with mock.patch.object(z.subprocess, "Popen") as popen:
            z.cmd_hook(io.StringIO(json.dumps(payload)))
        return popen.called

    def test_hook_spawns_on_session_start(self):
        self.assertTrue(self.hook({"hook_event_name": "SessionStart"}))

    def test_hook_filters_bash_commands(self):
        bash = {"hook_event_name": "PostToolUse", "tool_name": "Bash"}
        self.assertFalse(self.hook(dict(bash, tool_input={"command": "ls -la"})))
        self.assertTrue(self.hook(dict(bash, tool_input={"command": "npx skills add a/b -g"})))

    def test_hook_quiet_when_nothing_to_do(self):
        shutil.rmtree(os.path.join(self.skills, "alpha"))
        shutil.rmtree(os.path.join(self.skills, "beta"))
        self.assertFalse(self.hook({"hook_event_name": "SessionStart"}))

    def test_hook_ignored_in_child_process(self):
        os.environ["SKILL_ZH_CHILD"] = "1"
        self.assertFalse(self.hook({"hook_event_name": "SessionStart"}))


if __name__ == "__main__":
    unittest.main()
