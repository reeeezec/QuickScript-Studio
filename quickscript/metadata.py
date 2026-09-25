# -*- coding: utf-8 -*-
"""QuickScript Studio —— 项目元信息与路径约定

集中管理项目名、版本号、配置目录、互斥体名等，避免散落在各处。
"""
from __future__ import annotations

import os
import sys

# --------------------------------------------------------------------------
# 项目标识
# --------------------------------------------------------------------------

APP_NAME_EN = "QuickScript Studio"
APP_NAME_ZH = "快捷脚本开发器"
APP_NAME = "%s / %s" % (APP_NAME_EN, APP_NAME_ZH)
APP_NAME_SHORT = APP_NAME_EN

VERSION = "0.1.0"
VERSION_TUPLE = (0, 1, 0)
RELEASE_DATE = "2025-09-25"

# 脚本格式版本：写入 JSON 的 version 字段
SCRIPT_FORMAT_VERSION = 2

# 单实例互斥体名
MUTEX_NAME = "Local\\QuickScriptStudio.SingleInstance"

# 窗口标题里用于识别的关键字（单实例检测 / 自己启动的窗口不要误绑）
WINDOW_TITLE_KEY = APP_NAME_EN

PROJECT_URL = "https://github.com/reeeezec/QuickScript-Studio"
LICENSE_NAME = "MIT"

DESCRIPTION_EN = ("A generic keyboard & mouse automation tool for Windows. "
                  "Compose repeatable desktop operations as editable scripts.")
DESCRIPTION_ZH = "通用键鼠自动化工具：把重复的桌面操作编排成可编辑的脚本并自动执行。"


# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------

def app_dir() -> str:
    """程序所在目录（打包成 exe 后是 exe 所在目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    """数据目录。

    优先使用程序目录下的 data（便携模式，方便放 U 盘里带走）；
    若该位置不可写（例如装在 Program Files），退回用户配置目录。
    """
    portable = os.path.join(app_dir(), "data")
    if _writable(portable):
        return portable
    base = (os.environ.get("APPDATA")
            or os.path.expanduser("~"))
    fallback = os.path.join(base, "QuickScriptStudio")
    return fallback


def _writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_probe")
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
        return True
    except Exception:
        return False


def sub_dir(*parts) -> str:
    p = os.path.join(data_dir(), *parts)
    os.makedirs(p, exist_ok=True)
    return p


SCRIPT_DIR = lambda: sub_dir("scripts")          # noqa: E731
TEMPLATE_DIR = lambda: sub_dir("templates")      # noqa: E731
TEMP_DIR = lambda: sub_dir("temp")               # noqa: E731
TRASH_DIR = lambda: sub_dir("trash")             # noqa: E731
LIBRARY_FILE = lambda: os.path.join(data_dir(), "library.json")   # noqa: E731
LAUNCH_LOG = lambda: os.path.join(data_dir(), "launch.log")       # noqa: E731


def ensure_dirs() -> None:
    for fn in (SCRIPT_DIR, TEMPLATE_DIR, TEMP_DIR, TRASH_DIR):
        fn()


def version_string() -> str:
    return "v%s" % VERSION


def about_text() -> str:
    return (
        "%s\n\n"
        "%s\n\n"
        "版本 %s（%s）\n"
        "授权 %s\n"
        "%s"
        % (APP_NAME, DESCRIPTION_ZH, VERSION, RELEASE_DATE, LICENSE_NAME, PROJECT_URL)
    )
