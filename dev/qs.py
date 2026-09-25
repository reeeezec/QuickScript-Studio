#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""QuickScript Studio —— 打包/直接运行用的入口脚本

为什么不直接把 quickscript/__main__.py 当打包入口：
    该文件使用相对导入（from .metadata import ...），
    而 PyInstaller 会把入口脚本当作顶层模块 __main__ 执行，
    此时没有父包，相对导入会抛
    "attempted relative import with no known parent package"。
    所以这里用一个薄壳，先按包的方式导入再调用。

用法：
    python qs.py                启动图形界面
    python qs.py --version      查看版本
    python qs.py --check        只做环境自检
"""
import os
import sys

# 保证无论从哪个目录启动，都能找到 quickscript 包

# --- 源码位置自适应 ---------------------------------------------------------
# 布局可能有两种：
#   A) 入口与 quickscript/ 同目录（开发时的仓库根）
#   B) 源码在 ../src/ 下（分层后的交付目录）
# 这里把两种候选位置都加入 sys.path，两种布局都能直接运行。
_here = os.path.dirname(os.path.abspath(__file__))
for _cand in (
    _here,                                   # A: 同目录
    os.path.join(_here, "src"),             # A': 子目录 src/
    os.path.join(os.path.dirname(_here), "src"),   # B: 上级 src/
    os.path.dirname(_here),                 # B': 上级目录
):
    if os.path.isdir(os.path.join(_cand, "quickscript")):
        if _cand not in sys.path:
            sys.path.insert(0, _cand)
        break
# ---------------------------------------------------------------------------

from quickscript.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
