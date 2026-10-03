# skill-zh

[中文](README.md) · [Changelog](CHANGELOG.md)

A Claude Code plugin that puts a Chinese summary in front of English skill descriptions whenever skills are installed or updated, so the skill menu reads in Chinese.

```text
Before: Diagnosis loop for hard bugs and performance regressions. Use when the user says "diagnose"/"debug this" ...
After:  疑难 bug 和性能问题的诊断循环。用于用户要求诊断问题或报告功能异常、报错、失败或性能低下。 ｜ EN: Diagnosis loop for hard bugs and performance regressions. Use when the user says "diagnose"/"debug this" ...
```

The original English is kept verbatim, so when a skill triggers doesn't change.

## Install

```text
/plugin marketplace add windery/skill-zh
/plugin install skill-zh@skill-zh
```

Start a new session afterwards. Existing English descriptions are translated in the background and show up from the following session.

## Requirements

- macOS or Linux
- Python 3.8+ available as `python3`
- Claude Code, logged in, with `claude` on `PATH`
- Optional: PyYAML for stricter SKILL.md parsing; a built-in fallback parser is used otherwise

## Usage

Translation runs on its own at session start, and after Claude runs a command that looks like it installs or updates skills (`npx skills add`, copying into a `skills/` directory, ...).

Three user-invoked commands are available. Claude never invokes them on its own and they add nothing to the context:

| Command | What it does |
| --- | --- |
| `/skill-zh:status` | Show each skill's state: translated, pending, already Chinese |
| `/skill-zh:translate` | Translate pending descriptions now |
| `/skill-zh:restore` | Put every original English description back |

## Configuration

Edit the two skill-zh rows in `/config`, or run `/plugin configure skill-zh@skill-zh`. Restart Claude Code to apply.

| Option | Default | Meaning |
| --- | --- | --- |
| `model` | `haiku` | Model used for `claude -p` translation calls |
| `exclude` | empty | Comma-separated skill folder names to leave alone, e.g. `ego-browser,agent-reach` |

## How it works

1. **Hooks.** `SessionStart` and `PostToolUse` (Bash) hooks run `async`, so they never block the session. A Bash command only matters if it looks like a skill install or update.
2. **Scan.** Each `SKILL.md` description is classified as translated (contains ` ｜ EN: `), already Chinese (at least as many Chinese characters as English words), or pending.
3. **Detached run.** Pending work runs in a process of its own session. Claude Code cancels async hooks still running when a session ends (`--debug` logs `Hook SessionStart:startup ... cancelled`), which would kill a translation halfway through a short `claude -p` session.
4. **Translate.** `claude -p --model haiku` with the user's own login, 15 descriptions per call, JSON in and out. The child session loads no settings sources and gets no tools, so it has no plugins or hooks and can't trigger itself.
5. **Rewrite.** Only `description` changes, to a single line `<Chinese> ｜ EN: <original>`. Every other byte of the file is kept, and the result is re-parsed and compared before it is written.
6. **Length guard.** Codex and the Agent Skills spec cap descriptions at 1024 characters, and an over-long one stops the skill from loading. The Chinese part is truncated to fit; if the original alone is too long, the skill is skipped.
7. **Backups and locking.** The original file is saved to `~/.claude/skill-zh/originals/` before writing. A file lock keeps concurrent sessions from translating at the same time.

When a skill update overwrites the description, the next session translates it again.

**Why not replace the description?** It is both the menu text and what the model reads to decide when to use the skill; there is no separate display field. Replacing it would drop the author's English trigger phrases.

## Managed directories

`~/.agents/skills`, `~/.claude/skills` (follows `CLAUDE_CONFIG_DIR`), `~/.codex/skills` (follows `CODEX_HOME`, excluding `.system`), `~/.config/opencode/skills`, `~/.cursor/skills`, `~/.gemini/skills`.

Project-level skill directories, skills synced from claude.ai and plugin-bundled skills are never touched. Skills symlinked from several roots are written once, through their real path.

## Privacy and data handling

- Only skill descriptions are sent to Claude, using your own Claude Code login and quota.
- Backups and the log live in `~/.claude/skill-zh/` (under `CLAUDE_CONFIG_DIR` when set), created owner-only. The directory survives uninstalling, so you can still restore afterwards.

## Limitations

- Only Claude Code has hooks. Skills installed from Codex or a terminal are picked up at the next Claude Code session, or by `/skill-zh:translate`.
- New descriptions show from the next session.
- Windows is not supported.

## Troubleshooting

- **Nothing happens:** run `/skill-zh:status`, then read `~/.claude/skill-zh/log.txt`.
- **"翻译调用失败" in the log:** check that `claude -p "hi"` works in a terminal.
- **"改写后校验没通过" for a skill:** its frontmatter is unusual and was left alone on purpose. Please open an issue with that SKILL.md.
- **Uninstall:** run `/skill-zh:restore`, then `claude plugin uninstall skill-zh@skill-zh`.

## Development

```bash
pip install pytest pyyaml ruff
pytest                       # temp dirs and a fake translator only; never touches your skills or calls Claude
ruff check . && ruff format --check .
claude plugin validate . --strict
claude --plugin-dir .        # try the plugin without installing it
```

`python3 skill_zh status` runs the core from a checkout. Point it elsewhere with `SKILL_ZH_SKILL_DIRS` (`:`-separated skill roots) and `SKILL_ZH_STATE_DIR`.

## License

[MIT](LICENSE)
