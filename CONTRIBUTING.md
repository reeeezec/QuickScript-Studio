# Contributing to QuickScript Studio / 贡献指南

感谢你愿意为 **QuickScript Studio（快捷脚本开发器）** 做出贡献！
Thanks for your interest in contributing to **QuickScript Studio**!

QuickScript Studio 是一个**通用键鼠自动化工具**：把重复性的桌面操作录制成可编辑的
脚本并自动执行。它**不是**游戏外挂，也**不是**针对任何特定游戏或网站的工具。
本项目**不接受**任何外挂 / 作弊 / 绕过反作弊相关的功能、示例或讨论。

> 中文说明在前，英文说明在后。
> Chinese section first, English section follows.

---

## 一、中文

### 1. 开发环境要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / 11（依赖 Win32 `SendInput` API，不支持 Linux / macOS） |
| Python | 3.8 或更高版本 |
| 第三方依赖 | **无**。仅使用标准库：`tkinter` / `ctypes` / `zlib` / `json` 等 |
| 编辑器 | 任意（VS Code、PyCharm 等） |

安装 Python 时请勾选 **Add Python to PATH**。

### 2. 获取代码与运行

```bat
git clone <your-fork-url>
cd QuickScript-Studio
python -m quickscript
```

> 也可以双击仓库中的启动 BAT 脚本。若想操作以管理员权限运行的目标程序，
> 请使用管理员权限启动器，否则 Windows 的 UIPI 机制会拦截模拟输入。

### 3. 运行测试

本项目**不使用** `pytest`，而是自带一套自检脚本（单元自检、界面自检、
跨进程端到端真实输入验证、启动链验证）。

测试脚本的**具体路径与名称可能随版本变化**，请以 `README.md` 中的
「测试」小节为准；那里列出了当前版本所有可用的自检命令与推荐执行顺序。

建议在提交 PR 前把 README 中列出的全部自检跑一遍，并确认全部通过。
注意：端到端测试会**真实地移动鼠标、发送按键**，请先保存工作、关闭
不想被影响的前台窗口。

### 4. 代码风格约定

- 遵循 **PEP 8**。
- 缩进使用 **4 个空格**，不要用 Tab。
- **变量名、函数名、注释**：英文、中文均可，中文注释完全欢迎；
  但**标识符（变量/函数/类名）请统一使用英文**，以便国际协作者阅读。
- 文件统一使用 **UTF-8** 编码（Windows 下请勿保存为 GBK）。
- 尽量保持**零第三方依赖**：新增依赖的 PR 需要有非常充分的理由。
- 保持改动聚焦：一个 PR 只做一件事，避免混入无关的格式化改动。

### 5. 提交信息规范（Conventional Commits）

提交信息使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
<type>(<scope>): <subject>
```

常用 `type`：

| type | 含义 |
| --- | --- |
| `feat` | 新功能 |
| `fix` | 修复缺陷 |
| `docs` | 仅文档改动 |
| `refactor` | 重构（不改变外部行为） |
| `test` | 测试相关 |
| `chore` | 构建 / 工具 / 杂项 |

示例：

```
feat(engine): support wheel scroll with custom step count
fix(launcher): correct elevation when path contains CJK characters
docs(readme): document the v2 JSON script format
```

### 6. 提交 PR 的流程

1. **Fork** 本仓库并克隆到本地。
2. 从 `main` 创建**特性分支**，命名建议：`feat/xxx`、`fix/xxx`、`docs/xxx`。
3. 编写代码，并补充或更新相应自检。
4. **确认测试通过**（见上文「运行测试」与 README）。
5. 提交（遵循 Conventional Commits），推送到你的 fork。
6. 向本仓库的 `main` 分支发起 **Pull Request**，并在描述中说明：
   - 这个 PR 解决了什么问题、怎么解决的；
   - 如何验证（复现 / 测试命令）；
   - 是否影响脚本格式、界面或已有行为（若有，请说明兼容性）。
7. 等待 Review，按反馈修改。所有讨论请保持友善与就事论事。

### 7. 报告 Bug 时应提供的信息

请在 Issue 中尽量完整地提供以下内容，这能极大加快定位速度：

- **系统版本**：Windows 10 还是 11，版本号（`winver` 输出）。
- **Python 版本**：`python --version` 的输出。
- **是否以管理员权限运行**：是 / 否。
- **复现步骤**：从启动到出问题的**最小**操作序列。
- **期望行为 vs 实际行为**。
- **日志文件 `data/launch_log.txt`**（请直接附上文件内容或作为附件上传）。
- 如与界面显示有关：**截图**，以及显示器的缩放比例（如 125% / 150%）。
- 如与脚本有关：**可脱敏后的脚本 JSON**（请先删除任何个人信息）。
- 如涉及找图找色：使用的**目标图片**与当时的屏幕分辨率。

### 8. 行为准则（简述）

- **尊重每一个人**，对事不对人；不接受人身攻击、歧视或骚扰。
- **聚焦技术**：讨论实现、性能、可读性与兼容性。
- **不讨论外挂 / 作弊用途**：本项目是通用桌面自动化工具，
  任何游戏作弊、绕过反作弊、批量刷号等话题都会被关闭。
- 维护者有权关闭不符合上述准则的 Issue 与 PR。

---

## 二、English

### 1. Development requirements

| Item | Requirement |
| --- | --- |
| OS | Windows 10 / 11 (uses the Win32 `SendInput` API; Linux/macOS are unsupported) |
| Python | 3.8 or newer |
| Third-party deps | **None.** Standard library only: `tkinter`, `ctypes`, `zlib`, `json`, ... |
| Editor | Anything (VS Code, PyCharm, ...) |

Make sure **Add Python to PATH** is checked during installation.

### 2. Get the code and run it

```bat
git clone <your-fork-url>
cd QuickScript-Studio
python -m quickscript
```

> You can also double-click the launcher BAT files. To automate a target program
> that runs elevated, use the administrator launcher — otherwise Windows UIPI
> will block the simulated input.

### 3. Running the tests

This project does **not** use `pytest`. It ships its own self-check scripts
(unit self-check, GUI self-check, cross-process end-to-end real-input
verification, launch-chain verification).

The **exact paths and names of these scripts may change between versions**, so
treat the "Testing" section of `README.md` as the source of truth: it lists every
self-check command available in the current version and the recommended order.

Please run all self-checks listed in the README and make sure they pass before
opening a PR. Note that the end-to-end test **really moves the mouse and sends
keystrokes** — save your work and close foreground windows you do not want
disturbed.

### 4. Code style

- Follow **PEP 8**.
- Indent with **4 spaces**, never tabs.
- **Comments may be written in English or Chinese** — Chinese comments are
  welcome. Please keep **identifiers (variables, functions, classes) in
  English** so that international contributors can read the code.
- All files must be **UTF-8** encoded (do not save as GBK on Windows).
- Keep the project **dependency-free**: a PR adding a third-party dependency
  needs a very strong justification.
- Keep changes focused: one PR, one concern. Avoid unrelated formatting churn.

### 5. Commit messages (Conventional Commits)

Use the [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <subject>
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

Examples:

```
feat(engine): support wheel scroll with custom step count
fix(launcher): correct elevation when path contains CJK characters
docs(readme): document the v2 JSON script format
```

### 6. Pull request workflow

1. **Fork** the repository and clone it locally.
2. Branch off `main` with a descriptive name (`feat/...`, `fix/...`, `docs/...`).
3. Write your code and add or update the corresponding self-checks.
4. **Make sure the tests pass** (see "Running the tests" above and the README).
5. Commit using Conventional Commits and push to your fork.
6. Open a **Pull Request** against `main` and describe:
   - what problem the PR solves and how;
   - how to verify it (reproduction / test commands);
   - whether it affects the script format, the UI, or existing behaviour
     (and if so, the compatibility impact).
7. Wait for review and iterate on the feedback. Keep the discussion friendly
   and focused on the technical merits.

### 7. What to include in a bug report

Please provide as much of the following as possible — it dramatically speeds up
triage:

- **OS version**: Windows 10 or 11 and the build number (`winver`).
- **Python version**: output of `python --version`.
- **Running elevated?** yes / no.
- **Steps to reproduce**: the **minimal** sequence from launch to the failure.
- **Expected behaviour vs actual behaviour**.
- **The `data/launch_log.txt` log file** (attach its contents).
- For UI issues: a **screenshot** and your display scaling (e.g. 125% / 150%).
- For script issues: the **script JSON** with any personal data removed.
- For colour/image matching: the **template image** used and the screen
  resolution at the time.

### 8. Code of conduct (short version)

- **Respect everyone.** Critique the work, not the person. Harassment,
  discrimination and personal attacks are not tolerated.
- **Stay technical**: implementation, performance, readability, compatibility.
- **No cheating / game-hack topics.** This is a general-purpose desktop
  automation tool; any request for game cheating, anti-cheat evasion or bulk
  account farming will be closed.
- Maintainers may close issues and PRs that violate the above.
