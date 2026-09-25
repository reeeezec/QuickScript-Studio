"""端到端测试的「被操作目标」进程（模拟目标窗口）。

独立进程运行，这样被测程序绑定它时走的是真实的跨进程路径
（真实目标程序也一定在另一个进程里）。

用法：python e2e_target.py <信息文件> <事件文件> <x> <y> <宽> <高>

- 启动后把窗口信息（hwnd / 客户区原点 / 尺寸 / 标题）写入 <信息文件>
- 之后每 150ms 把记录到的输入事件写入 <事件文件>（JSON）
- 收到 Ctrl+C 或 stdin 关闭时退出
"""
from __future__ import annotations

# 由 _move_tests.py 自动迁移而来。测试位于 tests/，项目根目录在其上一级。
import os as _os
import sys as _sys

PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, PROJECT_ROOT)


import json
import os
import sys
import time
import tkinter as tk

# path 由顶部 bootstrap 处理

from quickscript.platform import wininput as wi

wi.enable_dpi_awareness()

INFO_FILE = sys.argv[1]
EVENT_FILE = sys.argv[2]
X, Y, W, H = (int(v) for v in sys.argv[3:7])
TITLE = sys.argv[7] if len(sys.argv) > 7 else "E2E_TARGET_WINDOW"


class Target:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(TITLE)
        self.root.geometry("%dx%d+%d+%d" % (W, H, X, Y))
        self.root.configure(bg="#eef2f7")

        self.click_count = 0
        self.press = []
        self.release = []
        self.drag = []
        self.motion = []
        self.keys = []
        self._press_t = None

        self.btn = tk.Button(self.root, text="目标按钮",
                             font=("Microsoft YaHei UI", 12), command=self._on_click)
        self.btn.place(x=60, y=50, width=200, height=80)

        self.label = tk.Label(self.root, text="", bg="#eef2f7",
                              font=("Microsoft YaHei UI", 10))
        self.label.place(x=60, y=150)

        self.root.bind("<ButtonPress-1>", self._on_press)
        self.root.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<B1-Motion>", self._on_drag)
        self.root.bind("<Motion>", self._on_motion)
        self.root.bind("<KeyPress>", lambda e: self.keys.append(("down", e.keysym)))
        self.root.bind("<KeyRelease>", lambda e: self.keys.append(("up", e.keysym)))
        self.root.update_idletasks()
        self.root.update()

    def _on_click(self):
        self.click_count += 1
        self.label.configure(text="已点击 %d 次" % self.click_count)

    def _on_press(self, e):
        self._press_t = time.perf_counter()
        self.press.append((e.x_root, e.y_root))

    def _on_release(self, e):
        hold = (time.perf_counter() - self._press_t) if self._press_t else None
        self.release.append((e.x_root, e.y_root, hold))

    def _on_drag(self, e):
        # 第一个 B1-Motion 才是"按下的那个点"，按下瞬间的位置也一并记下来，
        # 这样测试才能准确核对拖动起点。
        if not self.drag:
            self.drag.append((self.press[-1][0], self.press[-1][1]) if self.press else
                             (e.x_root, e.y_root))
        self.drag.append((e.x_root, e.y_root))

    def _on_motion(self, e):
        self.motion.append((e.x_root, e.y_root))

    def hwnd(self):
        inner = int(self.root.winfo_id())
        return int(wi.user32.GetParent(inner) or inner)

    def snapshot(self):
        return {
            "click_count": self.click_count,
            "press": self.press,
            "release": self.release,
            "drag": self.drag,
            "motion": self.motion[-60:],     # 移动事件很多，只留尾部
            "keys": self.keys,
        }

    def write_events(self):
        tmp = EVENT_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False)
        os.replace(tmp, EVENT_FILE)


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
    t = Target()
    hwnd = t.hwnd()
    info = {
        "hwnd": hwnd,
        "title": wi.window_title(hwnd),
        "client": list(wi.window_client_rect(hwnd) or (0, 0, 0, 0)),
        "rect": list(wi.window_rect(hwnd) or (0, 0, 0, 0)),
        "pid": os.getpid(),
    }
    tmp = INFO_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False)
    os.replace(tmp, INFO_FILE)

    last = 0.0
    while True:
        try:
            t.root.update_idletasks()
            t.root.update()
        except tk.TclError:
            break
        now = time.time()
        if now - last > 0.15:
            last = now
            try:
                t.write_events()
            except Exception:
                pass
        time.sleep(0.005)
    try:
        t.write_events()
    except Exception:
        pass


if __name__ == "__main__":
    main()
