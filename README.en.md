# skill-zh

[中文](README.md) · [Changelog](CHANGELOG.md)

A Claude Code plugin that translates English skill descriptions into Chinese, in full, whenever skills are installed or updated, so the skill menu reads in Chinese.

```text
Before: Diagnosis loop for hard bugs and performance regressions. Use when the user says "diagnose"/"debug this" ...
After:  用于诊断困难的 bug 和性能回归的诊断流程。在用户说 "diagnose"/"debug this"、或报告某些东西已损坏/抛出异常/失败/运行缓慢时使用。
```

It is a complete translation, not a summary: every "use when" condition stays, and quoted trigger phrases, commands and names are kept verbatim, so skills keep triggering as before. The English original is backed up locally and can be restored at any time.

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
| `/skill-zh:status` | Show each skill's state: translated, pending, already Chinese, no description |
| `/skill-zh:translate` | Translate pending descriptions now |
| `/skill-zh:restore` | Put every original English description back |

## Configuration

Edit the two skill-zh rows in `/config`, or run `/plugin configure skill-zh@skill-zh`. Restart Claude Code to apply.

Opus is the default because it measured best: with the same prompt on 30 real descriptions, scored by the same review agents, Haiku left 8 skills with mistranslated terms or altered trigger conditions (`CI secrets` → 秘密, `cutover` → 转换, `agent` → 代理), Sonnet and Opus left none, and Opus read best. Only new or updated skills are translated, 30 take about a minute, so the cost difference is negligible.

| Option | Default | Meaning |
| --- | --- | --- |
| `model` | `opus` | Model used for `claude -p` translation calls; set `sonnet` to save quota |
| `exclude` | empty | Comma-separated skill folder names to leave alone, e.g. `ego-browser,agent-reach` |

## How it works

1. **Hooks.** `SessionStart` and `PostToolUse` (Bash) hooks run `async`, so they never block the session. A Bash command only matters if it looks like a skill install or update.
2. **Scan.** Each `SKILL.md` description is classified as translated, already Chinese (at least as many Chinese characters as English words), or pending; a file whose description can't be read is reported as having none. "Translated" means the description still equals the translation we recorded when writing it: a skill updated upstream (English again) is translated again. One you edited by hand into Chinese counts as yours and is never overwritten or restored; an edit back to English is indistinguishable from an upstream update and gets translated again.
3. **Detached run.** Pending work runs in a process of its own session. Claude Code cancels async hooks still running when a session ends (`--debug` logs `Hook SessionStart:startup ... cancelled`), which would kill a translation halfway through a short `claude -p` session.
4. **Translate.** `claude -p --model opus` with the user's own login, 10 descriptions per call, asking for complete translations that keep quoted trigger phrases. The prompt carries a glossary of standard Chinese terms (secrets → 密钥, cutover → 切换) and a list of developer words to keep in English (agent, issue, PR, spec, ...), added after reviewing 30 real translations. Only the descriptions go out, keyed by index; skill names and paths are never sent. Replies come back as plain text under `@@@ <key>` markers rather than JSON, because models routinely leave the quotes in those phrases unescaped. A reply that isn't mostly Chinese (a refusal, a half-translated text) is rejected and retried next time. The child session loads no settings sources and gets no tools, so it has no plugins or hooks and can't trigger itself.
5. **Rewrite.** Only `description` changes, to the Chinese translation on a single line. The file is re-read right before writing; if it changed while the translation ran, this round is skipped and the new content is translated next time. The result is re-parsed and compared before it is written: the description must equal the new value and every other top-level field must be unchanged line by line (without PyYAML that text-level check is all there is).
6. **Length guard.** Codex and the Agent Skills spec cap descriptions at 1024 characters, and an over-long one stops the skill from loading. A translation over the cap is not written.
7. **Backups and locking.** The original file and the translation written are recorded in `~/.claude/skill-zh/originals/` before writing. A file lock keeps concurrent sessions from translating at the same time; a run that doesn't get the lock gives up rather than queueing, and its work stays pending for the next session.

When a skill update overwrites the description, the next session translates it again.

**Why a complete translation, not a summary?** The description is both the menu text and what the model reads to decide when to use the skill; there is no separate display field. A summary would drop the author's conditions and trigger phrases. A complete translation that keeps quoted phrases verbatim serves both readers.

0.1 and 0.2 wrote `<one-line summary> ｜ EN: <original>`. After upgrading, those descriptions are translated again in full from the backed-up original, not just stripped of their English half.

## Managed directories

`~/.agents/skills`, `~/.claude/skills` (follows `CLAUDE_CONFIG_DIR`), `~/.codex/skills` (follows `CODEX_HOME`, excluding `.system`), `~/.config/opencode/skills`, `~/.cursor/skills`, `~/.gemini/skills`.

Project-level skill directories, skills synced from claude.ai (the `synced/` subdirectory), Codex's own (`.system/`) and plugin-bundled skills are never touched. Skills symlinked from several roots are written once, through their real path.

## Privacy and data handling

- Only skill descriptions are sent to Claude, using your own Claude Code login and quota.
- Backups and the log live in `~/.claude/skill-zh/` (under `CLAUDE_CONFIG_DIR` when set), created owner-only. The directory survives uninstalling. Run `/skill-zh:restore` before uninstalling; if you forget, reinstall and run it, or run `python3 skill_zh restore` from a checkout.

## Limitations

- Only Claude Code has hooks. Skills installed from Codex or a terminal are picked up at the next Claude Code session, or by `/skill-zh:translate`.
- New descriptions show from the next session.
- Translation quality is only sanity-checked (mostly Chinese, within the length cap). Edit a poor one by hand; it won't be overwritten again.
- A description edited back to English is indistinguishable from an upstream update and gets translated again.
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
