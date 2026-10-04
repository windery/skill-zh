# Changelog

## 0.3.2 - 2026-10-03

### Fixed

- SKILL.md files and backups are read and written byte for byte (`newline=""`). A CRLF file no longer comes back as LF: Python's text mode had been converting line endings on read, which the 0.3.1 fix and its string-level tests never saw. Found by translating real files with the real model.
- `restore` puts the original description line back verbatim, quoting style included, so a file nothing else touched is byte-identical to its backup.

## 0.3.1 - 2026-10-03

### Fixed

- `restore` no longer stops at the first file it cannot write; each failure is reported with its skill name.
- CRLF files keep their line endings, and a UTF-8 BOM is recognised and kept.
- Skills whose folder name contains a space are translated. Batch keys are now plain indices, so skill names and paths never reach the model.
- A file changed while its translation was running is left alone and translated again next time, instead of being overwritten with the stale copy.
- `restore` also covers skills listed in `exclude`.
- Replies that are not mostly Chinese (refusals, half-translated text) are rejected and retried.
- The `synced/` and `.system/` subdirectories are skipped explicitly rather than by accident of layout.
- Without PyYAML, the rewrite check compares every other top-level field line by line.

### Changed

- Comments and docstrings are in Chinese.
- `__version__` is read from plugin.json; `commands.status` and the `run` alias of `translate` are gone.
- README documents the fourth status (无简介), that a run which misses the lock does not queue, and which hand edits are left alone.

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
