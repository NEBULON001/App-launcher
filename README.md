# AppLauncher

> 基于 Python + tkinter 的桌面快捷启动器，支持自定义软件列表、.lnk 快捷方式自动解析、一键全部启动、开机自启、系统托盘常驻、毛玻璃效果及启动动画。

![screenshot](docs/screenshot.png)

## 功能特性

- **自定义软件列表** — 随时添加 / 删除本地可执行文件（`.exe`）或快捷方式（`.lnk`）
- **.lnk 自动解析** — 添加快捷方式时自动解析真实目标路径，无需手动查找
- **一键全部启动** — 单击即可同时启动列表中所有已注册的软件
- **开机自启** — 通过 Windows 注册表（`HKCU\...\Run`）实现开机自动运行
- **系统托盘常驻** — 最小化到托盘不占用任务栏，双击托盘图标即可恢复窗口
- **毛玻璃效果** — 三级降级策略适配不同 Windows 版本：
  - Level 1：Win11 22H2+ 原生 Acrylic / Mica（`DwmSetWindowAttribute`）
  - Level 2：Win10 / 旧版 Win11 `SetWindowCompositionAttribute` + `AccentPolicy`
  - Level 3：软件降级方案（PIL 截屏 + 高斯模糊 + 暗色叠加）
- **启动动画** — 淡入淡出 + 发光脉冲标题 + 进度条的现代启动画面
- **单实例锁** — 通过 Windows 命名互斥量确保全局唯一实例，重复启动时自动唤起已有窗口
- **无边框全屏** — 沉浸式无边框窗口，ESC 键快速退出

## 安装方式

### 方式一：下载 Release（推荐）

1. 前往 [Releases](../../releases) 页面下载最新的 `AppLauncher.exe`
2. 双击运行即可，无需安装 Python 环境

### 方式二：从源码运行

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/AppLauncher.git
cd AppLauncher

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行
python main.py
```

> **环境要求**：Python 3.10+，Windows 10/11（部分毛玻璃效果依赖 Windows 版本）

## 使用说明

1. **添加软件** — 点击工具栏「＋ 添加软件」按钮，在弹出的文件对话框中选择 `.exe` 或 `.lnk` 文件
2. **启动单个软件** — 点击列表中对应行的「▶」按钮
3. **一键全部启动** — 点击工具栏「▶ 全部启动」按钮，列表中所有软件将同时启动
4. **删除软件** — 点击列表中对应行的「✕」按钮，确认后从列表移除
5. **最小化到托盘** — 点击工具栏「— 最小化」按钮，窗口隐藏到系统托盘
6. **恢复窗口** — 双击系统托盘图标，或右键选择「显示」
7. **开机自启** — 勾选工具栏「开机自启」复选框，程序将注册到 Windows 启动项
8. **退出程序** — 点击工具栏「✕ 退出」按钮，或右键托盘图标选择「退出」，或按 `ESC` 键

## 技术栈

| 技术 | 说明 |
|------|------|
| Python 3.13 | 主开发语言 |
| tkinter | GUI 框架（Python 标准库） |
| pywin32 | Windows COM 接口（.lnk 解析、win32com） |
| pystray | 系统托盘图标 |
| Pillow | 图像处理（托盘图标生成、软件毛玻璃降级方案） |
| ctypes | Win32 API 直接调用（DWM 毛玻璃、互斥量单实例） |

## 项目结构

```
AppLauncher/
├── main.py                # 入口：单实例锁 + 启动序列
├── splash_animation.py    # 启动动画（淡入淡出 + 发光脉冲 + 进度条）
├── ui.py                  # 主窗口 UI（工具栏 + 可滚动列表 + 事件处理）
├── app_manager.py         # 应用列表管理（增删改查 + .lnk 解析 + 启动）
├── autostart.py           # 开机自启（Windows 注册表读写）
├── tray.py                # 系统托盘（pystray + 程序生成图标）
├── glass_effect.py        # 毛玻璃效果（三级降级：DWM → WCA → PIL）
├── requirements.txt       # Python 依赖清单
├── 启动.bat               # Windows 快速启动脚本
├── config.json            # 运行时生成的配置文件（软件列表）
├── README.md              # 项目说明
├── LICENSE                # MIT 开源协议
└── .gitignore             # Git 忽略规则
```

## License

[MIT License](LICENSE) © 2026 AppLauncher
