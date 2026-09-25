# -*- coding: utf-8 -*-
"""QuickScript Studio —— 测试总入口

依次运行所有测试套件，汇总结果。

    python tests/run_all.py            运行全部
    python tests/run_all.py units ui   只运行指定套件
    python tests/run_all.py --list     列出可用套件

退出码：0 = 全部通过；1 = 有失败；2 = 仅有环境性跳过。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)


def _relax_console_encoding():
    """让本脚本在非 UTF-8 控制台下也能打印中文。

    GitHub Actions 的 windows-latest runner 控制台是 cp1252（英文 Windows），
    打印中文会抛 UnicodeEncodeError，导致「测试全过但脚本自己崩了」。
    其他测试套件早已这样处理，这个总入口此前漏掉了。

    errors="replace" 只是把打不出的字符换成 "?"，不影响测试结果判断。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


_relax_console_encoding()

# 套件名 -> (脚本文件, 说明)
SUITES = {
    "units": ("test_units.py", "单元自检：结构体/按键/图像/序列化/引擎逻辑/权限"),
    "ui": ("test_ui.py", "界面自检：真实启动界面并截图验证布局"),
    "e2e": ("test_e2e.py", "端到端：跨进程真实产生键鼠输入并核对"),
    "ime": ("test_ime.py", "输入法吞按键的修复验证"),
    "launch": ("test_launch.py", "启动链验证：文件齐全/批处理可解析/提权参数"),
}

ORDER = ["units", "ui", "ime", "launch", "e2e"]


def run_one(name):
    fname, desc = SUITES[name]
    path = os.path.join(HERE, fname)
    print()
    print("=" * 74)
    print("  [%s] %s" % (name, desc))
    print("=" * 74)
    if not os.path.isfile(path):
        print("  找不到 %s" % fname)
        return name, "缺失", -1, 0.0

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    t0 = time.time()
    try:
        proc = subprocess.run([sys.executable, path], cwd=PROJECT_ROOT,
                              env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=600)
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        print("  超时（>600 秒）")
        return name, "超时", -1, time.time() - t0

    # 只打印尾部，避免刷屏
    lines = out.strip().splitlines()
    for line in lines[-14:]:
        print("  " + line)
    if err.strip():
        print("  --- stderr ---")
        for line in err.strip().splitlines()[-6:]:
            print("  " + line)

    if rc == 0:
        status = "通过"
    elif rc == 2:
        status = "环境跳过"
    else:
        status = "失败"
    return name, status, rc, time.time() - t0


def main(argv):
    if "--list" in argv:
        print("可用测试套件：")
        for k in ORDER:
            print("  %-8s %s" % (k, SUITES[k][1]))
        return 0

    want = [a for a in argv if not a.startswith("-")]
    names = want or ORDER
    for n in names:
        if n not in SUITES:
            print("未知套件：%s（用 --list 查看）" % n)
            return 1

    print("=" * 74)
    print(" QuickScript Studio —— 测试总入口")
    print(" 项目根目录: %s" % PROJECT_ROOT)
    print(" 平台: %s  Python: %s" % (sys.platform, sys.version.split()[0]))
    print("=" * 74)

    results = []
    t_all = time.time()
    for n in names:
        results.append(run_one(n))

    print()
    print("=" * 74)
    print(" 汇总")
    print("=" * 74)
    for name, status, rc, secs in results:
        mark = {"通过": "OK  ", "环境跳过": "SKIP", "失败": "FAIL",
                "缺失": "MISS", "超时": "TIME"}.get(status, "?   ")
        print("  [%s] %-8s %-10s %6.1fs" % (mark, name, status, secs))

    failed = [r for r in results if r[1] == "失败" or r[1] in ("缺失", "超时")]
    skipped = [r for r in results if r[1] == "环境跳过"]
    print()
    print("  总计 %.1f 秒" % (time.time() - t_all))

    if failed:
        print("  有 %d 个套件未通过" % len(failed))
        return 1
    if skipped:
        print("  全部通过，但有 %d 个套件因环境限制跳过" % len(skipped))
        return 2
    print("  全部通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
