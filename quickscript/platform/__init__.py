# -*- coding: utf-8 -*-
"""平台层 —— 与操作系统交互的部分。

这一层是唯一直接调用 Win32 API 的地方，便于将来移植到其它平台：
    wininput  键鼠注入、窗口查询、屏幕截取、全局热键、权限与输入法检查
    vision    找色 / 找图（自带 PNG/BMP/PPM 编解码，零第三方依赖）
    overlays  屏幕浮层：坐标拾取、区域框选
"""
from __future__ import annotations

from . import overlays, vision, wininput

__all__ = ["wininput", "vision", "overlays"]
