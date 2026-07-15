# 用户验收手册

本文用于发布前验证“多看阅读 WiFi 传书”Calibre 插件。自动化测试负责打包、插件加载和模拟上传；手机端实际收书与打开 EPUB 由用户完成。

## 准备条件

- macOS 已安装 Calibre，命令行目录已加入 `PATH`
- 手机和电脑连接同一局域网
- 多看阅读已开启 WiFi 传书，并显示可访问的 HTTP 地址
- Calibre 书库中准备以下样本：
  - 一本普通 EPUB
  - 两本以上 EPUB
  - 一本较大的 EPUB
  - 一本没有 EPUB 格式的书籍

## 发布前自动验证

```bash
make verify
```

通过标准：终端最后显示 `VERIFY OK`。该命令会完成：

1. 读取 `src/__init__.py` 版本号并生成版本化 ZIP
2. 检查 Python 语法、必要文件和 ZIP 完整性
3. 使用临时 `CALIBRE_CONFIG_DIRECTORY` 隔离真实配置
4. 测试 `calibre-customize -b src` 开发构建流程
5. 测试发布 ZIP 的全新安装、插件导入和模拟 `/files` 上传

## 安装到日常 Calibre

先正常退出 Calibre，再执行：

```bash
make install
```

安装脚本会先完整验证，再把当前已安装插件备份到 `dist/backups/`，最后使用 `calibre-customize -b src` 更新插件。

如明确允许脚本先请求 Calibre 关闭，可执行：

```bash
make install-shutdown
```

注意：强制关闭可能中断正在运行的 Calibre 任务。

## 启动用户验收

```bash
make user-test
```

该命令通过 `calibre-debug -g` 启动 Calibre，并把控制台输出保存到 `dist/logs/`。

## 验收项目

### 连接

- 输入多看显示的地址，不带 `http://` 时插件能自动补全
- 正确地址显示连接成功
- 错误 IP、错误端口和已关闭的 WiFi 传书服务能显示明确错误
- 测试连接期间界面没有卡死

### 传输

- 单本 EPUB 发送成功，手机端能看到并打开
- 多本 EPUB 能按顺序发送，进度条和当前书名正确
- 较大 EPUB 发送过程中 Calibre 界面仍可响应
- 无 EPUB 格式的书籍不会上传，并在最终结果中列出原因
- 发送期间不能重复触发发送任务

### 状态与结果

- 发送完成后按钮恢复可用，进度条隐藏
- 成功数和失败书目统计正确
- 保存 WiFi 地址后，重新打开对话框仍能读取该地址
- 完成测试并退出 Calibre 后，检查 `dist/logs/` 中最新日志没有本插件的未处理异常

## 验收结论

以下条件全部满足即可通过：

- `make verify` 成功
- 普通、多本和较大 EPUB 均能在手机端打开
- 无 EPUB、错误地址和服务关闭场景均有可理解的错误提示
- 测试期间 Calibre 没有卡死或崩溃
- 调试日志没有本插件的 traceback

本机现有 `GetFileName.zip` 插件可能产生独立的初始化错误；判断本插件结果时应与“多看阅读 WiFi 传书”的日志分开处理。

## 参考资料

- [Calibre 插件开发与调试](https://manual.calibre-ebook.com/zh_CN/creating_plugins.html)
- [calibre-customize 命令](https://manual.calibre-ebook.com/zh_CN/generated/zh_CN/calibre-customize.html)
- [Calibre 环境变量](https://manual.calibre-ebook.com/zh_CN/customize.html#environment-variables)
