# -*- coding: utf-8 -*-
"""QuickScript Studio 程序入口。

    python -m quickscript          启动图形界面
    python -m quickscript --check  只做环境自检，不打开界面
    python -m quickscript --version
"""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--version" in argv or "-V" in argv:
        from .metadata import APP_NAME, VERSION, RELEASE_DATE, LICENSE_NAME
        print("%s %s (%s)" % (APP_NAME, VERSION, RELEASE_DATE))
        print("License: %s" % LICENSE_NAME)
        return 0

    if "--check" in argv:
        return _env_check()

    # 图形界面需要 DPI 感知，必须在使用任何坐标 API 之前设置
    from .platform import wininput as wi
    wi.enable_dpi_awareness()

    from .metadata import ensure_dirs
    ensure_dirs()

    from .ui import App
    app = App()
    app.mainloop()
    return 0


def _env_check() -> int:
    """不开界面，直接报告环境状态。"""
    from .metadata import APP_NAME, VERSION, data_dir, about_text
    from .platform import wininput as wi

    wi.enable_dpi_awareness()
    print("=" * 62)
    print(" %s  %s" % (APP_NAME, VERSION))
    print("=" * 62)
    print("数据目录 : %s" % data_dir())
    print("运行权限 : %s" % ("管理员" if wi.is_admin() else "普通用户"))
    print("显示缩放 : DPI %d" % wi.system_dpi())
    print()

    ok, why = wi.test_input_injection()
    print("模拟输入 : %s" % ("正常" if ok else "被拦截"))
    if not ok:
        for line in why.split("\n"):
            print("           %s" % line)

    busy = [n for n, vk in (("F8", 0x77), ("F9", 0x78), ("F10", 0x79))
            if not wi.test_hotkey_available(vk)]
    print("全局热键 : %s" % ("F8/F9/F10 可用" if not busy
                            else "已被占用：%s" % "、".join(busy)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
