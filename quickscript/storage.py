# -*- coding: utf-8 -*-
"""QuickScript Studio —— 脚本库（多脚本管理 / 导入导出）

目录结构（默认在程序目录下，不可写时退回用户配置目录）：

    data/
      library.json          脚本清单（脚本名列表 + 当前选中）
      scripts/<名称>.json   每份脚本
      templates/*.png       找图用的模板图片
      temp/                 运行时临时文件（全屏截图缓冲）
      trash/                删除的脚本（可手动恢复）
      launch.log            启动器日志

路径统一由 metadata 提供，便于整体迁移或做便携模式。
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime

from . import metadata
from .model import Script, ScriptError, DEFAULT_SCRIPT_NAME

_INVALID = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def ensure_dirs():
    """确保所有数据目录存在。"""
    for d in (metadata.data_dir(), metadata.SCRIPT_DIR(), metadata.TEMPLATE_DIR(),
              metadata.TEMP_DIR(), metadata.TRASH_DIR()):
        os.makedirs(d, exist_ok=True)


def safe_name(name: str) -> str:
    """把脚本名变成安全的文件名。"""
    name = _INVALID.sub("_", str(name or "").strip())
    name = name.strip(" .")
    if not name:
        name = DEFAULT_SCRIPT_NAME
    if len(name) > 60:
        name = name[:60]
    return name


class LibraryError(Exception):
    pass


class ScriptLibrary:
    """脚本库：管理 data/scripts 下的所有脚本。"""

    def __init__(self):
        ensure_dirs()
        self._meta = self._read_meta()

    # -- 清单 ------------------------------------------------------------
    @property
    def _lib_file(self):
        # 每次读取，保证测试或运行时改了 data_dir 也能生效
        return metadata.LIBRARY_FILE()

    @property
    def _script_dir(self):
        return metadata.SCRIPT_DIR()

    def _read_meta(self):
        path = self._lib_file
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("scripts", [])
                    data.setdefault("current", "")
                    return data
            except Exception:
                pass
        return {"scripts": [], "current": ""}

    def _write_meta(self):
        ensure_dirs()
        path = self._lib_file
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._meta, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def names(self):
        """磁盘上实际存在的脚本名列表（同时修正清单）。"""
        disk = set()
        d = self._script_dir
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.lower().endswith(".json"):
                    disk.add(os.path.splitext(fn)[0])
        listed = [n for n in self._meta.get("scripts", []) if n in disk]
        extra = sorted(disk - set(listed))
        merged = listed + extra
        if merged != self._meta.get("scripts"):
            self._meta["scripts"] = merged
            self._write_meta()
        return merged

    def current(self):
        cur = self._meta.get("current") or ""
        return cur if cur in self.names() else ""

    def set_current(self, name):
        self._meta["current"] = name or ""
        self._write_meta()

    def path_for(self, name):
        return os.path.join(self._script_dir, safe_name(name) + ".json")

    def exists(self, name):
        return os.path.isfile(self.path_for(name))

    # -- 读写 ------------------------------------------------------------
    def save(self, script: Script):
        name = safe_name(script.name)
        script.name = name
        script.save(self.path_for(name))
        names = self.names()
        if name not in names:
            names.append(name)
            self._meta["scripts"] = names
        self._meta["current"] = name
        self._write_meta()
        return self.path_for(name)

    def load(self, name) -> Script:
        path = self.path_for(name)
        if not os.path.isfile(path):
            raise LibraryError("脚本不存在：%s" % name)
        sc = Script.load(path)
        sc.name = name
        return sc

    def delete(self, name):
        """删除脚本（移入 trash 以便恢复）。"""
        path = self.path_for(name)
        if os.path.isfile(path):
            backup = metadata.TRASH_DIR()
            os.makedirs(backup, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.move(path,
                        os.path.join(backup, "%s_%s.json" % (safe_name(name), stamp)))
        names = [n for n in self.names() if n != name]
        self._meta["scripts"] = names
        if self._meta.get("current") == name:
            self._meta["current"] = names[0] if names else ""
        self._write_meta()

    def rename(self, old, new):
        new = safe_name(new)
        if new == old:
            return new
        if self.exists(new):
            raise LibraryError("已存在同名脚本：%s" % new)
        sc = self.load(old)
        sc.name = new
        self.save(sc)
        self.delete(old)
        self._meta["current"] = new
        self._write_meta()
        return new

    # -- 导入导出 --------------------------------------------------------
    def export_to(self, script_or_path, target_path):
        """导出为独立的 .json 文件（可直接分享）。"""
        if isinstance(script_or_path, Script):
            data = script_or_path.to_dict()
        elif isinstance(script_or_path, dict):
            data = script_or_path
        else:
            with open(script_or_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        if not isinstance(data, dict):
            raise LibraryError("导出内容不是有效的脚本")
        tmp = target_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target_path)

    def import_from(self, source_path, new_name=None):
        """从 JSON 文件导入（自动处理版本迁移与重名）。"""
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise LibraryError("JSON 解析失败（第 %d 行）：%s" % (exc.lineno, exc.msg))
        try:
            sc = Script.from_dict(data)
        except ScriptError as exc:
            raise LibraryError(str(exc))

        name = safe_name(new_name or sc.name or DEFAULT_SCRIPT_NAME)
        if self.exists(name):
            base, i = name, 2
            while self.exists("%s (%d)" % (base, i)):
                i += 1
            name = "%s (%d)" % (base, i)
        sc.name = name
        self.save(sc)
        return sc, name

    # -- 模板图片 --------------------------------------------------------
    def template_path(self, prefix="template"):
        ensure_dirs()
        import time
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = "%s_%s" % (safe_name(prefix), stamp)
        path = os.path.join(metadata.TEMPLATE_DIR(), base + ".png")
        i = 2
        while os.path.exists(path):
            path = os.path.join(metadata.TEMPLATE_DIR(), "%s_%d.png" % (base, i))
            i += 1
        return path

    def list_templates(self):
        ensure_dirs()
        out = []
        d = metadata.TEMPLATE_DIR()
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith((".png", ".bmp", ".ppm")):
                out.append(os.path.join(d, fn))
        return out
