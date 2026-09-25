# 脚本格式说明（Script Format）

本文档描述 QuickScript Studio 的脚本文件格式。脚本是**纯 JSON**，
可以直接用文本编辑器查看和修改，也方便用 Git 管理版本。

- 当前格式版本：**`version: 2`**
- 文件扩展名：`.json`
- 编码：**UTF-8**（无 BOM）
- 默认存放位置：`data/scripts/<脚本名>.json`

---

## 1. 整体结构

```json
{
  "version": 2,
  "name": "示例脚本",
  "target": {
    "coord_mode": "window",
    "window_title": "记事本",
    "window_match": "contains",
    "window_class": "",
    "bring_to_front": true,
    "use_fixed_origin": false,
    "origin_x": 0,
    "origin_y": 0
  },
  "settings": {
    "start_delay": 1.0,
    "hold_jitter": 0.0,
    "delay_jitter": 0.0,
    "move_after_click": 0.0
  },
  "steps": [
    { "type": "click", "x": 100, "y": 200, "note": "点击开始按钮" },
    { "type": "delay", "seconds": 1.0, "note": "等待界面加载" }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `version` | int | 格式版本号。当前为 `2`。载入时据此决定是否需要迁移 |
| `name` | string | 脚本名（也是文件名来源） |
| `target` | object | 目标层设置：操作哪个窗口、坐标怎么算 |
| `settings` | object | 运行节奏设置 |
| `steps` | array | 有序的步骤列表，从上到下执行 |

---

## 2. `target` —— 目标层

决定「对谁操作」和「坐标如何解释」。

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `coord_mode` | `"screen"` \| `"window"` | `"window"` | 坐标模式，见下 |
| `window_title` | string | `""` | 目标窗口标题（部分或全部，取决于匹配方式） |
| `window_match` | `"contains"` \| `"exact"` \| `"startswith"` | `"contains"` | 标题匹配方式 |
| `window_class` | string | `""` | 窗口类名；填了就要求类名完全一致 |
| `bring_to_front` | bool | `true` | 运行时是否把目标窗口切到前台 |
| `use_fixed_origin` | bool | `false` | 是否使用固定原点（不跟随窗口） |
| `origin_x` / `origin_y` | int | `0` | 原点偏移量，含义随模式而定 |

### 坐标模式

**`screen` —— 屏幕绝对坐标**

步骤里的 `(x, y)` 就是屏幕像素位置。简单直接，
但目标窗口一旦移动或改变大小，脚本就失效。

**`window` —— 窗口相对坐标（推荐）**

步骤里的 `(x, y)` 相对「原点」计算，而原点默认是**目标窗口客户区的左上角**：

```
屏幕坐标 = 客户区左上角 + (origin_x + x, origin_y + y)
```

窗口移动、缩放后依然可用，脚本可复用性强。

- `use_fixed_origin: false`（默认）—— 原点跟随绑定窗口。
- `use_fixed_origin: true` —— 原点钉死在屏幕上的 `(origin_x, origin_y)`，
  不随窗口移动。适合窗口标题不稳定、但画面位置固定的场景。

> **提示**：窗口相对模式下，条件判断（找色/找图）也只截取目标窗口的客户区，
> 因此更快也更准确。

---

## 3. `settings` —— 运行节奏

影响整体手感，用来让操作更自然、也给目标程序留出响应时间。

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `start_delay` | float | `1.0` | 按下运行后的准备时间（秒），留出手动切换窗口的余量 |
| `hold_jitter` | float | `0.0` | 每次「按下时长」的随机浮动范围（±秒） |
| `delay_jitter` | float | `0.0` | 每次间隔的随机浮动范围（±秒） |
| `move_after_click` | float | `0.0` | 每次点击后额外停顿（秒） |

实际取值会在基准值上叠加 `±jitter` 的随机量，且不会小于 0。

---

## 4. `steps` —— 步骤

每个步骤至少有两个字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | 步骤类型，决定其余字段的含义 |
| `note` | string | **备注**，最长 300 字。仅用于说明，不影响执行 |

步骤按职责分为**三层**（第四层「目标层」体现在上面的 `target` 里）：

| 层 | 作用 | 步骤类型 |
|---|---|---|
| 动作层 | 产生输入 | `move` `click` `drag` `wheel` `key` `key_down` `key_up` |
| 流程层 | 控制走向 | `delay` `loop_begin` `loop_end` `label` `goto` `stop` |
| 触发层 | 条件分支 | `if_color` `if_image` |

### 4.1 动作层 —— 鼠标

#### `move` 移动鼠标

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `x` `y` | int | `0` | 目标坐标 |
| `duration` | float | `0.15` | 移动耗时（秒）。`0` 表示瞬移 |
| `jitter` | int | `0` | 每步的随机抖动（像素） |

#### `click` 点击

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `x` `y` | int | `0` | 目标坐标 |
| `button` | `left` \| `right` \| `middle` \| `x1` \| `x2` | `left` | 鼠标键 |
| `hold` | float | `0.05` | 按下时长（秒） |
| `clicks` | int | `1` | 点击次数 |
| `interval` | float | `0.08` | 连击之间的间隔（秒） |
| `move_time` | float | `0.12` | 移动到目标的耗时（秒），`0` = 瞬移 |

#### `drag` 拖动

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `x1` `y1` | int | `0` | 起点 |
| `x2` `y2` | int | `0` | 终点 |
| `button` | `left` \| `right` \| `middle` | `left` | 鼠标键 |
| `duration` | float | `0.3` | 拖动耗时（秒） |
| `steps` | int | `0` | 中间步数，`0` = 自动按距离计算 |
| `jitter` | int | `0` | 抖动（像素） |

#### `wheel` 滚轮

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `amount` | int | `1` | 滚动格数，**正数向上** |
| `times` | int | `1` | 重复次数 |
| `interval` | float | `0.05` | 每次间隔（秒） |

### 4.2 动作层 —— 键盘

#### `key` 按键

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `keys` | string | `"space"` | 按键名。组合键用 `+` 连接，如 `ctrl+shift+a` |
| `hold` | float | `0.05` | 按住时长（秒） |
| `times` | int | `1` | 重复次数 |
| `interval` | float | `0.1` | 每次间隔（秒） |
| `no_release` | bool | `false` | 结束时是否保持按住 |

按键名不区分大小写，支持：

- 字母数字：`a` ~ `z`、`0` ~ `9`
- 功能键：`F1` ~ `F24`
- 特殊键：`space`、`enter`、`esc`、`tab`、`backspace`、`delete`、`insert`
- 方向键：`up` `down` `left` `right`
- 小键盘：`num0` ~ `num9`、`multiply` `add` `subtract` `divide` `decimal`
- 修饰键：`ctrl` `shift` `alt` `win`（也可写 `lctrl` `rshift` 等）
- 中文别名：`空格`、`回车`、`上`、`下`、`左`、`右`

#### `key_down` / `key_up`

按住不放 / 松开按键。字段只有 `keys`。
适合需要持续按住的操作，两者成对使用。

### 4.3 流程层

#### `delay` 等待

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `seconds` | float | `0.5` | 基础等待秒数 |
| `random` | float | `0` | 额外随机量（±秒） |

#### `loop_begin` / `loop_end` 循环

`loop_begin` 的 `times` 表示循环体执行次数：

- `times: 0` —— **无限循环**（用 F10 停止）
- `times: 1` —— 等价于不循环
- `times: n` —— 执行 n 次

必须配对出现，**支持嵌套**：

```json
{ "type": "loop_begin", "times": 3 },
{ "type": "click", "x": 10, "y": 10 },
{ "type": "loop_begin", "times": 2 },
{ "type": "key", "keys": "space" },
{ "type": "loop_end" },
{ "type": "loop_end" }
```

#### `label` 标签 / `goto` 跳转

`label` 用 `name` 命名一个位置，`goto` 的 `name` 指向它。
标签名需唯一；重复时以第一个为准。

```json
{ "type": "label", "name": "开始" },
{ "type": "delay", "seconds": 1 },
{ "type": "goto", "name": "开始" }
```

#### `stop` 停止脚本

无条件结束运行。无额外字段。

### 4.4 触发层

两个触发步骤都支持相同的**分支**字段：

| 字段 | 取值 | 说明 |
|---|---|---|
| `on_success` | `continue` \| `goto` \| `stop` | 命中时做什么 |
| `success_label` | string | 命中且 `on_success` 为 `goto` 时的目标标签 |
| `on_fail` | `continue` \| `goto` \| `stop` | 未命中时做什么 |
| `fail_label` | string | 未命中且 `on_fail` 为 `goto` 时的目标标签 |

#### `if_color` 判断某点颜色

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `x` `y` | int | `0` | 取样点坐标 |
| `color` | string | `"#FF0000"` | 期望颜色，`#RRGGBB` 或 `r,g,b` |
| `tol` | int | `10` | 每个通道允许的偏差（0~255） |

命中条件：`|实际 - 期望| <= tol` 对 R、G、B 三个通道**都**成立。

```json
{
  "type": "if_color",
  "x": 120, "y": 340,
  "color": "#4CAF50", "tol": 12,
  "on_success": "goto", "success_label": "成功",
  "on_fail": "continue",
  "note": "按钮变绿就是可点状态"
}
```

#### `if_image` 判断画面上是否有图片

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `image` | string | `""` | 模板图片路径（PNG/BMP/PPM） |
| `tol` | int | `12` | 颜色容差 |
| `similarity` | float | `0.98` | 最低匹配度（0.3 ~ 1.0） |
| `region` | string | `""` | 搜索区域 `"x,y,w,h"`（脚本坐标）。留空 = 整个画面 |

模板图片建议**小而有特征**；搜索区域越小，速度越快、误判越少。
匹配度会打印在运行日志里，便于调参。

---

## 5. 版本迁移

载入脚本时会自动识别并升级旧格式，**无需手工转换**。

| 版本 | 特征 | 迁移到 v2 时发生什么 |
|---|---|---|
| v1 | 根节点有 `"schema": 1`，目标与节奏字段**平铺在根节点** | 目标字段收进 `target`，节奏字段收进 `settings`，版本号改为 `2` |
| 无版本号 | 既无 `version` 也无 `schema` | 按 v1 处理 |

迁移是**只读转换**：原文件不会被改动，只有重新保存时才写出新格式。

### 检测顺序

1. 有 `version` → 用它
2. 有 `schema` → 视为 v1
3. 同时有 `target` 和 `settings` → 视为当前版本
4. 其它 → 按 v1 处理

### v1 示例与其迁移结果

迁移前：

```json
{
  "schema": 1,
  "name": "旧脚本",
  "coord_mode": "window",
  "window_title": "记事本",
  "start_delay": 1.5,
  "steps": [{ "type": "click", "x": 10, "y": 20 }]
}
```

迁移后：

```json
{
  "version": 2,
  "name": "旧脚本",
  "target": { "coord_mode": "window", "window_title": "记事本" },
  "settings": { "start_delay": 1.5 },
  "steps": [{ "type": "click", "x": 10, "y": 20, "note": "" }]
}
```

---

## 6. 向前兼容

- **未知字段会被保留**：载入时读不懂的字段不会丢弃，重新保存时原样写回。
  这让你可以安全地手工加注释性字段，也方便未来扩展。
- **缺省字段自动补全**：步骤里没写的字段会填入该类型的默认值。
- **未知步骤类型会报错**：这属于结构问题，无法安全忽略，因此明确拒绝载入。

---

## 7. 完整示例

```json
{
  "version": 2,
  "name": "记事本自动化",
  "target": {
    "coord_mode": "window",
    "window_title": "记事本",
    "window_match": "contains",
    "bring_to_front": true,
    "use_fixed_origin": false,
    "origin_x": 0,
    "origin_y": 0
  },
  "settings": {
    "start_delay": 1.5,
    "hold_jitter": 0.01,
    "delay_jitter": 0.05,
    "move_after_click": 0.0
  },
  "steps": [
    { "type": "label", "name": "开始", "note": "循环入口" },
    { "type": "click", "x": 300, "y": 500,
      "button": "left", "hold": 0.06, "clicks": 1, "move_time": 0.15,
      "note": "点一下输入区" },
    { "type": "delay", "seconds": 0.3, "random": 0.1 },
    { "type": "key", "keys": "ctrl+a", "hold": 0.05, "times": 1 },
    { "type": "key", "keys": "hello world", "hold": 0.03, "times": 1,
      "note": "逐个字符输入" },
    { "type": "loop_begin", "times": 3, "note": "重复三次" },
    { "type": "key", "keys": "enter", "hold": 0.05, "times": 1 },
    { "type": "delay", "seconds": 0.2 },
    { "type": "loop_end" },
    { "type": "if_color", "x": 120, "y": 340,
      "color": "#4CAF50", "tol": 12,
      "on_success": "goto", "success_label": "开始",
      "on_fail": "stop", "note": "变绿就继续循环，否则结束" },
    { "type": "stop" }
  ]
}
```

更多可直接导入的示例见仓库的 `examples/` 目录。

---

## 8. 校验规则

保存或运行前会做检查，分两类：

**错误（会阻止运行）**

- 脚本没有任何步骤
- `goto` 或分支的 `success_label` / `fail_label` 指向不存在的标签
- `loop_begin` 与 `loop_end` 未配对
- 按键名无法识别
- 颜色值无法解析
- 步骤类型未知（载入时即报错）

**警告（仍可运行）**

- 未绑定窗口却使用窗口相对坐标（会退回屏幕绝对坐标）
- `if_image` 未选择模板图片，或图片文件不存在

---

## 9. 相关文档

- [README](../README.md) —— 项目总览与使用说明
- [CONTRIBUTING](../CONTRIBUTING.md) —— 参与开发
- 代码层面：`quickscript/model.py`（格式定义与迁移）、
  `quickscript/layers/`（四层的具体实现）
