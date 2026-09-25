"""验证：输入法修复是否真的生效。

场景：目标窗口处于中文输入法（布局 0x0804）时，注入的按键会被吞成 '??'。
调用 win_input.ensure_english_input() 之后，按键应恢复为正确的 'a'。
"""
from __future__ import annotations

# 由 _move_tests.py 自动迁移而来。测试位于 tests/，项目根目录在其上一级。
import os as _os
import sys as _sys

PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, PROJECT_ROOT)


import functools
import json
import os
import tempfile
import shutil
import subprocess
import sys
import time

print = functools.partial(print, flush=True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from quickscript.platform import wininput as wi

wi.enable_dpi_awareness()

PASS, FAIL, SKIP = [], [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print("  [%s] %s   %s" % ("OK  " if cond else "FAIL", name, detail))


def skip(name, detail=""):
    """环境不满足时跳过，而不是判失败。

    例如英文版 Windows（含 GitHub Actions runner）根本没装中文输入法，
    无法建立"按键被输入法吞掉"的场景。这不是本程序的缺陷，
    应当与 tests/run_all.py 的 exit code 2（环境性跳过）语义一致。
    """
    SKIP.append((name, detail))
    print("  [SKIP] %s   %s" % (name, detail))


TMP = os.path.join(tempfile.gettempdir(), "quickscript_ime")
INFO, EV = os.path.join(TMP, "info.json"), os.path.join(TMP, "ev.json")
TITLE = "IME_FIX_TEST_%d" % os.getpid()


def start_target():
    os.makedirs(TMP, exist_ok=True)
    for p in (INFO, EV):
        if os.path.isfile(p):
            os.remove(p)
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "e2e_target.py"),
                             INFO, EV, "300", "200", "620", "460", TITLE], cwd=HERE)
    end = time.time() + 20
    while time.time() < end:
        if os.path.isfile(INFO):
            try:
                info = json.load(open(INFO, encoding="utf-8"))
                if info.get("hwnd") and info["client"][2] > 0:
                    return proc, info
            except Exception:
                pass
        time.sleep(0.1)
    raise RuntimeError("目标进程启动超时")


def keys():
    try:
        return json.load(open(EV, encoding="utf-8")).get("keys", [])
    except Exception:
        return []


def send_a():
    scan = wi.user32.MapVirtualKeyW(0x41, 0)
    kb = wi.Keyboard()
    kb.press("a", hold=0.05)


def inject_and_read(tag):
    wi.activate_window(HWND)
    time.sleep(0.25)
    before = len(keys())
    send_a()
    time.sleep(0.5)
    delta = keys()[before:]
    downs = [x for x in delta if x[0] == "down"]
    got = downs[0][1] if downs else "(无)"
    print("     %-24s 布局=0x%04X  %-24s" % (tag, wi.window_layout_id(HWND), str(delta)))
    return got


def force_chinese():
    """用真实热键 Win+Space 切到中文。"""
    for _ in range(4):
        if wi.window_layout_id(HWND) == wi.LANG_CHINESE_SIMPLIFIED:
            return True
        kb = wi.Keyboard()
        kb.key_down(0x5B)
        kb.key_down(0x20)
        kb.key_up(0x20)
        kb.key_up(0x5B)
        time.sleep(0.8)
    return wi.window_layout_id(HWND) == wi.LANG_CHINESE_SIMPLIFIED


HWND = 0


def main():
    global HWND
    # GBK 控制台下输出 ✓ 之类的字符会抛 UnicodeEncodeError，
    # 让本来通过的测试反而"崩"掉。这里统一把输出改成容错模式。
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    print("输入法修复验证开始")
    proc, info = start_target()
    HWND = int(info["hwnd"])
    try:
        # 前提检查：目标窗口必须能取得前台焦点。
        # 否则按键会送到别处（例如正在运行的目标程序），造成误判。
        # 若前台被更高权限的窗口占用，普通权限进程抢不到焦点，那是环境限制。
        wi.activate_window(HWND)
        time.sleep(0.6)
        fg = wi.foreground_window()
        if fg != HWND:
            fg_pid = wi.process_id_of_window(fg)
            fg_lvl = wi.integrity_level(fg_pid)
            my_lvl = wi.integrity_level(wi.kernel32.GetCurrentProcessId())
            print("目标窗口无法取得前台焦点：")
            print("  当前前台 = %r（%s 权限）"
                  % (wi.window_title(fg) or "(无标题)", wi.level_name(fg_lvl)))
            print("  本进程   = %s 权限" % wi.level_name(my_lvl))
            if (fg_lvl or 0) > (my_lvl or 0):
                print()
                print("  >>> 前台被更高权限的窗口占用（例如以管理员身份运行的目标程序），")
                print("      普通权限进程抢不到焦点，按键会被送到那个窗口去。")
                print("      这是环境限制，不是本程序缺陷。")
                print("  >>> 请先关闭目标程序（或让前台空着）再重新运行本测试。")
            print()
            check("目标窗口能取得前台焦点（测试前提）", False,
                  "前台被 %r 占用" % (wi.window_title(fg) or "其它窗口"))
            return 2          # 2 = 环境不满足，与 1（真实失败）区分
        print("目标 hwnd=%d\n" % HWND)

        # 1) 建立问题场景：切到中文
        print("步骤1：把目标窗口切到中文输入法")
        got_cn = force_chinese()
        if got_cn:
            check("能建立中文输入法场景（用于复现问题）", True)
        else:
            # 英文版 Windows（包括 GitHub Actions 的 windows-latest runner）
            # 没有安装中文输入法，无法复现"按键被吞"的场景。
            # 这是环境限制而非缺陷，跳过而不是失败 —— 与 run_all.py 的
            # "环境跳过"(exit code 2) 语义保持一致。
            skip("能建立中文输入法场景（用于复现问题）",
                 "本机未安装中文输入法（布局 0x%04X），无法复现该场景"
                 % wi.window_layout_id(HWND))

        if got_cn:
            print("步骤2：中文布局下注入按键（预期被吞）")
            got = inject_and_read("修复前")
            check("复现了『按键被输入法吞掉』问题", got in ("??", "(无)"),
                  "收到 %r（'??' 表示被输入法转成 VK_PROCESSKEY）" % got)

        # 3) 调用修复函数
        print("\n步骤3：调用 ensure_english_input()")
        switched, why = wi.ensure_english_input(HWND)
        print("     返回：switched=%s  %s" % (switched, why))
        if got_cn:
            check("修复函数报告已切换", switched, why)
        check("目标窗口布局已变为英文", wi.window_layout_id(HWND) == wi.LANG_ENGLISH_US,
              "布局 0x%04X" % wi.window_layout_id(HWND))

        # 4) 再次注入，应正常
        print("\n步骤4：修复后再注入（预期正常）")
        got2 = inject_and_read("修复后")
        check("修复后按键送达正确（收到 'a'）", got2 == "a", "收到 %r" % got2)

        # 5) 幂等性：已英文时再调用不应出错
        print("\n步骤5：幂等性检查")
        switched2, why2 = wi.ensure_english_input(HWND)
        check("已是英文时再次调用不出错且不误报切换",
              (not switched2) and ("英文" in why2), why2)

        # 6) 扫描码仍随按键下发（部分自绘窗口程序读扫描码）
        print("\n步骤6：扫描码检查")
        scan = wi.user32.MapVirtualKeyW(0x41, 0)
        check("能取得 'a' 的硬件扫描码", scan == 0x1E, "扫描码=0x%02X" % scan)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(TMP, ignore_errors=True)

    print("\n" + "=" * 62)
    print("通过 %d 项，失败 %d 项，跳过 %d 项" % (len(PASS), len(FAIL), len(SKIP)))
    for n, d in FAIL:
        print("  · %s   %s" % (n, d))
    for n, d in SKIP:
        print("  - %s：%s" % (n, d))
    if not FAIL and SKIP:
        print("输入法修复验证通过（有环境性跳过）✓")
    elif not FAIL:
        print("输入法修复验证通过 ✓")
    # 0 = 全过；1 = 有真实失败；2 = 无失败但有环境性跳过（与 run_all.py 一致）
    if FAIL:
        return 1
    return 2 if SKIP else 0


if __name__ == "__main__":
    sys.exit(main())
