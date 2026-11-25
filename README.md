# TL_Macro

Windows 桌面游戏宏辅助工具（多键宏 / 单键宏 / 图像宏）。

## 环境

- Windows 10/11 x64
- Python 3.11+
- 建议以管理员权限运行（全局热键与输入模拟）

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app.py
```

## 打包

```bash
.venv\Scripts\pyinstaller.exe TL_Macro.spec
```

输出：`dist/TL_Macro/TL_Macro.exe`

## 测试

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 文档

开发设计说明见 [`docs/DESIGN.md`](docs/DESIGN.md)。

## 版本

见 `version.py`（当前 v1.7.0）。
