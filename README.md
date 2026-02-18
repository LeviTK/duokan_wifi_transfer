# 多看阅读 WiFi 传书 Calibre 插件

通过 WiFi 将 Calibre 书库中的 EPUB 书籍一键传输到多看阅读 App。

## 环境要求

- Calibre 2.0 及以上
- Python 3.x（Calibre 内置）
- 手机与电脑处于同一局域网，多看阅读已开启 WiFi 传书

## 安装

1. 将 `src/` 目录下的所有文件打包为 ZIP 文件（保持目录结构）
2. 在 Calibre 中：首选项 → 插件 → 从文件安装插件 → 选择打包好的 ZIP

## 使用

1. 在 Calibre 书库中选中一本或多本书籍（仅支持 EPUB 格式）
2. 点击工具栏中的「多看阅读WiFi传书」按钮
3. 在弹出对话框中输入多看阅读显示的 WiFi 地址（如 `http://192.168.1.x:8080`）
4. 点击「测试连接」确认网络通畅
5. 点击「发送选中的书籍」开始传输

## 项目结构

```
├── src/                        # 插件源码（打包时取此目录内容）
│   ├── __init__.py             # 插件元数据与注册
│   ├── ui.py                   # Calibre 工具栏集成、HTTP 上传逻辑
│   ├── main.py                 # 对话框 UI 与后台工作线程
│   ├── images/                 # 图标资源
│   └── plugin-import-name-duokan_wifi_transfer.txt
├── doc/                        # 文档目录
└── README.md
```

## 打包插件

```bash
cd src
zip -r ../duokan_wifi_transfer.zip .
```

## 版本

当前版本：1.2.0
