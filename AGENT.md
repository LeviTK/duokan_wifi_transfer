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
doc/                # 文档目录
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

Calibre 插件以 ZIP 格式安装，打包时取 `src/` 目录内容：

```bash
cd src
zip -r ../duokan_wifi_transfer.zip .
```

## 关键接口

| 接口 | 说明 |
|------|------|
| `POST {address}/files` | 上传 EPUB，字段名 `newfile`，返回 200 表示成功 |
| `GET {address}` | 连接测试，返回 200 表示多看 WiFi 服务在线 |

## 注意事项

- 仅支持 EPUB 格式；其他格式书籍会被标记为失败并跳过。
- `send_book_to_duokan()` 返回 `(bool, str | None)` 元组；调用方需做元组解包。
- 默认 WiFi 地址 `http://192.168.1.100:8080` 仅为占位，用户必须替换为实际地址。
