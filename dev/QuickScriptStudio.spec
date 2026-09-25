# -*- coding: utf-8 -*-
"""PyInstaller 打包配置（spec 文件）

用法：
    pyinstaller --noconfirm --clean QuickScriptStudio.spec

产物：
    dist/QuickScriptStudio.exe     单文件，双击即用

设计说明
--------
* **onefile 模式**：用户要的是"以 exe 形式打开"，单文件最省事 —— 拷到哪都能跑。
  代价是每次启动会解压到临时目录（首次启动约 1~2 秒），这是可接受的取舍；
  若更在意启动速度，把 EXE(...) 换成 COLLECT(...) 即为 onedir 模式。

* **windowed (--noconsole)**：GUI 程序不该带黑框。
  启动失败的信息由程序自身写入 data/launch.log，不会静默消失。

* **数据目录**：EXE 所在目录通常可写（用户会把 exe 放到自己的文件夹），
  此时数据存在 exe 旁边的 data/，可随 U 盘带走；
  若放在 Program Files 等只读位置，metadata.data_dir() 会自动回退到
  %APPDATA%\\QuickScriptStudio —— 两种情况都能正常工作。

* **不打包 examples/docs**：这些是给开发者看的，运行时用不到，减体积。
"""
import os

from PyInstaller.utils.hooks import collect_submodules

# 项目根目录
# 用 spec 文件自身的位置推算路径，这样从任何目录调用都正确。
# 布局：<ROOT>/dev/QuickScriptStudio.spec，入口 <ROOT>/dev/qs.py
# SPECPATH 是 PyInstaller 注入的全局变量，值为 spec 所在目录。
SPEC_DIR = os.path.abspath(SPECPATH)
ROOT = os.path.dirname(SPEC_DIR)

# 显式收集本项目包，确保四层与平台层都被打进去
hiddenimports = (
    collect_submodules("quickscript")
)

# 需要一并打包的数据文件：(源, 目标目录)
# 目前运行时不依赖外部数据文件，templates 由用户自己截取。
datas = []

a = Analysis(
    # 入口必须用 qs.py：quickscript/__main__.py 用的是相对导入，
    # 被 PyInstaller 当顶层脚本执行时会因没有父包而失败。
    [os.path.join(SPEC_DIR, "qs.py")],
    pathex=[ROOT, SPEC_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # tkinter 用不到的一堆模块，排除掉能明显减小体积
    excludes=[
        "numpy", "PIL", "cv2", "matplotlib", "scipy", "pandas",
        "test", "unittest", "pydoc", "doctest",
        "email", "html", "http", "xmlrpc", "pdb",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="QuickScriptStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                # 不用 UPX：容易触发杀毒误报
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # 无控制台窗口（GUI 程序）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 版本资源（可选，没有该文件时自动跳过）
    version=None,
    icon=os.path.join(SPEC_DIR, "icon.ico") if os.path.isfile(
        os.path.join(SPEC_DIR, "icon.ico")) else None,
)
