# -*- coding: utf-8 -*-
"""QuickScript Studio —— 通用键鼠自动化工具

分层架构：
    layers.actions    动作层 —— 鼠标 / 键盘的原子动作
    layers.flow       流程层 —— 等待 / 循环 / 跳转 / 停止
    layers.triggers   触发层 —— 找色 / 找图等条件判断
    layers.target     目标层 —— 窗口绑定与坐标模式

    platform.*        平台层 —— Win32 输入注入、窗口、截屏、热键、图像识别
    model             脚本数据模型与格式定义
    runtime           执行引擎（组合上述各层）
    storage           脚本库（多脚本管理与导入导出）
    ui                Tkinter 图形界面
"""
from __future__ import annotations

from .metadata import (APP_NAME, APP_NAME_EN, APP_NAME_ZH, APP_NAME_SHORT,
                       VERSION, VERSION_TUPLE, RELEASE_DATE,
                       SCRIPT_FORMAT_VERSION, MUTEX_NAME, WINDOW_TITLE_KEY,
                       PROJECT_URL, LICENSE_NAME, about_text, version_string)

__all__ = [
    "APP_NAME", "APP_NAME_EN", "APP_NAME_ZH", "APP_NAME_SHORT",
    "VERSION", "VERSION_TUPLE", "RELEASE_DATE",
    "SCRIPT_FORMAT_VERSION", "MUTEX_NAME", "WINDOW_TITLE_KEY",
    "PROJECT_URL", "LICENSE_NAME", "about_text", "version_string",
]

__version__ = VERSION
