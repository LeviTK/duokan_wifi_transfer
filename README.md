# WiFi传书 Calibre 插件

通过 WiFi 将 Calibre 书库中的 EPUB 书籍一键传输到多看阅读 App。

## 环境要求

- Calibre 5.0 及以上
- Python 3.x（Calibre 内置）
- 手机与电脑处于同一局域网，多看阅读已开启 WiFi 传书

## 安装

1. 将 `src/` 目录下的所有文件打包为 ZIP 文件（保持目录结构）
2. 在 Calibre 中：首选项 → 插件 → 从文件安装插件 → 选择打包好的 ZIP

从 v1.2.x 升级时，先在 Calibre 插件管理器中删除旧名称“多看阅读WiFi传书”，再安装 v1.3.0。Calibre 会按显示名称识别插件，不手动删除会导致新旧插件并存；已有设备配置使用相同配置键，不会因此丢失。

## 使用

1. 在 Calibre 书库中选中一本或多本书籍（仅支持 EPUB 格式）
2. 首次使用从下拉菜单「管理接收设备」打开设备管理器，添加并命名地址
3. 在设备管理器或下拉菜单勾选一个或多个收件设备，并可另行设置默认设备
4. 点击工具栏主按钮后，插件先显示解析进度并验证已保存地址，再将每本书发送到所有可达的勾选设备
5. macOS 上，不可达设备会按其已保存端口在当前 Wi-Fi 子网内寻找；同端口多设备只有在发现结果能一一对应时才自动映射，不会重复发送到同一主机
6. 「自动查找」会把结果合并到设备管理器供命名、编辑和保存；没有设备时只询问多看页面显示的一个端口
7. Windows/Linux 仍会直连测试并发送到可达的已保存地址，但不支持自动子网查找；不可达地址需在设备管理器中手动修正

## 项目结构

```
├── src/                        # 插件源码（打包时取此目录内容）
│   ├── __init__.py             # 插件元数据与注册
│   ├── ui.py                   # 工具栏与多设备配置
│   ├── transport.py            # 直连探测与流式上传
│   ├── main.py                 # 对话框 UI 与后台工作线程
│   ├── images/                 # 图标资源
│   └── plugin-import-name-duokan_wifi_transfer.txt
├── doc/                        # 文档目录
├── scripts/                    # 打包、验证、安装和用户测试入口
├── tests/                      # 在 Calibre 运行时执行的集成测试
├── Makefile                    # 自动化命令入口
└── README.md
```

## 本地自动化

Calibre 的 macOS 命令行目录为：

```bash
/Applications/calibre.app/Contents/MacOS
```

若终端尚未识别相关命令，可临时执行：

```bash
export PATH="/Applications/calibre.app/Contents/MacOS:$PATH"
```

生成版本化插件包：

```bash
make build
```

执行完整自动验证：

```bash
make verify
```

该命令会检查源码和 ZIP，并通过临时 `CALIBRE_CONFIG_DIRECTORY` 完成隔离构建、发布包安装、插件导入和本地模拟上传，不会修改日常 Calibre 配置。

先正常退出 Calibre，再执行真实安装：

```bash
make install
```

安装前会把当前名称和旧名称插件备份到 `dist/backups/`，自动移除旧名称后再安装已验证 ZIP。安装完成后执行以下命令进入手机端人工验收：

```bash
make user-test
```

详细步骤和通过标准见 [用户验收手册](doc/USER_TESTING.md)。

## 版本

当前版本：1.3.0
