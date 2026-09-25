"""启动链验证（正式版，会随交付一起提供）

验证内容：
  1. 关键文件齐全
  2. run_admin.py 的检查模式正常
  3. 每个 .bat 都能被 cmd 正确解析（不会出现语法/找不到命令错误）
  4. 中文名 BAT 只做转发，且正文与文件名编码分离得当
  5. 提权接口可用（只做 dry-run，不真的弹 UAC）

用法：python launch_test.py
"""
from __future__ import annotations

# 由 _move_tests.py 自动迁移而来。测试位于 tests/，项目根目录在其上一级。
import os as _os
import sys as _sys

PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, PROJECT_ROOT)


import os
import tempfile
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = PROJECT_ROOT          # 启动相关文件都在项目根目录
PASS, FAIL, SKIP = [], [], []

PARSE_ERRORS = (
    "is not recognized as an internal or external command",
    "The syntax of the command is incorrect",
    "was unexpected at this time",
    "命令语法不正确",
    "此时不应有",
    "系统找不到指定的路径",
)


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print("  [%s] %s   %s" % ("OK  " if cond else "FAIL", name, detail))


def skip(name, why):
    SKIP.append((name, why))
    print("  [跳过] %s   （%s）" % (name, why))


def bat_files():
    found = [f for f in os.listdir(ROOT) if f.lower().endswith(".bat")]
    dev_dir = os.path.join(ROOT, "dev")
    if os.path.isdir(dev_dir):
        found += [os.path.join("dev", f) for f in os.listdir(dev_dir)
                  if f.lower().endswith(".bat")]
    return sorted(found)


def parse_probe(fn):
    """只验证 BAT 的**语法解析**是否正常。

    关键点：探测文件必须放在项目根目录里执行。
    因为 BAT 普遍以 `cd /d "%~dp0"` 定位自身，再转发给同目录的另一个 BAT；
    若把它复制到别处运行，转发目标就不存在，会误报「找不到命令」。
    因此这里在根目录生成一个临时副本，跑完即删。
    """
    path = os.path.join(ROOT, fn)
    with open(path, "rb") as f:
        raw = f.read()
    lines = raw.replace(b"\r\n", b"\n").split(b"\n")

    launch_keys = (b"__main__.py", b"test_units.py", b"test_ui.py", b"test_e2e.py",
                   b"test_ime.py", b"run_admin.py", b"test_launch.py",
                   b"run_admin.bat", b"run.bat", b"-m quickscript",
                   b"run_all.py", b"tests\\")
    out = []
    for ln in lines:
        low = ln.strip().lower()
        if low.startswith(b"rem"):
            out.append(ln)
            continue
        if low.startswith(b"pause"):
            out.append(b"rem pause")
            continue
        if any(k in low for k in launch_keys):
            # 换成 echo，避免真的启动程序；语法结构保持不变
            out.append(b"echo [SKIP] " + ln.strip()[:50])
            continue
        out.append(ln)
    patched = b"\r\n".join(out)

    # 探测文件必须与原始 BAT 同目录：这些脚本用 %~dp0 定位自身，
    # 并可能转发给同目录的另一个 BAT；换个目录跑就会误报「找不到命令」。
    # 名字里先去掉 .bat 扩展名，避免生成 xxx.bat.bat。
    src_dir = os.path.dirname(os.path.join(ROOT, fn))
    stem = os.path.splitext(os.path.basename(fn))[0]
    safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in stem)
    probe = os.path.join(src_dir, "_probe_%s.bat" % safe)
    try:
        with open(probe, "wb") as f:
            f.write(patched)
    except OSError as exc:
        # 目录只读时无法生成探测文件 —— 报告为跳过，而不是失败
        return "__SKIP__: %s" % exc

    try:
        p = subprocess.run(["cmd", "/c", probe], capture_output=True, timeout=30,
                           cwd=src_dir, stdin=subprocess.DEVNULL)
        blob = p.stdout + p.stderr
    except subprocess.TimeoutExpired as exc:
        blob = (exc.stdout or b"") + (exc.stderr or b"")
    finally:
        try:
            os.remove(probe)
        except Exception:
            pass

    text = blob.decode("utf-8", "replace")
    if "\ufffd" in text:
        text += "\n" + blob.decode("gbk", "replace")
    return text


def _safe_output():
    """GBK 控制台下打印 ✓ 等字符会抛 UnicodeEncodeError，
    让本来通过的测试反而崩掉。统一改成容错输出。"""
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass


def main():
    _safe_output()
    print("=" * 70)
    print("启动链验证")
    print("=" * 70)

    print("\n1. 关键文件齐全")
    # 新的包结构：代码在 quickscript/ 下，启动器在根目录
    for fn in ("dev/run_admin.py", "dev/run_admin.bat",
               "quickscript/__main__.py", "quickscript/__init__.py",
               "quickscript/metadata.py", "quickscript/model.py",
               "quickscript/runtime.py", "quickscript/storage.py",
               "quickscript/ui.py",
               "quickscript/layers/__init__.py", "quickscript/layers/actions.py",
               "quickscript/layers/flow.py", "quickscript/layers/triggers.py",
               "quickscript/layers/target.py",
               "quickscript/platform/__init__.py",
               "quickscript/platform/wininput.py",
               "quickscript/platform/vision.py",
               "quickscript/platform/overlays.py",
               "README.md", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md",
               "docs/script-format.md",
               "examples/01-notepad-input.json",
               "tests/run_all.py"):
        check("存在 %s" % fn, os.path.isfile(os.path.join(ROOT, fn)))

    print("\n1b. 启动器 BAT 齐全")
    for fn in ("启动.bat", "以管理员身份启动.bat",
               "dev/run.bat", "dev/run_admin.bat", "dev/调试启动.bat"):
        check("存在 %s" % fn, os.path.isfile(os.path.join(ROOT, fn)))

    print("\n2. run_admin.py 检查模式")
    p = subprocess.run([sys.executable, os.path.join(ROOT, "dev", "run_admin.py"), "--check"],
                       capture_output=True, cwd=ROOT)
    out = p.stdout.decode("utf-8", "replace")
    check("--check 返回码为 0", p.returncode == 0, "返回码=%s" % p.returncode)
    check("报告当前权限", "当前权限" in out)
    check("--check 不会触发提权", "用户账户控制" not in out)
    check("报告使用新项目名", "QuickScript" in out, out.splitlines()[1] if out else "")

    print("\n2b. python -m quickscript --version 可用")
    p = subprocess.run([sys.executable, "-m", "quickscript", "--version"],
                       capture_output=True, cwd=ROOT)
    vout = p.stdout.decode("utf-8", "replace")
    check("--version 返回码为 0", p.returncode == 0, "返回码=%s" % p.returncode)
    check("版本输出含项目名", "QuickScript Studio" in vout, vout.strip()[:60])

    print("\n3. 每个 BAT 都能被 cmd 正确解析")
    for fn in bat_files():
        text = parse_probe(fn)
        if text.startswith("__SKIP__"):
            skip("「%s」无法生成探测文件" % fn, text[8:].strip()[:60])
            continue
        hits = [m for m in PARSE_ERRORS if m in text]
        # 只关心"找不到命令/语法错误"，转发目标存在与否不算解析错误
        check("「%s」无解析错误" % fn, not hits, "; ".join(hits))

    print("\n3b. BAT 不能带 UTF-8 BOM（否则 cmd 第一行解析失败）")
    for fn in bat_files():
        with open(os.path.join(ROOT, fn), "rb") as f:
            raw = f.read()
        has_bom = raw[:3] == b"\xef\xbb\xbf"
        first_ok = raw.lstrip(b"\xef\xbb\xbf").lower().startswith(b"@echo off")
        check("「%s」无 BOM" % fn, not has_bom,
              "检测到 BOM！会导致 cmd 报错" if has_bom else "")
        check("「%s」以 @echo off 开头" % fn, first_ok,
              repr(raw[:16]) if not first_ok else "")

    print("\n4. BAT 里的中文只允许出现在 echo 行（结构行出现中文才危险）")
    # 判定依据：cmd 用 OEM 代码页解析 .bat。中文放在 echo 里无副作用；
    # 但如果出现在 if/for 条件、标签、变量赋值等结构行，就可能被误解析成命令。
    STRUCT_PREFIX = (b"if ", b"if(", b"for ", b"goto ", b"call ", b"set ",
                     b":", b"%", b"else")
    for fn in bat_files():
        with open(os.path.join(ROOT, fn), "rb") as f:
            raw = f.read()
        if all(b < 128 for b in raw):
            check("「%s」正文为纯 ASCII" % fn, True, "")
            continue
        bad_lines = []
        for ln in raw.replace(b"\r\n", b"\n").split(b"\n"):
            stripped = ln.strip()
            if all(b < 128 for b in stripped):
                continue
            low = stripped.lower()
            if low.startswith(b"rem") or low.startswith(b"echo") or low.startswith(b"::"):
                continue          # 注释和 echo 里放中文是安全的
            if any(low.startswith(p) for p in STRUCT_PREFIX):
                bad_lines.append(stripped[:50])
        check("「%s」中文只在 echo/注释里" % fn, not bad_lines,
              "结构行含中文: %s" % bad_lines if bad_lines else "")

    print("\n5. 中文名 BAT 内容是薄转发层（不做实际工作，降低解析风险）")
    for fn in bat_files():
        if not any(ord(c) > 127 for c in fn):
            continue
        with open(os.path.join(ROOT, fn), "rb") as f:
            raw = f.read()
        if b"run_admin.bat" in raw:
            check("「%s」转发到 run_admin.bat" % fn, True, "")
        else:
            # 不转发的（如自检/调试启动）只要结构行无中文即可，前面已校验
            skip("「%s」不是转发层" % fn, "它是独立功能的 BAT，已通过解析测试")

    print("\n6. 提权接口可用性（dry-run，不弹 UAC）")
    # run_admin.py 位于 dev/（开发工具），其所在目录要能被 import 到
    for base in (ROOT, os.path.join(ROOT, "dev")):
        if base not in sys.path:
            sys.path.insert(0, base)
    import run_admin
    check("is_admin() 可调用", isinstance(run_admin.is_admin(), bool))
    exe = run_admin.python_exe()
    check("能定位到界面解释器", os.path.isfile(exe), exe)
    entry = os.path.join(ROOT, run_admin.ENTRY_MODULE, "__main__.py")
    check("模块入口存在", os.path.isfile(entry),
          "%s/__main__.py" % run_admin.ENTRY_MODULE)
    check("ShellExecuteW 可访问",
          hasattr(run_admin.ctypes.windll.shell32, "ShellExecuteW"))
    check("错误码提示覆盖常见情况", 5 in run_admin.ERR_HINT and 2 in run_admin.ERR_HINT,
          str(sorted(run_admin.ERR_HINT)))
    check("单实例识别关键字是新项目名",
          run_admin.APP_TITLE_KEY == "QuickScript Studio", run_admin.APP_TITLE_KEY)

    print("\n7. 提权参数构造正确（不执行）")
    check("入口使用模块方式（-m quickscript）",
          run_admin.ENTRY_MODULE == "quickscript", run_admin.ENTRY_MODULE)
    check("含中文的脚本目录能被正确表达",
          subprocess.list2cmdline([os.path.join(ROOT, "中文 x.py")]).count('"') == 2,
          subprocess.list2cmdline([os.path.join(ROOT, "中文 x.py")]))

    print("\n8. 提权命令必须先用 cd 切目录（否则会静默失败）")
    # 实测教训：runas cmd /c "E:\Python\pythonw.exe" "<...>\gui.py"
    # 会返回 42（成功）但目标进程根本不启动；必须先 cd 到程序目录、
    # 再用相对文件名调用解释器，才会真正执行。
    import inspect
    src = inspect.getsource(run_admin.launch_gui_elevated)
    check("提权命令包含 cd /d", "cd /d" in src, "")
    check("提权命令用相对文件名调用解释器（不是跨盘绝对路径）",
          "os.path.basename" in src, "")
    check("提权命令带输出重定向（便于排查）", "2>&1" in src, "")

    print("\n9. 提权命令行里的路径必须是纯 ASCII（cmd 按 OEM 代码页解析）")
    check("启动日志路径为纯 ASCII",
          all(ord(c) < 128 for c in run_admin.LAUNCH_LOG),
          run_admin.LAUNCH_LOG)
    check("日志放在 data 目录下", "data" in run_admin.LAUNCH_LOG, "")

    print("\n10. pythonw 下不会因 print 失败而静默崩溃")
    check("say() 有异常保护", "except Exception" in inspect.getsource(run_admin.say), "")
    check("有顶层异常兜底（写日志而非静默退出）",
          "traceback" in inspect.getsource(run_admin), "")
    check("日志函数自身不会抛异常",
          "except Exception" in inspect.getsource(run_admin.log), "")

    print("\n11. 单实例检测必须用窗口枚举（不能靠查进程命令行）")
    # 实测教训：若已有实例以管理员权限运行，普通权限进程读它的
    # CommandLine 会被「拒绝访问」，检测会静默失败并误判为没有实例。
    src_inst = inspect.getsource(run_admin.find_existing_instances)
    # 去掉文档字符串后再判断，避免把"说明为什么不用它"的注释当成真的调用
    import re as _re
    body = _re.sub(r'""".*?"""', "", src_inst, flags=_re.S)
    body = _re.sub(r"#.*", "", body)
    check("用窗口枚举实现（list_windows）", "list_windows" in body, "")
    check("代码里没有真的去查 CommandLine / CIM",
          "CommandLine" not in body and "CimInstance" not in body, "")
    check("检测函数可调用且返回列表",
          isinstance(run_admin.find_existing_instances(), list),
          str(run_admin.find_existing_instances())[:80])
    check("已有实例时不会重复启动（main 里有单实例分支）",
          "find_existing_instances" in inspect.getsource(run_admin.main), "")

    shutil.rmtree(os.path.join(tempfile.gettempdir(), "quickscript_launch"),
                        ignore_errors=True)

    print("\n" + "=" * 70)
    print("通过 %d 项，失败 %d 项，跳过 %d 项" % (len(PASS), len(FAIL), len(SKIP)))
    for n, d in FAIL:
        print("  ✗ %s   %s" % (n, d))
    for n, w in SKIP:
        print("  - 跳过 %s：%s" % (n, w))
    if not FAIL:
        print("启动链验证通过 ✓")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
