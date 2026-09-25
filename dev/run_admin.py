# -*- coding: utf-8 -*-
"""QuickScript Studio —— 管理员权限启动器

为什么需要这个启动器
--------------------
有些目标程序以「管理员权限」运行。Windows 的安全机制(UIPI)禁止普通权限进程
向更高权限的窗口发送模拟点击/按键 —— 表现就是「本工具自己聚焦时点击有效，
一切到目标窗口就没反应」。所以本工具需要用管理员权限启动。

为什么提权要绕个弯（实测结论）
------------------------------
用 ShellExecuteW(runas) 直接把「别的盘符上的绝对路径」交给解释器时，
进程会静默不启动：返回码 42（表示发起成功），但目标进程没跑起来、也没有任何输出。
实测可行的做法是——**先用 cd 切到项目目录，再用相对文件名启动解释器**：

    失败：runas cmd /c "E:\\Python\\pythonw.exe" "…\\quickscript\\__main__.py"
    成功：runas cmd /c cd /d "…" && pythonw.exe -m quickscript > log 2>&1

另外提权命令行里不要出现中文（cmd 会按 OEM 代码页处理，容易解析出错），
所以日志文件名用 ASCII，中文说明留给界面显示。

用法
----
  python run_admin.py            启动界面（需要时会弹 UAC）
  python run_admin.py --check    只检查权限与环境，不启动
  python run_admin.py --no-elev  不提权，直接以当前权限启动
  python run_admin.py --force    即使已是管理员也重新提权（调试用）
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ENTRY_MODULE = "quickscript"                    # 用模块入口，不依赖具体文件名

# --- 源码位置自适应 ---------------------------------------------------------
# 支持两种布局：
#   A) 入口与 quickscript/ 同目录（开发时的仓库根）
#   B) 源码在 src/ 下（分层后的交付目录，入口可能在 dev/ 或根目录）
_SRC_BASE = HERE
for _cand in (
    HERE,                                          # A: 同目录
    os.path.join(HERE, "src"),                     # A': 子目录 src/
    os.path.join(os.path.dirname(HERE), "src"),    # B: 上级 src/
    os.path.dirname(HERE),                         # B': 上级目录
):
    if os.path.isdir(os.path.join(_cand, ENTRY_MODULE)):
        _SRC_BASE = _cand
        if _cand not in sys.path:
            sys.path.insert(0, _cand)
        break
# ---------------------------------------------------------------------------

# 数据目录沿用源码树里的位置（提权命令会 cd 到源码目录）
LAUNCH_LOG = os.path.join(_SRC_BASE, "data", "launch.log")

# 窗口标题里用于识别本程序的标记
APP_TITLE_KEY = "QuickScript Studio"

shell32 = ctypes.windll.shell32
shell32.ShellExecuteW.restype = ctypes.c_void_p
shell32.ShellExecuteW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p,
                                  ctypes.c_wchar_p, ctypes.c_wchar_p,
                                  ctypes.c_wchar_p, ctypes.c_int)

SW_SHOWNORMAL = 1
SW_HIDE = 0

ERR_HINT = {
    2: "系统找不到指定的文件",
    3: "系统找不到指定的路径",
    5: "访问被拒绝 —— UAC 确认被取消，或被安全策略/杀毒软件拦截",
    8: "内存不足",
    26: "共享冲突",
    27: "文件关联不完整",
    28: "DDE 超时",
    29: "DDE 失败",
    30: "DDE 忙",
    31: "没有关联的应用程序",
    32: "动态链接库(DLL)加载失败",
}


# --------------------------------------------------------------------------
# 日志与小工具
# --------------------------------------------------------------------------

def log(msg: str) -> None:
    """写日志文件。pythonw 没有控制台，出问题只能靠这个排查。"""
    try:
        os.makedirs(os.path.dirname(LAUNCH_LOG), exist_ok=True)
        with open(LAUNCH_LOG, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def say(msg: str = "") -> None:
    """有控制台就打印，没有也绝不因为 print 失败而中断。"""
    try:
        if sys.stdout is not None:
            print(msg)
            sys.stdout.flush()
    except Exception:
        pass
    log(msg)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def python_exe(console: bool = False) -> str:
    """优先返回 pythonw.exe（无黑窗口）。"""
    exe = sys.executable
    want = "python.exe" if console else "pythonw.exe"
    cand = os.path.join(os.path.dirname(exe), want)
    return cand if os.path.isfile(cand) else exe


def safe_pause() -> None:
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\n按回车键关闭…")
    except Exception:
        pass


def show_tail(n: int = 25) -> None:
    if not os.path.isfile(LAUNCH_LOG):
        return
    say("—— 最近 %d 行启动日志 ——" % n)
    try:
        with open(LAUNCH_LOG, encoding="utf-8", errors="replace") as f:
            for line in f.read().splitlines()[-n:]:
                say("  " + line)
    except Exception:
        pass


# --------------------------------------------------------------------------
# 单实例检测
# --------------------------------------------------------------------------

def find_existing_instances():
    """找出已经打开的本程序窗口，返回 [(pid, title), ...]。

    为什么不用「查进程命令行」的办法：
      如果已有实例以管理员权限运行，普通权限进程读它的 CommandLine 会被
      「拒绝访问」，于是检测静默失败、误判为"没有实例"（实测踩过这个坑）。
      枚举窗口标题不涉及读别的进程内存，权限要求低，最可靠。

    为什么要检测：热键(F8/F9/F10)是全局的，只能被一个实例注册。
    重复启动会让新实例的热键注册失败，用户会以为"热键坏了"。
    """
    out = []
    try:
        from quickscript.platform import wininput as wi
        seen = set()
        for w in wi.list_windows(include_hidden=True):
            if APP_TITLE_KEY in (w.get("title") or ""):
                pid = wi.process_id_of_window(w["hwnd"])
                if pid and pid != os.getpid() and pid not in seen:
                    seen.add(pid)
                    out.append((pid, w["title"]))
    except Exception as exc:
        log("单实例检测失败（忽略）：%s" % exc)
    return out


def focus_existing_instance() -> bool:
    """把已有实例的窗口切到前台，返回是否成功。"""
    try:
        from quickscript.platform import wininput as wi
        for w in wi.list_windows(include_hidden=True):
            if APP_TITLE_KEY in (w.get("title") or ""):
                if wi.activate_window(w["hwnd"]):
                    return True
    except Exception as exc:
        log("激活已有实例失败：%s" % exc)
    return False


# --------------------------------------------------------------------------
# 提权
# --------------------------------------------------------------------------

def elevate(inner_cmd: str, show_window: bool = True) -> int:
    """提权执行一段 cmd 命令，返回 ShellExecuteW 返回值（>32 为成功）。"""
    return int(shell32.ShellExecuteW(
        None, "runas", "cmd.exe", "/c " + inner_cmd, HERE,
        SW_SHOWNORMAL if show_window else SW_HIDE))


def launch_gui_elevated(src_dir=None) -> int:
    """提权启动界面。

    做法（实测唯一可靠的组合）：
      1) 先 cd 到项目目录 —— 避开跨盘符绝对路径导致的静默失败
      2) 解释器用相对文件名调用，入口用 -m quickscript
      3) 输出重定向到 ASCII 路径的日志
    """
    exe = os.path.basename(python_exe(console=False))
    work = src_dir or HERE
    inner = ('cd /d "%s" && "%s" -m %s > "%s" 2>&1'
             % (work, exe, ENTRY_MODULE, LAUNCH_LOG))
    log("提权启动界面：%s" % inner)
    return elevate(inner, show_window=False)


# --------------------------------------------------------------------------
def main() -> int:
    argv = sys.argv[1:]
    check_only = "--check" in argv
    no_elev = "--no-elev" in argv
    force = "--force" in argv

    log("=" * 56)
    log("启动器被调用 argv=%s  is_admin=%s" % (argv, is_admin()))

    try:
        from quickscript.metadata import APP_NAME, VERSION
        app_name, version = APP_NAME, VERSION
    except Exception:
        app_name, version = "QuickScript Studio", "?"

    say("=" * 62)
    say(" %s  %s" % (app_name, version))
    say(" 管理员权限启动器")
    say("=" * 62)
    say("项目目录 : %s" % HERE)
    say("源码目录 : %s" % _SRC_BASE)
    say("当前权限 : %s" % ("管理员" if is_admin() else "普通用户"))
    say("解释器   : %s" % python_exe())
    say("")

    # 入口位置已由顶部的源码位置自适应算好
    entry = os.path.join(_SRC_BASE, ENTRY_MODULE, "__main__.py")
    if not os.path.isfile(entry):
        say("找不到 %s/__main__.py，无法启动。请确认文件完整。" % ENTRY_MODULE)
        safe_pause()
        return 1

    if check_only:
        say("（--check 模式：只检查环境，不启动界面）")
        return 0

    # 单实例检查：热键是全局的，重复启动会让新实例的热键注册失败
    if not force:
        running = find_existing_instances()
        if running:
            say("已经有一个 %s 在运行了（进程 %s）。"
                % (app_name, "、".join(str(p) for p, _t in running)))
            if focus_existing_instance():
                say("已把它的窗口切到最前，请直接使用那个窗口。")
            else:
                say("请在任务栏找到「%s」窗口。" % app_name)
            say("（确实要再开一个，请加 --force 参数）")
            return 0

    # 已是管理员（或用户明确要求不提权）：直接启动界面
    if (is_admin() or no_elev) and not force:
        say("以当前权限启动界面……")
        exe = python_exe(console=False)
        try:
            os.chdir(_SRC_BASE)             # 先切目录，保持行为一致
            os.execv(exe, [exe, "-m", ENTRY_MODULE])
        except Exception as exc:
            log("execv 失败：%s" % exc)
            try:
                subprocess.Popen([exe, "-m", ENTRY_MODULE], cwd=_SRC_BASE)
                say("已用备用方式启动界面。")
                return 0
            except Exception as exc2:
                log("备用启动也失败：%s" % exc2)
                say("启动界面失败：%s" % exc2)
                safe_pause()
                return 1

    # 普通权限：需要提权
    say("需要管理员权限：有些目标程序以管理员身份运行，")
    say("普通权限无法向它们发送模拟点击和按键。")
    say("")
    say(">>> 接下来会弹出「用户账户控制」窗口，请点【是】 <<<")
    say("")

    try:
        os.remove(LAUNCH_LOG)              # 清掉旧日志，便于看本次结果
    except Exception:
        pass

    ret = launch_gui_elevated(_SRC_BASE)
    log("提权返回码 = %d" % ret)

    if ret > 32:
        say("已发起提权启动（返回码 %d），正在确认界面是否出现…" % ret)
        ok = False
        for _ in range(14):
            time.sleep(0.7)
            try:
                from quickscript.platform import wininput as wi
                if any(APP_TITLE_KEY in (w.get("title") or "")
                       for w in wi.list_windows(True)):
                    ok = True
                    break
            except Exception:
                pass
        if ok:
            say("界面已成功启动 ✓")
            return 0
        say("没有检测到界面窗口。请查看下面的启动日志，或按任务栏查找。")
        show_tail()
        safe_pause()
        return 1

    say("提权启动失败（返回码 %d）" % ret)
    hint = ERR_HINT.get(ret)
    if hint:
        say("  原因：%s" % hint)
    say("")
    say("可以尝试：")
    say("  1. 右键启动用的 BAT → 以管理员身份运行；")
    say("  2. 以管理员身份打开「命令提示符」，然后执行：")
    say('     cd /d "%s"' % HERE)
    say('     python -m quickscript')
    say("  3. 若安全软件拦截提权，请临时关闭其「程序启动保护」。")
    show_tail()
    safe_pause()
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        log("未捕获异常：\n%s" % traceback.format_exc())
        try:
            say("启动器出错，详情见 data/launch.log")
            say(traceback.format_exc())
        except Exception:
            pass
        sys.exit(1)
