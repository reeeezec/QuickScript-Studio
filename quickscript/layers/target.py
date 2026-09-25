# -*- coding: utf-8 -*-
"""目标层 —— 「对谁操作」以及「坐标怎么算」

职责：
  1. 解析绑定目标（按窗口标题/类名查找，或使用屏幕绝对坐标）
  2. 维护坐标空间：脚本坐标 <-> 屏幕坐标
  3. 提供正确的截屏区域（供触发层做找色/找图）

坐标模式
--------
    SCREEN  屏幕绝对坐标：脚本里的 (x, y) 就是屏幕像素位置。
            简单直接，但目标窗口一移动脚本就失效。

    WINDOW  窗口相对坐标：脚本里的 (x, y) 相对「原点」计算。
            原点默认跟随绑定窗口的客户区左上角，窗口移动/缩放后依然可用；
            也可以用 fixed_origin 把原点钉死在某个屏幕位置（适合画布位置固定、
            但窗口标题不好绑定的情况）。

对外只暴露 to_screen() / to_script()，上层（流程层、动作层）不需要知道细节。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..platform import wininput as wi

# 坐标模式常量
SCREEN = "screen"
WINDOW = "window"

COORD_MODES = (WINDOW, SCREEN)

MODE_LABELS = {
    WINDOW: "窗口相对坐标",
    SCREEN: "屏幕绝对坐标",
}


@dataclass
class TargetSpec:
    """目标描述：绑定哪个窗口、原点在哪、是否自动前置。"""

    coord_mode: str = WINDOW
    window_title: str = ""
    window_match: str = "contains"     # contains | exact | startswith
    window_class: str = ""
    bring_to_front: bool = True
    use_fixed_origin: bool = False
    origin_x: int = 0
    origin_y: int = 0

    # -- 序列化 ----------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "coord_mode": self.coord_mode,
            "window_title": self.window_title,
            "window_match": self.window_match,
            "window_class": self.window_class,
            "bring_to_front": self.bring_to_front,
            "use_fixed_origin": self.use_fixed_origin,
            "origin_x": self.origin_x,
            "origin_y": self.origin_y,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TargetSpec":
        data = data or {}
        mode = data.get("coord_mode", WINDOW)
        if mode not in COORD_MODES:
            mode = WINDOW
        match = data.get("window_match", "contains")
        if match not in ("contains", "exact", "startswith"):
            match = "contains"
        return cls(
            coord_mode=mode,
            window_title=str(data.get("window_title") or ""),
            window_match=match,
            window_class=str(data.get("window_class") or ""),
            bring_to_front=bool(data.get("bring_to_front", True)),
            use_fixed_origin=bool(data.get("use_fixed_origin", False)),
            origin_x=int(data.get("origin_x", 0) or 0),
            origin_y=int(data.get("origin_y", 0) or 0),
        )

    def copy(self) -> "TargetSpec":
        return TargetSpec.from_dict(self.to_dict())


@dataclass
class BoundTarget:
    """已经解析好的目标：窗口句柄 + 实际坐标原点。"""

    spec: TargetSpec
    hwnd: int = 0
    client_origin: tuple = (0, 0)      # 客户区左上角的屏幕坐标
    client_size: tuple = (0, 0)        # 客户区尺寸
    origin: tuple = (0, 0)             # 实际使用的坐标原点（屏幕坐标）
    bound: bool = False                # 是否成功绑定到窗口

    # -- 坐标换算 --------------------------------------------------------
    def to_screen(self, x, y):
        return int(self.origin[0] + x), int(self.origin[1] + y)

    def to_script(self, sx, sy):
        return int(sx - self.origin[0]), int(sy - self.origin[1])

    @property
    def is_screen_mode(self) -> bool:
        return self.spec.coord_mode == SCREEN

    # -- 截屏区域 --------------------------------------------------------
    def capture_rect(self):
        """返回应该截取的区域 (left, top, w, h)。

        窗口相对模式下只截客户区，既更快也更准；
        屏幕模式或未绑定时截整个虚拟桌面。
        """
        if self.spec.coord_mode == WINDOW and self.hwnd:
            rect = wi.window_client_rect(self.hwnd)
            if rect:
                self.client_origin = (rect[0], rect[1])
                self.client_size = (rect[2], rect[3])
                self.origin = (rect[0], rect[1]) if not self.spec.use_fixed_origin else self.origin
                return rect
        return None

    # -- 描述 ------------------------------------------------------------
    def describe(self) -> str:
        spec = self.spec
        if self.is_screen_mode:
            return "坐标模式：屏幕绝对坐标"
        if self.hwnd:
            title = wi.window_title(self.hwnd)
            if len(title) > 28:
                title = title[:28] + "…"
            return "已绑定窗口：「%s」  原点 (%d,%d)  画面 %dx%d" % (
                title, self.origin[0], self.origin[1],
                self.client_size[0], self.client_size[1])
        if spec.use_fixed_origin:
            return "固定原点 (%d,%d)（未绑定窗口）" % (spec.origin_x, spec.origin_y)
        return "未绑定窗口 → 按屏幕绝对坐标执行"


class TargetResolver:
    """把 TargetSpec 解析成 BoundTarget（含窗口查找与原点计算）。"""

    def __init__(self, spec: TargetSpec):
        self.spec = spec
        self.bound = BoundTarget(spec=spec)

    def refresh(self, activate: bool = False) -> bool:
        """重新解析。返回是否成功绑定到窗口。"""
        spec = self.spec
        bt = self.bound
        bt.spec = spec

        if spec.coord_mode == SCREEN:
            bt.hwnd = 0
            bt.origin = (0, 0)
            bt.bound = False
            return False

        title = (spec.window_title or "").strip()
        cls = (spec.window_class or "").strip()
        hwnd = wi.find_window(title, spec.window_match, cls) if (title or cls) else 0
        bt.hwnd = int(hwnd or 0)

        if bt.hwnd:
            rect = wi.window_client_rect(bt.hwnd)
            if rect:
                bt.client_origin = (rect[0], rect[1])
                bt.client_size = (rect[2], rect[3])
            if activate:
                wi.activate_window(bt.hwnd)
                time.sleep(0.15)
                rect = wi.window_client_rect(bt.hwnd)
                if rect:
                    bt.client_origin = (rect[0], rect[1])
                    bt.client_size = (rect[2], rect[3])

        if spec.use_fixed_origin:
            bt.origin = (int(spec.origin_x), int(spec.origin_y))
        elif bt.hwnd:
            bt.origin = (bt.client_origin[0] + int(spec.origin_x),
                         bt.client_origin[1] + int(spec.origin_y))
        else:
            bt.origin = (0, 0)

        bt.bound = bool(bt.hwnd)
        return bt.bound
