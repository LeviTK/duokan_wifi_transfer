# Changelog

所有版本的变更记录均记录于此文件，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [1.2.0] - 2025-11-08

### Changed
- 重构项目目录结构：插件源码移至 `src/`，新增 `doc/`、`dist/` 目录
- 打包产物命名规范化，格式统一为 `{插件名}_v{版本}.zip`，输出至 `dist/`
- `dist/` 加入 `.gitignore`，不纳入版本控制

### Added
- 新增 `README.md`，包含安装、使用及打包说明
- 新增 `AGENT.md`，记录项目架构、关键接口及开发约定，供 AI Agent 上下文使用

---

## [1.1.0] - 2025-10-13

### Added
- 新增工具栏图标（`images/icon.png`）
- 新增 `ConnectionTestWorker`（QThread）：后台异步测试 WiFi 连接，不阻塞主界面
- 新增 `SendBooksWorker`（QThread）：后台顺序发送书籍，通过 Qt Signals 回报进度
- 新增 `MultipartStream`：分块流式读取 EPUB，以 multipart/form-data POST 上传，避免大文件整体加载进内存

### Changed
- 上传接口路径修正为 `POST {address}/files`
- 进度条在发送过程中实时更新，完成后自动隐藏
- 错误信息细化：区分连接拒绝、URL 错误及未预期异常

---

## [1.0.0] - 2025-10-07

### Added
- 初始版本发布
- 支持通过 WiFi 将 Calibre 书库中的 EPUB 书籍传输到多看阅读 App
- `DuokanWiFiDialog` 对话框：WiFi 地址输入、连接测试、书籍发送
- WiFi 地址持久化（`JSONConfig`），支持保存与快速配置
- 工具栏菜单入口：「发送选中书籍」与「配置 WiFi 地址」
- 支持 Windows、macOS、Linux，最低兼容 Calibre 2.0
