# Changelog

所有版本的变更记录均记录于此文件，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [1.3.0] - 2026-07-15

### Added
- 原生设备管理器、多个具名接收设备、持久化多选收件人、默认设备，以及旧地址安全迁移
- 当前 Wi-Fi 子网内复用已知端口逐地址测试，严格验证两个多看指纹并经用户确认后保存
- 代理无关的直连流式传输层；macOS 私网流量严格绑定当前 Wi-Fi 接口
- 新增原创“书籍、Wi-Fi 与手机传输”插件图标及 SVG 母版

### Changed
- 插件对外名称由“多看阅读WiFi传书”简化为“WiFi传书”；内部配置键保持不变
- 工具栏主按钮先自动解析所有勾选设备，再执行书籍 × 接收设备的多目标上传
- 下拉菜单直接勾选收件人并标示默认设备；解析和上传均使用不可变端点快照
- 地址变化只用于当次已验证快照，不静默覆盖偏好设置；结果按设备报告成功、失败和不可达项

### Fixed
- 修复 Calibre 9.11 / Qt 6 下设备管理器因表头枚举差异无法打开的问题
- 按 Calibre 官方 `InterfaceAction` 资源模式在 `genesis()` 中加载插件 ZIP 图标
- 自动查找结果回填设备管理器；同端口多设备采用不复用主机的安全一一映射，歧义项保留供手动处理
- Windows/Linux 先直连验证已保存地址，仅将自动子网查找标记为不支持
- 上传对话框增加按“设备 × EPUB”计数的真实进度条，并按设备列出不可达和跳过项

## [1.2.1] - 2026-07-15

### Added
- 新增 `Makefile` 和 `scripts/automation.py`，支持版本化打包、静态校验、隔离 Calibre 安装测试与真实安装备份
- 新增 Calibre 运行时模拟上传测试，验证 `/files` multipart 请求、字段名、文件名和 EPUB 内容
- 新增调试模式用户测试入口及 `doc/USER_TESTING.md` 验收手册

### Fixed
- 修复后台线程结果信号覆盖 `QThread.finished`，导致线程尚未退出便被销毁并使 Calibre 崩溃的问题
- 后台连接或发送任务执行期间阻止关闭对话框，避免活动线程随窗口销毁

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
