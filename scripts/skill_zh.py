#!/usr/bin/env python3
"""skill-zh：给英文 skill 简介补上中文说明，英文原文原样保留在后面，触发词不受影响。

改写后的 description 形如：「中文说明 ｜ EN: 英文原文」。

用法：
  skill_zh.py status    列出每个 skill 的汉化状态
  skill_zh.py run       立刻扫描并翻译
  skill_zh.py restore   把改过的简介全部改回英文原文
  skill_zh.py hook      给 Claude Code 钩子用：读 stdin，有待翻译的就转到后台翻译，立刻返回

可选配置 ~/.claude/skill-zh/config.json：
  {"exclude": ["skill 名"], "extra_dirs": ["~/some/skills"], "model": "haiku"}
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

__version__ = "0.1.0"

HOME = os.path.expanduser("~")

# 只扫全局目录。项目里的 skill 不碰，免得在仓库里改出 diff。
# ~/.claude/skills/synced（claude.ai 同步）和 ~/.codex/skills/.system（Codex 自带）不在 */SKILL.md 范围内，天然跳过。
SKILL_DIRS = [
    "~/.agents/skills",
    "~/.claude/skills",
    "~/.codex/skills",
    "~/.config/opencode/skills",
    "~/.cursor/skills",
    "~/.gemini/skills",
]
SEP = " ｜ EN: "
MAX_LEN = 1024  # Codex 等工具对 description 的长度上限，超了整个 skill 会加载失败
BATCH = 15
ZH_LIMIT = 80
CJK = re.compile(r"[一-鿿]")
FM = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
DESC_KEY = re.compile(r"description\s*:")
# 看起来像在装/更新 skill 的命令，或动了 skills 目录
INSTALL_CMD = re.compile(r"\bskills?\b.*\b(add|install|update|upgrade)\b|/skills(/|\b)", re.I)

PROMPT = """你是技术翻译。下面 JSON 的每个值是一个 AI 编程助手 skill 的英文简介。
把每条改写成简体中文的一句话说明（不超过 {limit} 个汉字），说清它是干什么的、什么时候用。
- skill 名、命令、产品名、文件名保留原文，中文和英文之间加一个空格
- 不加引号，不换行
- 只输出一个 JSON 对象：键与输入完全相同，值是中文说明。不要输出任何其他内容。

输入：
{payload}"""


def state_path(*parts):
    base = os.environ.get("SKILL_ZH_STATE") or os.path.join(HOME, ".claude", "skill-zh")
    return os.path.join(base, *parts)


def log(msg, quiet=True):
    os.makedirs(state_path(), exist_ok=True)
    with open(state_path("log.txt"), "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    if not quiet:
        print(msg)


def load_config():
    try:
        with open(state_path("config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def skill_files():
    cfg = load_config()
    dirs = os.environ.get("SKILL_ZH_DIRS")
    dirs = dirs.split(os.pathsep) if dirs else SKILL_DIRS + list(cfg.get("extra_dirs", []))
    exclude = set(cfg.get("exclude", []))
    seen = set()
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(os.path.expanduser(d), "*", "SKILL.md"))):
            name = os.path.basename(os.path.dirname(f))
            real = os.path.realpath(f)
            if name in exclude or real in seen:
                continue
            seen.add(real)
            yield name, real


# ---------- frontmatter ----------

def _desc_block(lines):
    """返回 description 在 frontmatter 行列表里的 [start, end)，找不到返回 None。"""
    for i, line in enumerate(lines):
        if DESC_KEY.match(line):
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j][:1] in (" ", "\t")):
                j += 1
            while j > i + 1 and not lines[j - 1].strip():
                j -= 1
            return i, j
    return None


def _fallback_desc(fm):
    """没装 PyYAML 时的简易解析，只认 description 一个字段。"""
    lines = fm.split("\n")
    blk = _desc_block(lines)
    if not blk:
        return None
    i, j = blk
    first = DESC_KEY.sub("", lines[i], count=1).strip()
    rest = [l.strip() for l in lines[i + 1:j]]
    if first[:1] in (">", "|"):
        return " ".join(l for l in rest if l)
    value = " ".join([first] + [l for l in rest if l])
    if value[:1] == '"':
        try:
            return json.loads(value)
        except ValueError:
            return value.strip('"')
    if value[:1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def parse_fm(text):
    m = FM.match(text)
    if not m:
        return None
    try:
        import yaml
    except ImportError:
        return {"description": _fallback_desc(m.group(1))}
    try:
        data = yaml.safe_load(m.group(1))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def get_desc(text):
    data = parse_fm(text)
    d = data.get("description") if data else None
    return d if isinstance(d, str) else None


def set_desc(text, new):
    """把 description 换成单行双引号字符串，其他字段和正文原样不动。失败返回 None。"""
    m = FM.match(text)
    if not m:
        return None
    lines = m.group(1).split("\n")
    blk = _desc_block(lines)
    if not blk:
        return None
    i, j = blk
    lines[i:j] = ["description: " + json.dumps(new, ensure_ascii=False)]
    out = text[:m.start(1)] + "\n".join(lines) + text[m.end(1):]
    # 写回前自检：description 变成预期值，其余字段一个不差
    old, now = parse_fm(text), parse_fm(out)
    if not now or now.get("description") != new:
        return None
    old = dict(old or {})
    now = dict(now)
    old.pop("description", None)
    now.pop("description", None)
    return out if old == now else None


def mostly_zh(desc):
    """中文字数不少于英文单词数才算中文简介；夹几个中文触发词的英文简介仍要翻译。"""
    return len(CJK.findall(desc)) >= len(re.findall(r"[A-Za-z]+", desc))


def compose(zh, en):
    en = " ".join(en.split())
    room = MAX_LEN - len(SEP) - len(en)
    if room < 10:
        return None
    if len(zh) > room:
        zh = zh[:room - 1] + "…"
    return zh + SEP + en


# ---------- 翻译 ----------

def claude_bin():
    for c in (shutil.which("claude"), os.path.join(HOME, ".local", "bin", "claude"),
              os.environ.get("CLAUDE_CODE_EXECPATH")):
        if c and os.access(c, os.X_OK):
            return c
    return None


def translate(items):
    """items: {key: 英文简介} → {key: 中文说明}，失败的键不出现在结果里。"""
    exe = claude_bin()
    if not exe:
        log("找不到 claude 命令，跳过翻译")
        return {}
    model = load_config().get("model", "haiku")
    result = {}
    keys = list(items)
    for k in range(0, len(keys), BATCH):
        chunk = {key: items[key] for key in keys[k:k + BATCH]}
        prompt = PROMPT.format(limit=ZH_LIMIT, payload=json.dumps(chunk, ensure_ascii=False, indent=1))
        try:
            # 不加载任何设置来源：子进程里没有插件和钩子，不会递归触发自己
            p = subprocess.run(
                [exe, "-p", "--model", model, "--tools", "", "--disable-slash-commands",
                 "--strict-mcp-config", "--no-session-persistence", "--setting-sources", "",
                 "--output-format", "text"],
                input=prompt, capture_output=True, text=True, timeout=300, cwd=state_path(),
                env=dict(os.environ, SKILL_ZH_CHILD="1"))
            out = p.stdout
            data = json.loads(out[out.index("{"):out.rindex("}") + 1])
        except Exception as e:
            log("翻译调用失败：%r" % (e,))
            continue
        for key, zh in data.items():
            if key in chunk and isinstance(zh, str) and CJK.search(zh):
                result[key] = " ".join(zh.split())
    return result


# ---------- 命令 ----------

def scan():
    """返回 (待翻译列表, 全部状态列表)。"""
    todo, rows = [], []
    for name, path in skill_files():
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        desc = get_desc(text)
        if not desc:
            state = "无简介"
        elif SEP in desc:
            state = "已汉化"
        elif mostly_zh(desc):
            state = "本来就是中文"
        else:
            state = "待翻译"
            todo.append((name, path, text, desc))
        rows.append((name, state, path))
    return todo, rows


def orig_path(path):
    h = hashlib.sha1(path.encode("utf-8")).hexdigest()[:10]
    return state_path("originals", "%s-%s.md" % (os.path.basename(os.path.dirname(path)), h))


def cmd_run(quiet):
    if not acquire():
        log("已有一个翻译任务在跑，跳过", quiet)
        return
    try:
        todo, _ = scan()
        if not todo:
            log("没有需要翻译的 skill", quiet)
            return
        keys = {"%d:%s" % (n, t[0]): t for n, t in enumerate(todo)}
        zh = translate({k: t[3] for k, t in keys.items()})
        os.makedirs(state_path("originals"), exist_ok=True)
        done = 0
        for k, (name, path, text, desc) in keys.items():
            if k not in zh:
                log("%s：没拿到译文，下次再试" % name, quiet)
                continue
            new_desc = compose(zh[k], desc)
            new_text = set_desc(text, new_desc) if new_desc else None
            if not new_text:
                log("%s：改写后校验没通过，保持原样" % name, quiet)
                continue
            try:
                with open(orig_path(path), "w", encoding="utf-8") as f:
                    f.write(text)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_text)
            except OSError as e:
                log("%s：写文件失败 %r" % (name, e), quiet)
                continue
            done += 1
            log("%s：%s" % (name, zh[k]), quiet)
        log("本次汉化 %d / %d 个" % (done, len(keys)), quiet)
    finally:
        release()


def cmd_status():
    _, rows = scan()
    if not rows:
        print("没找到任何 skill")
        return
    width = max(len(r[0]) for r in rows)
    for name, state, path in sorted(rows, key=lambda r: (r[1], r[0])):
        print("%-*s  %-6s  %s" % (width, name, state, path.replace(HOME, "~")))


def cmd_restore():
    n = 0
    for name, path in skill_files():
        op = orig_path(path)
        if not os.path.exists(op):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        cur = get_desc(text)
        with open(op, encoding="utf-8") as f:
            orig = get_desc(f.read())
        if not cur or SEP not in cur or not orig:
            continue
        new_text = set_desc(text, orig)
        if new_text:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)
            n += 1
            print("已改回英文：" + name)
    print("共改回 %d 个" % n)


def cmd_hook(stdin=None):
    if os.environ.get("SKILL_ZH_CHILD"):
        return
    try:
        data = json.load(stdin or sys.stdin)
    except Exception:
        data = {}
    if data.get("hook_event_name") == "PostToolUse":
        cmd = (data.get("tool_input") or {}).get("command") or ""
        if not INSTALL_CMD.search(cmd):
            return
    if not scan()[0]:
        return
    os.makedirs(state_path(), exist_ok=True)
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "run", "--quiet"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, cwd=state_path())


def acquire():
    os.makedirs(state_path(), exist_ok=True)
    lock = state_path("lock")
    try:
        os.mkdir(lock)
        return True
    except FileExistsError:
        if time.time() - os.path.getmtime(lock) < 900:
            return False
        shutil.rmtree(lock, ignore_errors=True)
        try:
            os.mkdir(lock)
            return True
        except FileExistsError:
            return False


def release():
    shutil.rmtree(state_path("lock"), ignore_errors=True)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    cmd = args[0] if args else "status"
    if cmd == "hook":
        try:
            cmd_hook()
        except Exception as e:  # 钩子出错不能影响正常会话
            log("hook 出错：%r" % (e,))
    elif cmd == "run":
        cmd_run(quiet="--quiet" in args)
    elif cmd == "status":
        cmd_status()
    elif cmd == "restore":
        cmd_restore()
    elif cmd in ("-V", "--version"):
        print(__version__)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
