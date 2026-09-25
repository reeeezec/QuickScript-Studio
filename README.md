<div align="center">

# QuickScript Studio

**快捷脚本开发器**

A generic keyboard & mouse automation tool for Windows · 通用键鼠自动化工具

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey.svg)]()
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)]()

[中文](#中文文档) · [English](#english)

</div>

---

## ⚠️ 合规与免责声明 / Compliance & Disclaimer

> **请在使用前完整阅读本节。**
>
> 1. **本项目是通用的桌面自动化工具**，与任何游戏、网站、平台均无关联，
>    也不针对任何特定软件做适配或绕过。
> 2. **严禁用于任何违反法律法规、服务条款或破坏公平性的用途**，
>    包括但不限于：游戏外挂与作弊、刷量刷单、抢购秒杀、
>    绕过验证码或风控、未授权访问他人系统、批量注册、发送垃圾信息。
> 3. **请仅在你拥有合法权限的设备与软件环境中使用**。
>    在他人设备、生产系统或受保护环境中使用前，务必取得明确授权。
> 4. **使用本工具产生的全部后果由使用者自行承担**。
>    作者与贡献者不对任何直接或间接损失负责，亦不提供任何形式的担保。
> 5. 本软件按 **MIT 许可证** 发布，即「按原样提供」，不附带任何明示或暗示的保证。
> 6. 若你不同意上述条款，请**立即停止使用并删除本软件**。

> **Read this section before use.**
>
> 1. This is a **generic desktop automation tool**. It is not associated with, and
>    does not target or circumvent, any game, website, or platform.
> 2. **Do not use it for anything unlawful, against terms of service, or unfair** —
>    including game cheating, click/engagement fraud, ticket scalping,
>    bypassing CAPTCHAs or anti-abuse systems, unauthorized access to systems,
>    mass registration, or spam.
> 3. **Use it only on devices and software you are authorized to control.**
>    Obtain explicit permission before running it on someone else's machine
>    or on production systems.
> 4. **You are solely responsible for any consequences.**
>    The authors and contributors accept no liability for any direct or
>    indirect damages, and provide no warranty of any kind.
> 5. Released under the **MIT License** — provided "as is", without warranty.
> 6. If you do not agree, **stop using and delete this software immediately**.

---

# 中文文档

## 1. 项目解决什么问题

日常工作和测试里有大量**重复、机械的键鼠操作**：

- 每次都要在同一个软件里点同样的几个按钮、填一样的字段
- 手动重复几十上百次点击来做界面测试，手酸且容易漏
- 需要在没有提供 API 的老旧软件里批量处理数据，只能靠模拟键鼠
- 想用脚本自动化，但现有工具要么要写代码、要么录制的脚本无法精细调整

**QuickScript Studio 把这类重复操作变成可编辑的脚本：**

| 问题 | 本项目怎么做 |
|---|---|
| 不会写代码 | 图形界面点选添加步骤，**按 F8 直接拾取屏幕坐标**，不用手算像素 |
| 录制工具不好调 | 每一步的**参数都能精确设置**（按下时长、连击间隔、移动耗时、抖动） |
| 窗口一移动脚本就废 | **窗口相对坐标**模式：绑定目标窗口，窗口移动/缩放后依然可用 |
| 需要判断再操作 | **找色/找图**条件分支，命中与否可跳转、可停止 |
| 流程一长就看不懂 | 每个步骤可写**备注**，还能一键查看全部备注 |
| 想要复杂流程 | 循环、标签跳转，支持嵌套 |

- **零第三方依赖**：只用 Python 标准库（tkinter / ctypes / zlib / json），装好 Python 就能跑
- **脚本是纯 JSON**：可以用文本编辑器改，也能用 Git 做版本管理

---

## 2. 主要功能

### 2.1 四层架构

代码与脚本格式都按职责分为四层，边界清晰、便于扩展：

| 层 | 职责 | 步骤类型 |
|---|---|---|
| **动作层** | 产生输入 | `move` `click` `drag` `wheel` `key` `key_down` `key_up` |
| **流程层** | 控制走向 | `delay` `loop_begin` `loop_end` `label` `goto` `stop` |
| **触发层** | 条件分支 | `if_color` `if_image` |
| **目标层** | 对谁操作、坐标怎么算 | 不体现在步骤里，而是脚本级 `target` 设置 |

### 2.2 鼠标

| 步骤 | 可调参数 |
|---|---|
| 移动鼠标 | 目标坐标、移动耗时、随机抖动 |
| 点击 | 目标坐标、鼠标键（左/右/中/侧键）、**按下时长**、点击次数、连击间隔、移动耗时 |
| 拖动 | 起点、终点、鼠标键、拖动耗时、中间步数、抖动 |
| 滚轮 | 滚动格数、次数、间隔 |

### 2.3 键盘

- 支持 **170 个按键名**：字母数字、`F1`~`F24`、方向键、小键盘、修饰键，还有中文别名（`空格`/`回车`/`上`/`下`）
- **组合键**：`ctrl+shift+a`、`alt+F4`
- **按住时长**、连发次数、连发间隔
- **按住不放 / 松开按键**：适合需要持续按住的操作
- 注入时同时提供虚拟键码与**硬件扫描码**，兼容只读扫描码的程序

### 2.4 流程控制

- **等待**：可加随机浮动，让节奏更自然
- **循环**：`循环开始` / `循环结束` 配对，**支持嵌套**，次数填 `0` 表示无限循环
- **标签跳转**：`标签` 定义位置，`跳转` 转到它
- **停止脚本**
- 内置**死循环保护**（超过 30 万步自动停止）

### 2.5 条件触发

| 步骤 | 说明 |
|---|---|
| 如果某点颜色符合 | 判断指定坐标的颜色，可设容差（0~255） |
| 如果画面上有图片 | 在画面中查找模板图片，可设最低匹配度与搜索区域 |

两者都支持 **命中 / 未命中 → 继续 / 跳转到标签 / 停止脚本**。
找图功能**自带 PNG/BMP/PPM 解码**，不需要 opencv 或 numpy。

### 2.6 两种坐标模式

| 模式 | 说明 | 适用场景 |
|---|---|---|
| **窗口相对坐标**（推荐） | 坐标相对目标窗口客户区左上角，窗口移动/缩放后依然可用 | 绝大多数情况 |
| **屏幕绝对坐标** | 坐标就是屏幕像素位置 | 目标位置完全固定 |

窗口相对模式还支持**固定原点**：把原点钉死在屏幕某个位置，不随窗口移动。

### 2.7 全局热键

| 热键 | 功能 |
|---|---|
| **F8** | 拾取鼠标当前位置的坐标（并可同时取色），连续拾取 |
| **F9** | 开始运行脚本 |
| **F10** | 紧急停止（**会自动松开所有按住的键**） |

### 2.8 脚本管理

- 多脚本管理：新建、保存、另存为、重命名、删除（删除进回收目录，可恢复）
- **导入 / 导出 JSON**，方便备份与分享
- 每个步骤可写**备注**（最长 300 字），列表里有独立备注列，菜单可**一键查看全部备注**并双击跳转
- 脚本格式**带 `version` 字段**，旧版本自动迁移

### 2.9 环境自检

自动化最怕「跑完了但目标程序没反应」。本项目内置自检，明确报告四类问题：

| 检查项 | 说明 |
|---|---|
| **模拟输入** | 真实移动一次鼠标并读回位置，确认注入没被拦截 |
| **运行权限** | 检测目标程序是否以管理员权限运行（UIPI 会拦截低权限进程的输入） |
| **键盘输入法** | 中文输入法会把注入按键吞成 `VK_PROCESSKEY`，运行前自动切英文布局 |
| **全局热键** | 检测 F8/F9/F10 是否被其它程序占用 |

菜单 **「帮助 → 环境自检」** 可随时手动检查。

---

## 3. 安装方法

### 方式一：直接运行 exe（最简单，无需安装 Python）

**获取 exe**，任选其一：

- 到 [Releases](../../releases) 页面下载 `QuickScriptStudio-v*.zip`（由 GitHub Actions 自动构建）
- 或自己本地打包，见下方「打包成单个 exe」

**使用**：把 `QuickScriptStudio.exe` 放到任意**可写**的目录，
双击即可打开，**不需要安装 Python，也不需要任何依赖**。

> ⚠️ 不要放在 `C:\Program Files` 这类只读位置。程序会在 exe 旁边创建 `data/`
> 存放脚本与模板；若该位置不可写，会自动回退到 `%APPDATA%\QuickScriptStudio`。

**关于杀毒软件**：exe 由 PyInstaller 打包，未加壳（未使用 UPX），
但个别杀软仍可能对「单文件自解压」型程序报警。如果被拦截，
把 exe 加入信任列表，或改用下方的「方式二：从源码运行」。

### 方式二：从源码运行

**环境要求**

- Windows 10 / 11
- Python **3.8 或以上**（[下载](https://www.python.org/downloads/)）
  安装时**务必勾选** `Add Python to PATH`

**步骤**

```bat
:: 1. 获取代码
git clone https://github.com/reeeezec/QuickScript-Studio.git
cd QuickScript-Studio

:: 2. 直接运行（无需 pip install，本项目零第三方依赖）
python -m quickscript
```

也可以双击 `启动.bat`（普通权限）或 `以管理员身份启动.bat`（推荐）。

**打包成单个 exe**

```bat
:: 一键打包（会自动安装 PyInstaller，然后构建）
dev/打包exe.bat

:: 或手动执行
pip install pyinstaller
pyinstaller --noconfirm --clean dev/QuickScriptStudio.spec
:: 产物：dist\QuickScriptStudio.exe（约 12 MB，单文件）
```

打包配置在 [`dev/QuickScriptStudio.spec`](dev/QuickScriptStudio.spec)，要点：

| 设置 | 取值 | 原因 |
|---|---|---|
| 模式 | **onefile**（单文件） | 拷到哪都能跑，用户要求「以 exe 形式打开」 |
| 控制台 | `console=False` | GUI 程序不带黑框；启动失败会写入 `data/launch.log` |
| 入口 | `qs.py` | `quickscript/__main__.py` 用相对导入，不能直接当打包入口 |
| UPX | 关闭 | 压缩后极易被杀毒软件误报 |
| 排除 | `numpy`/`PIL`/`cv2` 等 | 本项目零第三方依赖，排除后体积更小 |

> onefile 每次启动会把运行时解压到临时目录（首次启动约 1~2 秒）。
> 若更在意启动速度，可把 spec 里的 `EXE(...)` 换成 `COLLECT(...)` 改成目录模式。

### ⚠️ 关于管理员权限

如果**目标程序以管理员权限运行**，Windows 的安全机制（UIPI）会**静默丢弃**
低权限进程发送的模拟输入。典型现象是：

> 本工具自己在前台时点击有效，一切换到目标窗口就完全没反应。

**解决办法：以管理员身份运行本工具。** 环境自检会明确告知是否属于这种情况。
用 `以管理员身份启动.bat` 可以一键提权；exe 也可以右键 →「以管理员身份运行」。

---

## 4. 使用方法

### 4.1 五分钟上手

**第 1 步：启动**

```bat
python -m quickscript
```

**第 2 步：绑定目标窗口**

1. 打开你要操作的程序（记事本、浏览器、业务软件……）
2. 回到本工具，点顶部 **「刷新窗口列表」**，在下拉框里选中目标窗口
   - 更稳的做法：先点一下目标程序，再回来点 **「取前台窗口」**
3. 绑定成功后，右上角会显示绿色的 `坐标：已绑定窗口 宽x高 ✓`

**第 3 步：放置第一个坐标点**

1. 点一下目标程序，把鼠标移到你要点击的位置
2. 按 **F8**：屏幕顶部出现浮条，显示当前位置
3. 再按一次 **F8** 记录这个点（可连续记录多个）
4. 点浮条上的 **「✓ 完成」**，坐标会写回你选中的步骤

**第 4 步：设置参数**

在右侧「步骤参数」里调整。推荐起点：

| 参数 | 推荐值 | 说明 |
|---|---|---|
| 按下时长 | `0.05` ~ `0.12` 秒 | 太短容易被忽略，太长显得迟钝 |
| 连击间隔 | `0.08` ~ `0.15` 秒 | |
| 移动耗时 | `0.15` 左右 | **不要填 0**（瞬移最不自然） |
| 抖动 | `1` ~ `3` 像素 | |

在「脚本设置」里还可以给整体加随机浮动，让节奏更自然。

**第 5 步：运行**

- 按 **F9**（会先等 `开始前准备时间` 让你切换窗口）
- 随时按 **F10** 紧急停止

### 4.2 界面说明

```
┌──────────────────────────────────────────────────────────────────────┐
│ 脚本：[下拉选择]  新建 保存 另存为 重命名 删除      ← 脚本管理        │
│ 绑定窗口：[标题输入框] [窗口列表▾] 刷新 取前台窗口   ← 绑定目标       │
├────────┬────────────────────────────────┬────────────────────────────┤
│ 添加步骤│  ↑上移 ↓下移 复制 删除 清空     │ 步骤参数 │ 脚本设置       │
│        │  ▶ 从选中步骤开始运行            │                            │
│  鼠标   │ ┌──┬────────┬────────┬───────┐ │  X: [240]                  │
│  键盘   │ │# │ 类型   │ 内容   │ 备注  │ │  Y: [270]                  │
│  流程   │ │1 │ 🏷 标签 │ …      │       │ │  按下时长: [0.06]          │
│  条件   │ │2 │ ● 点击 │ …      │ 点按钮│ │  [🎯 F8 拾取屏幕坐标]      │
├────────┴─┴────────┴────────┴───────┴─┴────────────────────────────┤
│ 运行日志（按颜色区分 正常 / 成功 / 警告 / 错误）                      │
├──────────────────────────────────────────────────────────────────────┤
│ 鼠标 屏幕(960,540) 脚本(240,270) [窗口相对]   F8 · F9 · F10          │
└──────────────────────────────────────────────────────────────────────┘
```

- **左栏**：所有可添加的步骤，按 鼠标 / 键盘 / 流程 / 条件 分组，悬停有说明
- **中栏**：步骤列表。双击某一步 = 只测试这一步；运行时当前步骤高亮
- **右栏**：「步骤参数」是当前步骤的全部参数；「脚本设置」是整份脚本的全局设置

> 📷 **界面截图占位**
> <!-- TODO: 在此插入界面截图 -->
> `![主界面](docs/images/main-window.png)`
> `![参数面板](docs/images/step-params.png)`

### 4.3 常用技巧

- **只测试一步**：选中步骤 → 点「测试本步」，不用跑完整个脚本
- **从中间开始跑**：选中某一步 → 点「从选中步骤开始运行」
- **写备注**：选中步骤 → 按 **F2** 快速编辑，或在右侧备注框里写
- **查看全部备注**：菜单「工具 → 查看全部备注…」，双击可跳回该步骤
- **输入文本**：`keys` 填的是**按键名**（如 `a`、`space`、`ctrl+s`），
  不是要输入的文本内容。需要输入一段文字时，请逐键添加步骤
- **让节奏更自然**：在「脚本设置」里加大 `按下时长随机浮动` 和 `间隔随机浮动`

---

## 5. 功能示例

`examples/` 目录下有 6 个可直接导入的示例脚本：

| 文件 | 演示内容 |
|---|---|
| `01-notepad-input.json` | **最小可用**：点击输入区并发送按键，用来快速验证环境 |
| `02-loop-click.json` | **循环与等待**：重复点击 10 次，带随机间隔 |
| `03-drag-path.json` | **拖动轨迹**：沿路径平滑拖动，演示步数控制 |
| `04-conditional-color.json` | **条件分支**：找色判断，未命中就跳回标签重试 |
| `05-keyboard.json` | **键盘操作**：连发、按住不放、组合键 |
| `06-screen-coords.json` | **屏幕绝对坐标模式** |

**导入方法**：菜单「文件 → 导入脚本 (JSON)…」，选择文件即可。

> ⚠️ 示例里的坐标是**参考值**，请按你自己的窗口重新用 F8 拾取。

### 示例一：把这段 JSON 存成 `hello.json` 再导入

```json
{
  "version": 2,
  "name": "最小示例",
  "target": {
    "coord_mode": "window",
    "window_title": "记事本",
    "window_match": "contains",
    "bring_to_front": true
  },
  "settings": { "start_delay": 1.5, "delay_jitter": 0.05 },
  "steps": [
    { "type": "click", "x": 300, "y": 300, "hold": 0.06, "move_time": 0.15,
      "note": "点一下输入区" },
    { "type": "delay", "seconds": 0.4, "random": 0.1 },
    { "type": "key", "keys": "ctrl+a", "hold": 0.05, "note": "全选" },
    { "type": "key", "keys": "a", "hold": 0.03, "times": 3, "interval": 0.12,
      "note": "连按三次 a" },
    { "type": "key", "keys": "enter", "hold": 0.05, "note": "换行" }
  ]
}
```

### 示例二：循环 + 条件判断（伪代码，便于理解编排思路）

```
标签 <重试>
  点击「提交」按钮
  等待 1 秒
  如果 (120,340) 的颜色是 #4CAF50  →  继续
  否则                              →  跳转回 <重试>
  按 Enter
  停止脚本
```

对应的 JSON 步骤：

```json
{ "type": "label", "name": "重试" },
{ "type": "click", "x": 400, "y": 500, "hold": 0.06, "move_time": 0.15 },
{ "type": "delay", "seconds": 1.0, "random": 0.2 },
{ "type": "if_color", "x": 120, "y": 340, "color": "#4CAF50", "tol": 12,
  "on_success": "continue", "on_fail": "goto", "fail_label": "重试" },
{ "type": "key", "keys": "enter", "hold": 0.05 },
{ "type": "stop" }
```

### 示例三：用找图判断界面状态

```json
{ "type": "if_image",
  "image": "data/templates/保存按钮.png",
  "tol": 12,
  "similarity": 0.95,
  "region": "0,0,400,120",
  "on_success": "goto", "success_label": "可以保存",
  "on_fail": "stop" }
```

- 用界面的「📷 截取屏幕区域做模板」直接框选一小块存成模板图片
- **模板要小而有特征**；`region` 越小，查找越快越准
- 匹配度会打印在运行日志里，方便你调参

### 脚本格式完整参考

字段含义、全部步骤类型、版本迁移规则，见
**[docs/script-format.md](docs/script-format.md)**。

---

## 项目结构

顶层只放**用户直接需要**的东西，开发工具收在 `dev/` 里：

```
QuickScriptStudio.exe    打包好的程序（双击即用，无需 Python）
启动.bat                 普通权限启动
以管理员身份启动.bat       提权启动（推荐，兼容管理员权限的目标程序）
README.md / LICENSE / CHANGELOG.md / CONTRIBUTING.md

quickscript/             ★ 程序源码
├── __main__.py          模块入口（python -m quickscript）
├── metadata.py          项目名、版本、路径约定
├── model.py             脚本数据模型与格式（含 v1→v2 迁移）
├── runtime.py           执行引擎：组合四层
├── storage.py           脚本库（多脚本管理与导入导出）
├── ui.py                Tkinter 图形界面
├── compat.py            旧接口兼容层
├── layers/              四层架构
│   ├── actions.py         动作层：鼠标 / 键盘
│   ├── flow.py            流程层：等待 / 循环 / 跳转 / 停止
│   ├── triggers.py        触发层：找色 / 找图
│   └── target.py          目标层：窗口绑定与坐标模式
└── platform/            平台层：唯一直接调用 Win32 的地方
    ├── wininput.py        键鼠注入、窗口、截屏、热键、权限与输入法检查
    ├── vision.py          找色 / 找图（自带图像编解码）
    └── overlays.py        屏幕浮层：坐标拾取、区域框选

dev/                     ★ 开发与打包工具
├── 打包exe.bat            一键打包 exe
├── 一键自检.bat           运行全部自动化测试
├── 调试启动.bat           带控制台启动，便于看报错
├── QuickScriptStudio.spec PyInstaller 打包配置
├── qs.py                 打包入口（GUI 启动壳）
├── run_admin.py          管理员权限启动器
├── run.bat / run_admin.bat  开发时的启动脚本
└── icon.ico              程序图标（exe 会内嵌）

docs/script-format.md    脚本格式说明
examples/                示例脚本
tests/                   自动化测试（tests/run_all.py 为总入口）
data/                    运行时数据（脚本、模板、日志；已 gitignore）
dist/ build/             打包产物（已 gitignore）
```

依赖方向是单向的：`layers/*` 只依赖抽象与执行上下文，彼此不互相调用，
由 `runtime` 负责组合。因此各层可以独立测试与替换。

> 打包配置用 `SPECPATH` 推算路径，因此 `dev/打包exe.bat` 与 GitHub Actions
> 无论从哪个目录调用，产出的 exe 都落在项目根目录下。

---

## 开发与测试

```bat
:: 运行程序
python -m quickscript

:: 只做环境自检，不开界面
python -m quickscript --check

:: 查看版本
python -m quickscript --version

:: 运行全部测试
python tests\run_all.py
```

测试分四类：单元自检、界面自检、跨进程端到端真实输入验证、启动链验证。
详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 常见问题

**Q：跑完了，但目标程序没反应？**

先点菜单 **「帮助 → 环境自检」**，它会直接告诉你是哪一类问题。常见三种：

1. **权限不足** —— 目标程序以管理员权限运行，而本工具不是。
   现象是「工具自己在前台时点击有效，切到目标窗口就没反应」。
   → 以管理员身份运行本工具。

2. **模拟输入被拦截** —— 后台的加速器或安全软件开启了「游戏模式 / 键鼠保护」，
   导致 `SendInput` 返回成功但鼠标纹丝不动。
   → 退出该软件或关闭其键鼠保护。

3. **按键没反应，但鼠标正常** —— 中文输入法把注入按键吞成了 `VK_PROCESSKEY`。
   → 本工具运行时会自动切英文布局；也可手动按 `Win + 空格` 切换。

**Q：坐标看着对，但点偏了？**

- 确认已绑定窗口、且是「窗口相对坐标」模式
- 目标程序若有缩放显示（如浏览器缩放），坐标会整体偏移，需重新拾取
- 用「测试本步」单独验证这一步

**Q：找图总是找不到？**

把 `region` 搜索区域框小一点、`similarity` 降到 0.9 左右，
或者重新截取一张**更小、更有特征**的模板图片。

**Q：怎么停止？**

按 **F10**。所有按住的键盘键和鼠标键都会被自动松开。

**Q：脚本文件存在哪？**

默认在程序目录的 `data/scripts/` 下，一个脚本一个 JSON 文件。
如果程序目录不可写（例如装在 `C:\Program Files`），会自动改用
`%APPDATA%\QuickScriptStudio\`。

---

## 许可证

[MIT](LICENSE) © 2025 QuickScript Studio contributors

---

# English

## 1. What problem does it solve?

Everyday work and testing involve a lot of **repetitive, mechanical input**:

- Clicking the same few buttons and filling the same fields over and over
- Manually repeating hundreds of clicks for UI testing
- Automating legacy software that offers no API — simulated input is the only way
- Wanting automation, but existing tools either require coding or produce
  recordings you cannot fine-tune

**QuickScript Studio turns those routines into editable scripts:**

| Problem | How this project solves it |
|---|---|
| Can't write code | Add steps by clicking in the GUI; **press F8 to pick screen coordinates** — no pixel math |
| Recordings are hard to tweak | Every step exposes **precise parameters** (hold duration, click interval, move time, jitter) |
| Scripts break when a window moves | **Window-relative coordinates**: bind a target window and the script keeps working after moves/resizes |
| Need to react to state | **Color / image matching** with conditional branches (jump or stop) |
| Long flows become unreadable | Add a **note** to any step; browse all notes at once |
| Need complex flows | Loops and label jumps, with nesting |

- **Zero third-party dependencies** — standard library only (tkinter / ctypes / zlib / json)
- **Scripts are plain JSON** — editable in any text editor, versionable with Git

---

## 2. Key features

### Architecture — four layers

| Layer | Responsibility | Step types |
|---|---|---|
| **Actions** | Produce input | `move` `click` `drag` `wheel` `key` `key_down` `key_up` |
| **Flow** | Control the path | `delay` `loop_begin` `loop_end` `label` `goto` `stop` |
| **Triggers** | Conditional branches | `if_color` `if_image` |
| **Target** | What to act on, how coordinates map | Not a step — a script-level `target` section |

### Mouse

Move (with duration & jitter) · Click (button, **hold duration**, click count,
interval, move time) · Drag (path, duration, step count, jitter) · Wheel.

### Keyboard

- **170 key names**: letters/digits, `F1`–`F24`, arrows, numpad, modifiers,
  plus Chinese aliases (`空格`, `回车`, `上`, `下`)
- **Combos**: `ctrl+shift+a`, `alt+F4`
- Hold duration, repeat count, repeat interval
- **Key down / key up** for sustained holds
- Injects both virtual-key code and **hardware scan code** for wider compatibility

### Flow control

Wait (with optional randomness) · Loops (pair `loop_begin` / `loop_end`, **nestable**,
`0` = infinite) · Labels & jumps · Stop · Built-in infinite-loop guard (300k steps).

### Conditional triggers

| Step | Description |
|---|---|
| If a pixel's color matches | Check a coordinate's color with configurable tolerance |
| If an image is on screen | Template matching with minimum similarity and search region |

Both support **hit / miss → continue / jump to label / stop**.
Image matching ships with its **own PNG/BMP/PPM decoder** — no OpenCV, no numpy.

### Two coordinate modes

| Mode | Description | When to use |
|---|---|---|
| **Window-relative** (recommended) | Relative to the target window's client area; survives moves and resizes | Almost always |
| **Absolute screen** | Plain screen pixels | Fixed-position targets |

Window-relative mode also supports a **fixed origin** pinned to a screen position.

### Global hotkeys

| Key | Action |
|---|---|
| **F8** | Pick the coordinate under the cursor (and its color); repeatable |
| **F9** | Run the script |
| **F10** | Emergency stop (**releases every held key**) |

### Script management

Multi-script library (new / save / save-as / rename / delete with recoverable
trash), **JSON import & export**, **per-step notes** (up to 300 chars) with a
dedicated column and an all-notes overview, and a **`version`-tagged format**
with automatic migration from older files.

### Environment self-check

The worst failure mode in automation is "it ran, but nothing happened".
The built-in check reports four classes of problems explicitly:

| Check | What it detects |
|---|---|
| **Input injection** | Actually moves the cursor and reads it back to confirm injection works |
| **Privileges** | Whether the target runs elevated (UIPI blocks input from lower-integrity processes) |
| **Keyboard IME** | A Chinese IME swallows injected keys as `VK_PROCESSKEY`; switches to English layout before running |
| **Hotkeys** | Whether F8/F9/F10 are already taken by another program |

Run it any time from **Help → Environment self-check**.

---

## 3. Installation

### Option A — run the exe (easiest, no Python required)

**Get the exe**, either way:

- Download `QuickScriptStudio-v*.zip` from [Releases](../../releases)
  (built automatically by GitHub Actions)
- Or build it locally — see *Build a single-file exe* below

**Use it:** put `QuickScriptStudio.exe` in any **writable** folder and double-click.
**No Python installation and no dependencies are required.**

> ⚠️ Avoid read-only locations such as `C:\Program Files`. The app creates a
> `data/` folder next to the exe for scripts and templates; if that location is
> not writable it automatically falls back to `%APPDATA%\QuickScriptStudio`.

**A note on antivirus software:** the exe is packed with PyInstaller and is *not*
compressed with UPX, but some antivirus products still flag self-extracting
single-file binaries. If that happens, allow-list the exe or use Option B.

### Option B — from source

**Requirements:** Windows 10/11 and Python **3.8+**
(tick `Add Python to PATH` during installation).

```bat
git clone https://github.com/reeeezec/QuickScript-Studio.git
cd QuickScript-Studio

:: No pip install needed — zero third-party dependencies
python -m quickscript
```

You can also double-click `启动.bat` (normal privileges) or
`以管理员身份启动.bat` (recommended).

**Build a single-file exe**

```bat
:: One-click build (installs PyInstaller if needed, then builds)
dev/打包exe.bat

:: Or manually
pip install pyinstaller
pyinstaller --noconfirm --clean dev/QuickScriptStudio.spec
:: Output: dist\QuickScriptStudio.exe (~12 MB, single file)
```

The build configuration lives in [`dev/QuickScriptStudio.spec`](dev/QuickScriptStudio.spec):

| Setting | Value | Why |
|---|---|---|
| Mode | **onefile** | Runs from anywhere; "open it as an exe" is the use case |
| Console | `console=False` | No black console for a GUI app; failures go to `data/launch.log` |
| Entry point | `qs.py` | `quickscript/__main__.py` uses relative imports and cannot be the entry |
| UPX | disabled | Compressed binaries trigger antivirus false positives |
| Excludes | `numpy`/`PIL`/`cv2` etc. | Zero third-party dependencies, so excluding keeps it small |

> onefile re-extracts runtime files to a temp folder on each launch
> (~1–2 s on first start). If start-up speed matters more to you, replace
> `EXE(...)` with `COLLECT(...)` in the spec to build a folder instead.

### ⚠️ About administrator privileges

If the **target program runs elevated**, Windows' UIPI silently drops simulated
input from a lower-integrity process. The classic symptom is:

> Clicks work while this tool is focused, but stop working the moment you
> switch to the target window.

**Fix: run this tool as Administrator.** The environment self-check tells you
whether this is your situation.

---

## 4. Usage

### Five-minute quick start

**Step 1 — Launch**

```bat
python -m quickscript
```

**Step 2 — Bind a target window**

1. Open the program you want to automate
2. Back in the tool, click **Refresh window list** and pick it
   (or focus the target and click **Use foreground window**)
3. On success the top-right shows `坐标：已绑定窗口 WxH ✓`

**Step 3 — Capture a coordinate**

1. Focus the target and position your cursor where you want to click
2. Press **F8** — a bar appears at the top of the screen
3. Press **F8** again to record the point (repeat for more points)
4. Click **✓ Done** on the bar; coordinates are written into the selected step

**Step 4 — Tune parameters** (recommended starting values)

| Parameter | Value | Why |
|---|---|---|
| Hold duration | `0.05`–`0.12` s | Too short gets ignored; too long feels sluggish |
| Click interval | `0.08`–`0.15` s | |
| Move time | `~0.15` s | **Don't use 0** (instant jumps look unnatural) |
| Jitter | `1`–`3` px | |

**Step 5 — Run**

- Press **F9** (waits for *start delay* so you can switch windows)
- Press **F10** any time to stop

### UI overview

```
┌──────────────────────────────────────────────────────────────────────┐
│ Script: [dropdown]  New Save Save-as Rename Delete   ← script library│
│ Target window: [title] [window list▾] Refresh Use foreground         │
├────────┬────────────────────────────────┬────────────────────────────┤
│ Add    │  ↑ ↓ Copy Delete Clear          │ Step params │ Script setup │
│ steps  │  ▶ Run from selected step        │                            │
│ Mouse  │ ┌──┬────────┬────────┬───────┐ │  X: [240]                  │
│ Keyboard│ │# │ Type   │ Content│ Note  │ │  Y: [270]                  │
│ Flow   │ │1 │ 🏷 Label│ …      │       │ │  Hold: [0.06]              │
│ Trigger│ │2 │ ● Click │ …     │ start │ │  [🎯 F8 pick coordinate]   │
├────────┴─┴────────┴────────┴───────┴─┴────────────────────────────┤
│ Run log (colour-coded: info / ok / warning / error)                  │
└──────────────────────────────────────────────────────────────────────┘
```

> 📷 **Screenshot placeholder**
> <!-- TODO: insert screenshots here -->
> `![Main window](docs/images/main-window.png)`
> `![Step parameters](docs/images/step-params.png)`

### Tips

- **Test one step**: select it and click *Test this step*
- **Run from the middle**: select a step and click *Run from selected step*
- **Add a note**: press **F2**, or use the note box on the right
- **See all notes**: *Tools → View all notes…* (double-click to jump back)
- **Typing text**: `keys` holds **key names** (`a`, `space`, `ctrl+s`), not text.
  Add one step per key to type a string
- **More natural pacing**: raise *hold jitter* and *delay jitter* in Script setup

---

## 5. Examples

Six ready-to-import scripts live in `examples/`:

| File | Demonstrates |
|---|---|
| `01-notepad-input.json` | **Minimal**: click a field and send keys — good for a smoke test |
| `02-loop-click.json` | **Loops & waits**: click 10 times with randomised intervals |
| `03-drag-path.json` | **Drag paths** with smooth stepping |
| `04-conditional-color.json` | **Conditional branch**: colour check, loop back on miss |
| `05-keyboard.json` | **Keyboard**: repeats, sustained hold, key combos |
| `06-screen-coords.json` | **Absolute screen coordinate mode** |

Import via **File → Import script (JSON)…**.

> ⚠️ Coordinates in the examples are **reference values** — re-capture them with
> F8 for your own windows.

### Minimal script

```json
{
  "version": 2,
  "name": "Minimal",
  "target": {
    "coord_mode": "window",
    "window_title": "Notepad",
    "window_match": "contains",
    "bring_to_front": true
  },
  "settings": { "start_delay": 1.5, "delay_jitter": 0.05 },
  "steps": [
    { "type": "click", "x": 300, "y": 300, "hold": 0.06, "move_time": 0.15,
      "note": "focus the edit area" },
    { "type": "delay", "seconds": 0.4, "random": 0.1 },
    { "type": "key", "keys": "ctrl+a", "hold": 0.05, "note": "select all" },
    { "type": "key", "keys": "a", "hold": 0.03, "times": 3, "interval": 0.12,
      "note": "press 'a' three times" },
    { "type": "key", "keys": "enter", "hold": 0.05, "note": "newline" }
  ]
}
```

### Conditional branch

```json
{ "type": "label", "name": "retry" },
{ "type": "click", "x": 400, "y": 500, "hold": 0.06, "move_time": 0.15 },
{ "type": "delay", "seconds": 1.0, "random": 0.2 },
{ "type": "if_color", "x": 120, "y": 340, "color": "#4CAF50", "tol": 12,
  "on_success": "continue", "on_fail": "goto", "fail_label": "retry" },
{ "type": "key", "keys": "enter", "hold": 0.05 },
{ "type": "stop" }
```

### Image matching

```json
{ "type": "if_image",
  "image": "data/templates/save-button.png",
  "tol": 12,
  "similarity": 0.95,
  "region": "0,0,400,120",
  "on_success": "goto", "success_label": "can-save",
  "on_fail": "stop" }
```

Use **📷 Capture screen region as template** to grab a small, distinctive area.
Smaller `region` values are faster and more accurate; match scores are printed
in the run log so you can tune thresholds.

**Full format reference:** [docs/script-format.md](docs/script-format.md)

---

## License

[MIT](LICENSE) © 2025 QuickScript Studio contributors
