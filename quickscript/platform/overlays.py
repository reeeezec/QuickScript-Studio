# -*- coding: utf-8 -*-
"""QuickScript Studio —— 浮动交互组件

PickBar        屏幕顶部的小浮条：按 F8 连续拾取鼠标坐标/颜色，不遮挡目标程序操作
RegionCapture  全屏截图 + 拖框选区：用来制作找图模板、框选搜索区域
"""
from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import ttk

from . import vision
from . import wininput as wi

UI_FONT = "Microsoft YaHei UI"


class PickBar(tk.Toplevel):
    """屏幕顶部浮条。始终置顶、不抢焦点（显示后会自动把目标窗口切回前台）。"""

    def __init__(self, master, on_done, on_cancel, hint="把鼠标移到目标位置，按 F8 拾取"):
        super().__init__(master)
        self.on_done = on_done
        self.on_cancel = on_cancel
        self.picks = []
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
        try:
            self.attributes("-toolwindow", True)
        except Exception:
            pass
        self.configure(bg="#1a1d21")

        self._drag = (0, 0)
        bar = tk.Frame(self, bg="#1a1d21", padx=10, pady=6)
        bar.pack(fill="both", expand=True)

        self.hint_var = tk.StringVar(value=hint)
        title = tk.Label(bar, textvariable=self.hint_var, bg="#1a1d21", fg="#7fd7ff",
                         font=(UI_FONT, 10, "bold"))
        title.pack(side="left", padx=(0, 12))

        self.value_var = tk.StringVar(value="尚未拾取")
        value = tk.Label(bar, textvariable=self.value_var, bg="#1a1d21", fg="#ffd479",
                         font=("Consolas", 11, "bold"), width=34, anchor="w")
        value.pack(side="left")

        self.swatch = tk.Label(bar, text="      ", bg="#333333", relief="solid", bd=1)
        self.swatch.pack(side="left", padx=6)

        done = tk.Button(bar, text="✓ 完成", command=self._done, bg="#2f6f3f", fg="white",
                         activebackground="#3c8c50", activeforeground="white",
                         relief="flat", padx=12, font=(UI_FONT, 9, "bold"), cursor="hand2")
        done.pack(side="left", padx=(6, 4))
        cancel = tk.Button(bar, text="✕ 取消", command=self._cancel, bg="#6f2f2f", fg="white",
                           activebackground="#8c3c3c", activeforeground="white",
                           relief="flat", padx=12, font=(UI_FONT, 9), cursor="hand2")
        cancel.pack(side="left")

        tk.Label(bar, text="（左右拖动此条可移动）", bg="#1a1d21", fg="#6b7280",
                 font=(UI_FONT, 8)).pack(side="left", padx=(10, 0))

        for w in (bar, title, value, self.swatch):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)

        self.update_idletasks()
        w = self.winfo_reqwidth()
        sw = self.winfo_screenwidth()
        self.geometry("+%d+%d" % (max(0, (sw - w) // 2), 8))

    # -- 拖动 ------------------------------------------------------------
    def _start_drag(self, event):
        self._drag = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _do_drag(self, event):
        self.geometry("+%d+%d" % (event.x_root - self._drag[0], event.y_root - self._drag[1]))

    # -- 拾取 ------------------------------------------------------------
    def add_pick(self, x, y, color=None):
        self.picks.append((x, y, color))
        text = "脚本坐标 (%d, %d)" % (x, y)
        if color:
            text += "   %s" % vision.color_to_hex(color)
        if len(self.picks) > 1:
            text += "   [第 %d 次]" % len(self.picks)
        self.value_var.set(text)
        if color:
            self.swatch.configure(bg=vision.color_to_hex(color))
        self.hint_var.set("已拾取！继续移动鼠标再按 F8，或点「完成」")

    def _done(self):
        cb, self.on_done = self.on_done, None
        self.destroy()
        if cb:
            cb(self.picks)

    def _cancel(self):
        cb, self.on_cancel = self.on_cancel, None
        self.destroy()
        if cb:
            cb()


class RegionCapture(tk.Toplevel):
    """全屏截图 + 鼠标拖框选区。

    on_done(screen_rect)  screen_rect = (x, y, w, h)，屏幕绝对坐标
    """

    def __init__(self, master, on_done, on_cancel, hint="按住鼠标左键拖出要截取的区域"):
        super().__init__(master)
        self.on_done = on_done
        self.on_cancel = on_cancel
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
        self.configure(bg="black")

        vx, vy, vw, vh = self._virtual_desktop()
        self.vx, self.vy = vx, vy
        self.geometry("%dx%d+%d+%d" % (vw, vh, vx, vy))

        w, h, buf = wi.grab_screen(None)
        self.shot = (w, h, buf)
        tmp = os.path.join(self._temp_dir(), "capture_bg.ppm")
        wi.save_ppm(tmp, w, h, buf)
        self._tmp = tmp
        # PhotoImage 必须是实例属性，否则会被回收
        self.photo = tk.PhotoImage(file=tmp)

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg="black",
                                width=vw, height=vh)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")

        self.band = tk.Frame(self, bg="#111827")
        self.band.place(relx=0.5, y=10, anchor="n")
        tk.Label(self.band, text=hint + "　（Esc 或 右键 取消）", bg="#111827", fg="#7fd7ff",
                 font=(UI_FONT, 10, "bold"), padx=12, pady=6).pack()

        self.rect = None
        self.size_label = None
        self.start = None
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", lambda e: self._cancel())
        self.bind("<Escape>", lambda e: self._cancel())
        self.focus_force()
        self.grab_set()

    @staticmethod
    def _virtual_desktop():
        x = wi.user32.GetSystemMetrics(wi.SM_XVIRTUALSCREEN)
        y = wi.user32.GetSystemMetrics(wi.SM_YVIRTUALSCREEN)
        w = wi.user32.GetSystemMetrics(wi.SM_CXVIRTUALSCREEN)
        h = wi.user32.GetSystemMetrics(wi.SM_CYVIRTUALSCREEN)
        if w <= 1 or h <= 1:
            w, h, x, y = wi.user32.GetSystemMetrics(0), wi.user32.GetSystemMetrics(1), 0, 0
        return x, y, w, h

    @staticmethod
    def _temp_dir():
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "temp")
        os.makedirs(d, exist_ok=True)
        return d

    def _press(self, event):
        self.start = (event.x, event.y)
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#ffd479", width=2, fill="")
        if self.size_label:
            self.canvas.delete(self.size_label)
        self.size_label = None

    def _drag(self, event):
        if not self.start:
            return
        self.canvas.coords(self.rect, self.start[0], self.start[1], event.x, event.y)
        w = abs(event.x - self.start[0])
        h = abs(event.y - self.start[1])
        if self.size_label:
            self.canvas.delete(self.size_label)
        self.size_label = self.canvas.create_text(
            event.x + 8, event.y + 12, anchor="nw", text="%d × %d" % (w, h),
            fill="#ffd479", font=("Consolas", 11, "bold"))

    def _release(self, event):
        if not self.start:
            return
        x1, y1 = self.start
        x2, y2 = event.x, event.y
        x, y = min(x1, x2), min(y1, y2)
        w, h = abs(x2 - x1), abs(y2 - y1)
        cb, self.on_done = self.on_done, None
        self.grab_release()
        self.destroy()
        if w < 2 or h < 2:
            if cb:
                cb(None)
            return
        if cb:
            cb((self.vx + x, self.vy + y, w, h))

    def _cancel(self):
        cb, self.on_cancel = self.on_cancel, None
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if cb:
            cb()

    # -- 供调用方取用已截好的全屏画面 ------------------------------------
    def grab_region(self, rect):
        """从已经截好的全屏缓冲里裁剪 (x,y,w,h 屏幕坐标) → (w,h,bytes)"""
        w, h, buf = self.shot
        return vision.crop_bgra(w, h, buf, rect[0] - self.vx, rect[1] - self.vy, rect[2], rect[3])
