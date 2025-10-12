#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import (unicode_literals, division, absolute_import, print_function)

__license__ = 'GPL v3'
__copyright__ = '2024, Your Name'
__docformat__ = 'restructuredtext en'

import os
from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import error_dialog, info_dialog

try:
    from qt.core import QMenu, QInputDialog, QLineEdit
except ImportError:
    from PyQt5.Qt import QMenu, QInputDialog, QLineEdit

class InterfacePlugin(InterfaceAction):
    name = '多看阅读WiFi传书'
    action_spec = ('多看阅读WiFi传书', None, '一键传书到多看阅读', 'Ctrl+Shift+D')
    
    def genesis(self):
        self.qaction.triggered.connect(self.show_dialog)
        
        # 创建菜单
        self.menu = QMenu(self.gui)
        self.qaction.setMenu(self.menu)
        
        # 添加菜单项
        self.send_action = self.menu.addAction('发送选中的书籍', self.show_dialog)
        self.config_action = self.menu.addAction('配置WiFi地址', self.configure)
        
        # 从设置加载WiFi地址
        from calibre.utils.config import JSONConfig
        self.prefs = JSONConfig('plugins/duokan_wifi_transfer')
        self.duokan_wifi_address = self.prefs.get('wifi_address', 'http://192.168.1.100:8080')
    
    def configure(self):
        self.prefs = self.load_settings()
        current_address = self.prefs.get('wifi_address', 'http://192.168.1.100:8080')
        
        new_address, ok = QInputDialog.getText(
            self.gui, '配置多看阅读WiFi地址',
            '输入多看阅读WiFi传书地址:',
            QLineEdit.Normal, current_address
        )
        
        if ok and new_address:
            if not new_address.startswith('http://'):
                new_address = 'http://' + new_address
            
            self.prefs['wifi_address'] = new_address
            self.duokan_wifi_address = new_address
            info_dialog(self.gui, '成功', '多看阅读WiFi地址已更新为: %s' % new_address, show=True)
    
    def load_settings(self):
        from calibre.utils.config import JSONConfig
        self.prefs = JSONConfig('plugins/duokan_wifi_transfer')
        return self.prefs
    
    def show_dialog(self):
        from calibre_plugins.duokan_wifi_transfer.main import DuokanWiFiDialog
        dialog = DuokanWiFiDialog(self.gui, self)
        exec_method = getattr(dialog, 'exec', dialog.exec_)
        exec_method()
    
    def send_book_to_duokan(self, epub_path, title):
        """发送书籍到多看阅读"""
        try:
            import urllib.request
            import urllib.error
            import mimetypes
            import uuid
            
            # 打印调试信息
            print(f"正在发送书籍: {title}")
            print(f"目标地址: {self.duokan_wifi_address}/files")
            print(f"文件路径: {epub_path}")
            
            # 准备文件数据
            with open(epub_path, 'rb') as f:
                file_data = f.read()
            
            # 生成分隔符
            boundary = str(uuid.uuid4())
            
            # 构建multipart表单数据
            content_type = mimetypes.guess_type(epub_path)[0] or 'application/epub+zip'
            filename = os.path.basename(epub_path)
            
            # 构建请求头
            headers = {
                'User-Agent': 'Calibre Duokan Plugin/1.0',
                'Content-Type': f'multipart/form-data; boundary={boundary}'
            }
            
            # 构建请求体
            body = []
            body.append(f'--{boundary}'.encode())
            body.append(f'Content-Disposition: form-data; name="newfile"; filename="{filename}"'.encode())
            body.append(f'Content-Type: {content_type}'.encode())
            body.append(b'')
            body.append(file_data)
            body.append(f'--{boundary}--'.encode())
            body.append(b'')
            
            body = b'\r\n'.join(body)
            
            # 创建请求
            request = urllib.request.Request(
                self.duokan_wifi_address + '/files',  # 修改为正确的URL
                data=body,
                headers=headers,
                method='POST'
            )
            
            # 发送请求
            response = urllib.request.urlopen(request, timeout=30)
            
            # 打印响应信息
            print(f"响应状态码: {response.status}")
            response_content = response.read().decode('utf-8')
            print(f"响应内容: {response_content}")
            
            if response.status == 200:
                return True, None
            else:
                error_msg = f'HTTP状态码: {response.status}'
                return False, error_msg
                
        except urllib.error.URLError as e:
            reason = getattr(e, 'reason', e)
            if isinstance(reason, ConnectionRefusedError):
                error_msg = '无法连接到多看阅读WiFi服务（连接被拒绝）'
            else:
                error_msg = f'无法连接到多看阅读WiFi服务：{reason}'
            print(f"发送书籍 {title} 发生网络错误: {error_msg}")
            return False, error_msg
        except Exception as e:
            import traceback
            error_msg = f'发送书籍 {title} 时出现未预期错误：{type(e).__name__}: {str(e)}'
            print(f"{error_msg}\n{traceback.format_exc()}")
            return False, error_msg
