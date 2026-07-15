# AGENT

## 项目概述

这是一个 Calibre 插件，通过 HTTP 多部分表单（multipart/form-data）将 EPUB 书籍上传到多看阅读 App 的 WiFi 传书服务。

## 目录结构

```
src/
├── __init__.py     # 插件元数据（DuokanWifiBase 继承 InterfaceActionBase）
├── ui.py           # InterfacePlugin：Calibre 工具栏动作、菜单、HTTP 上传
├── main.py         # DuokanWiFiDialog、ConnectionTestWorker、SendBooksWorker
└── images/         # 图标资源（icon.png 为工具栏图标）
dist/               # 打包产物（已加入 .gitignore，不纳入版本控制）
doc/                # 文档目录
scripts/            # 自动化打包、验证、安装及用户测试脚本
tests/              # Calibre 运行时集成测试
Makefile            # 自动化统一入口
README.md
AGENT.md
```

## 架构说明

- **`InterfacePlugin`**（ui.py）：Calibre 工具栏入口，管理配置持久化（JSONConfig），调用 `send_book_to_duokan()` 执行 HTTP 上传。
- **`DuokanWiFiDialog`**（main.py）：主对话框，展示选书信息、进度条，协调两个后台线程。
- **`ConnectionTestWorker`**（main.py）：QThread，异步 GET 测试目标地址是否可达。
- **`SendBooksWorker`**（main.py）：QThread，顺序遍历书单，逐本调用 `send_book_to_duokan()`，通过 `progress` / `finished` 信号汇报状态。
- **`MultipartStream`**（ui.py）：自定义流式读取器，分块拼接 multipart 请求体，避免大文件整体加载进内存。

## 开发约定

- 所有 Qt 导入先尝试 `qt.core`（Calibre 内置），失败后回退到 `PyQt5.Qt`。
- 不在主线程执行网络 I/O；所有耗时操作均放入 QThread 子类。
- 错误信息在 `print()` 输出调试日志的同时通过 Qt 信号传回 UI 展示。
- EPUB 路径通过 `db.format_abspath(book_id, 'EPUB')` 获取，`None` 表示无该格式，需提前过滤。

## 打包插件

Calibre 插件以 ZIP 格式安装，打包产物输出到 `dist/`，文件名格式为 `{插件名}_{版本}.zip`。统一使用自动化入口，不再手工调用 `zip`：

```bash
make build
```

**注意事项：**
- 版本号取自 `src/__init__.py` 中 `DuokanWifiBase.version` 字段（元组形式，如 `(1, 2, 0)` → `v1.2.0`）
- 每次发布新版本，需同步更新 `__init__.py` 中的 `version` 并重新打包
- `dist/` 目录已加入 `.gitignore`，打包产物不纳入版本控制
- 打包内容为 `src/` 目录下所有文件（含 `plugin-import-name-*.txt` 和 `images/`），不包含 `dist/`、`doc/` 等项目级目录

## 自动验证与安装

```bash
make verify             # 静态检查、ZIP 校验、隔离构建/安装、导入和模拟上传
make install            # 完整验证、备份现有插件并更新日常 Calibre
make install-shutdown   # 请求关闭 Calibre 后再安装，可能中断正在运行的任务
make user-test          # 以调试模式启动 Calibre，保存日志并进入人工验收
```

- `make verify` 必须使用临时 `CALIBRE_CONFIG_DIRECTORY`，不得修改用户日常配置。
- 发布 ZIP 必须经过 `calibre-customize -a` 全新安装测试，开发源码必须经过 `calibre-customize -b src` 测试。
- 模拟上传测试在 `127.0.0.1` 随机端口启动临时 HTTP 服务，不访问外网或手机。
- 真实安装前必须备份已安装插件；默认不强制关闭 Calibre。
- 手机端实际收书和打开 EPUB 仍是人工验收项，步骤见 `doc/USER_TESTING.md`。

## 关键接口

| 接口 | 说明 |
|------|------|
| `POST {address}/files` | 上传 EPUB，字段名 `newfile`，返回 200 表示成功 |
| `GET {address}` | 连接测试，返回 200 表示多看 WiFi 服务在线 |

## 注意事项

- 仅支持 EPUB 格式；其他格式书籍会被标记为失败并跳过。
- `send_book_to_duokan()` 返回 `(bool, str | None)` 元组；调用方需做元组解包。
- 默认 WiFi 地址 `http://192.168.1.100:8080` 仅为占位，用户必须替换为实际地址。
