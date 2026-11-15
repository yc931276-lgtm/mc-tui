# MC-TUI：终端界面 Minecraft 启动器

[English](README.md) | **简体中文**

一个轻量、零依赖的**终端用户界面（TUI）Minecraft 启动器**，专为发现和启动**本地 Minecraft 文件**而设计。

完全使用 Python 标准库（`curses`、`subprocess`、`json`、`uuid` 等）构建，**无需任何 pip 外部包**或编译器。

---

## ✨ 功能

- **本地与离线优先**：
  - 无需 Microsoft 登录或外部账号。
  - 为自定义玩家名自动生成 Mojang 标准离线 UUID。
  - 100% 离线启动——不会发起不必要的网络请求或遥测。
- **内置原版 Minecraft 下载器**：
  - 直接下载 Mojang 官方正式版、快照和旧版本。
  - 下载版本 JSON、客户端 `.jar`、平台相关库/原生库，以及资源索引/对象。
  - 多线程并发下载，SHA-1 完整性校验、HTTP Range 断点续传（`.part` 文件）和重复目标去重。
  - 可选镜像（`official` Mojang 或 `bmclapi`）。
- **通用本地版本兼容**：
  - 支持 **Vanilla**、**Fabric**、**Forge**、**NeoForge**、**Quilt** 和 **OptiFine**。
  - 也可直接启动独立服务端或客户端 `.jar` 文件。
  - 递归解析模组加载器的版本继承（`inheritsFrom`）。
- **完整启动引擎**：
  - 同时支持**现代** `arguments` JSON 格式（1.13+）和**旧版** `minecraftArguments` 格式（1.7 – 1.12.2）。
  - 求值 Mojang 的操作系统与架构规则（`linux`、`x86_64`、`arm64` 等）。
  - 将 Maven 库坐标解析为本地 jar 路径。
  - 为旧版本自动解压原生共享库（`.so`）到原生目录。
- **智能 Java 运行时检测**：
  - 在 `/usr/lib/jvm`、`PATH`、`$JAVA_HOME` 和 SDK 管理器中发现已安装的 Java 环境。
  - 解析主版本（Java 8、11、17、21、25），为目标 Minecraft 版本选择合适的运行时。
  - 可在**设置**页通过 `apt` 安装缺失的 OpenJDK 8/17/21/25（需要 sudo 密码）。
- **交互式 TUI 与完整国际化**：
  - **简体中文与 English**：自动检测系统语言，也可在设置中手动切换。
  - **版本列表**：过滤和搜索版本（`/`），查看元数据、发布日期、所需 Java 版本，按 `[Enter]` 启动。
  - **设置页**：交互配置用户名、内存（`-Xms`、`-Xmx`）、JVM 参数、镜像、语言、自定义 Java/游戏路径、JRE 安装和外观。
  - **主题与外观**：七套配色预设（经典、海洋、森林、晚霞、单色、霓虹、纸张）、主色调覆盖、标题栏样式和选中行样式，支持实时预览。
  - **控制台日志**：实时查看 Minecraft 进程输出，彩色日志、自动滚动和结束进程。
  - **游戏目录选择器**：在 `~/.minecraft`、Prism Launcher 实例、Flatpak 目录或自定义文件夹之间切换。
  - **原版下载器**：浏览官方正式版/快照，按版本号搜索（如 `1.20.4`），预览详情并直接在 TUI 中下载。
  - **鼠标支持**：点击标签页、列表行和“启动/下载”按钮；双击行执行操作；点击已选中设置项的值即可编辑。
- **CLI 配套**：
  - 通过 `--list`、`--launch` 和 `--preview` 在无界面模式或脚本中使用。

---

## 🚀 快速开始

### 1. 启动交互式 TUI
```bash
# 直接运行
python3 run.py

# 或通过包装可执行文件
mc-tui
```

### 2. CLI 模式

**列出 Mojang 可下载的官方原版版本：**
```bash
./run.py --download-list
# 或者包含快照与预发布版
./run.py --download-list --snapshots
```

**下载官方 Minecraft 原版版本：**
```bash
# 完整下载（客户端 jar + 库 + 声音与材质资源）
./run.py --download 1.20.4

# 快速下载（仅客户端 jar + 库，跳过可选资源）
./run.py --download 1.20.4 --no-assets

# 使用 BMCLAPI 镜像下载
./run.py --download 1.20.4 --mirror bmclapi
```

**列出本地已安装版本：**
```bash
./run.py --list
# 或指定自定义游戏目录
./run.py --game-dir ~/Games/minecraft --list
```

**仅预览组装后的 Java 命令，不启动游戏：**
```bash
./run.py --preview 1.20.4
```

**直接从终端启动版本并流式输出日志：**
```bash
./run.py --launch 1.20.4 --username Steve --ram 4G
```

---

## ⌨️ TUI 键盘快捷键

| 快捷键 | 说明 |
|---|---|
| `[1]` `[2]` `[3]` `[4]` `[5]` | 切换 **版本列表**、**设置**、**控制台**、**游戏目录**、**下载** |
| `[Tab]` | 切换到下一个标签页 |
| `[↑]` / `[↓]` 或 `[k]` / `[j]` | 在列表或设置项间移动 |
| `[Enter]` | 启动选中版本 / 开始下载 / 编辑设置 |
| `[d]` | 从版本列表快速跳到**下载**页 |
| `[a]` | 开/关资源下载（下载页） |
| `[s]` | 开/关快照（下载页）/ 保存设置（设置页） |
| `[p]` | 预览完整 Java 命令与参数 |
| `[/]` | 按版本号搜索（如 `1.20.4`；下载页会自动选中完全匹配项） |
| `[r]` | 刷新版本列表 / manifest / 恢复默认设置 |
| `[Space]` | 切换日志自动滚动（控制台） |
| `[k]` | 结束正在运行的 Minecraft 进程（控制台） |
| `[c]` | 清空控制台日志 |
| `[e]` | 输入自定义路径（游戏目录页） |
| `[q]` | 退出启动器 / 取消当前下载 |
| 鼠标单击 | 切换标签页、选择列表行、点击“启动/下载”按钮 |
| 鼠标双击 | 启动 / 编辑 / 下载鼠标所在行 |

---

## 📁 项目结构

```
mc-tui/
├── bump_version.py         # 统一更新源码与 Debian 打包版本号
├── mc_tui/
│   ├── __init__.py
│   ├── config.py           # 配置管理（~/.config/mc-tui/config.json）
│   ├── downloader.py       # Mojang 原版版本、库与资源下载器
│   ├── i18n.py             # 国际化与简体中文翻译
│   ├── java_detector.py    # 多版本 Java 扫描与版本匹配
│   ├── version_parser.py   # 版本 JSON 解析、inheritsFrom 合并、Maven 解析
│   ├── launcher.py         # 启动计划构建、原生库解压、进程控制
│   ├── theme.py            # 配色主题与外观设置
│   └── tui/
│       ├── __init__.py
│       ├── app.py          # curses 主事件循环与控制器
│       ├── ui_helpers.py   # 弹窗、颜色对、安全渲染、文本输入
│       ├── version_filter.py # 下载页版本搜索与最佳匹配
│       ├── mouse.py        # 标签页、列表行与按钮的鼠标点击命中检测
│       └── views.py        # 标签页视图：版本、设置、控制台、目录选择、下载
├── tests/
│   ├── test_config.py
│   ├── test_downloader.py
│   ├── test_downloader_resume.py
│   ├── test_execution.py
│   ├── test_i18n.py
│   ├── test_java_detector.py
│   ├── test_jre_manager.py
│   ├── test_launcher.py
│   ├── test_mouse.py
│   ├── test_parser.py
│   ├── test_theme.py
│   └── test_version_filter.py
├── run.py                  # CLI 与 TUI 启动入口
├── mc-tui                  # 可执行包装符号链接
├── README.md               # English
└── README.zh-CN.md         # 简体中文
```

---

## 🧪 运行测试

```bash
cd /home/heaway/Dev/mc-tui
python3 -m unittest discover -s tests
```

---

## 📦 Debian 软件包（.deb）

### 更新版本号
版本号位于 `mc_tui/__init__.py`、`debian/control`、`debian/changelog`、man 手册和 README 的包文件名中。用一条命令统一更新：
```bash
python3 bump_version.py 1.2.0          # Debian 修订号默认为 1
python3 bump_version.py 1.2.0 2        # 仅打包修订号 2
python3 bump_version.py 1.2.0 --dry-run
```
启动器的 `${launcher_version}` / `-Dminecraft.launcher.version` 现在直接来自 `mc_tui.__version__`，无需单独修改。

### 构建软件包
在 Debian/Ubuntu 系统上构建 `.deb`：
```bash
./build_deb.sh
```
生成的包位于 `dist/mc-tui_1.1.0-1_all.deb`。只会生成这一份符合 Debian 规范命名的文件，不再创建便捷副本。构建脚本还会写入关于页显示的构建时间；直接从源码运行时显示“开发运行（未打包）”。

### 安装软件包
使用 `apt` 只安装启动器本身，唯一必需依赖是 Python 3。Java 运行时是可选的，不再自动拉取——可在 TUI 的**设置**页安装所需版本（`安装 JRE 8/17/21/25`），或手动执行 `sudo apt install openjdk-17-jre`：
```bash
sudo apt install ./dist/mc-tui_1.1.0-1_all.deb
```
或使用 `dpkg`：
```bash
sudo dpkg -i dist/mc-tui_1.1.0-1_all.deb
# 如果使用 dpkg，自动补齐缺失依赖：
sudo apt-get install -f
```

安装后，可在终端任意位置运行 `mc-tui`，也可从桌面应用菜单启动。
