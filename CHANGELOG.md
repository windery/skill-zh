# Changelog

## 0.3.0 - 2026-10-02

### Changed

- Descriptions become Chinese only: a complete translation replaces the old `<summary> ｜ EN: <original>` format. Quoted trigger phrases, commands and names stay verbatim so skills keep triggering.
- Descriptions written by 0.1/0.2 are translated again in full from the backed-up original on the next run.
- A translation is recognised by a record in the state directory instead of a marker in the file. Skills updated upstream are translated again; descriptions edited by hand are never overwritten or restored.
- Translations come back as `@@@ <key>` text blocks instead of JSON, which broke on unescaped quotes in trigger phrases. Batches shrink from 15 to 10.

## 0.2.1 - 2026-10-02

### Fixed

- `status` ends with a tally line, and `/skill-zh:status` asks Claude to show the output verbatim. A small model relaying the list used to miscount.

## 0.2.0 - 2026-10-02

### Added

- `/skill-zh:status`, `/skill-zh:translate` and `/skill-zh:restore` commands, user-invoked only.
- `model` and `exclude` options through the plugin's `userConfig`, editable in `/config`.
- `CLAUDE_CONFIG_DIR` and `CODEX_HOME` are honoured when locating skills and state.
- CI: ruff, pytest on Python 3.8 and 3.13 with and without PyYAML, `claude plugin validate --strict`.

### Changed

- Hooks are `async`, and the translation runs in a detached process so it survives the session ending.
- Concurrent runs are serialised with `flock`, which the kernel releases if a run dies.
- Code split into the `skill_zh` package; tests moved to pytest.
- The debug log rotates at 1 MB.

### Removed

- `~/.claude/skill-zh/config.json`. Use `/config` instead.

## 0.1.0 - 2026-10-02

- First release: SessionStart and PostToolUse hooks that prepend a Chinese summary to English skill descriptions, with backups and `restore`.
