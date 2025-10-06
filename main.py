#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import (unicode_literals, division, absolute_import, print_function)

__license__ = 'GPL v3'
__copyright__ = '2024, Your Name'
__docformat__ = 'restructuredtext en'

import os
from calibre.gui2 import error_dialog, info_dialog

try:
    from qt.core import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                        QLabel, QProgressBar, QLineEdit, QMessageBox)
except ImportError:
    from PyQt5.Qt import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                         QLabel, QProgressBar, QLineEdit, QMessageBox)

class DuokanWiFiDialog(QDialog):
    def __init__(self, gui, plugin_action):
        QDialog.__init__(self, gui)
        self.gui = gui
        self.plugin_action = plugin_action
        
        # 设置窗口标题和大小
        self.setWindowTitle('多看阅读WiFi传书')
        self.setMinimumWidth(500)
        
        # 创建主布局
        layout = QVBoxLayout(self)
        
        # 添加说明标签
        layout.addWidget(QLabel('请确保：\n1. 多看阅读已开启WiFi传书\n2. 电脑和手机在同一WiFi网络下'))
        
        # WiFi地址设置部分
        wifi_group = QHBoxLayout()
        wifi_group.addWidget(QLabel('多看阅读WiFi地址:'))
        self.wifi_address = QLineEdit(self.plugin_action.duokan_wifi_address)
        wifi_group.addWidget(self.wifi_address)
        test_button = QPushButton('测试连接')
        test_button.clicked.connect(self.test_connection)
        wifi_group.addWidget(test_button)
        layout.addLayout(wifi_group)
        
        # 选中书籍信息
        self.book_info = QLabel()
        layout.addWidget(self.book_info)
        
        # 进度条
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        
        # 按钮区域
        button_box = QHBoxLayout()
        
        # 发送按钮
        self.send_button = QPushButton('发送选中的书籍')
        self.send_button.clicked.connect(self.send_books)
        button_box.addWidget(self.send_button)
        
        # 保存设置按钮
        save_button = QPushButton('保存设置')
        save_button.clicked.connect(self.save_settings)
        button_box.addWidget(save_button)
        
        # 关闭按钮
        close_button = QPushButton('关闭')
        close_button.clicked.connect(self.close)
        button_box.addWidget(close_button)
        
        layout.addLayout(button_box)
        
        # 更新书籍信息
        self.update_book_info()
    
    def update_book_info(self):
        """更新选中书籍的信息"""
        rows = self.gui.library_view.selectionModel().selectedRows()
        count = len(rows)
        if count == 0:
            self.book_info.setText('未选择任何书籍')
            self.send_button.setEnabled(False)
        else:
            self.book_info.setText(f'已选择 {count} 本书籍')
            self.send_button.setEnabled(True)
    
    def test_connection(self):
        """测试与多看阅读WiFi服务的连接"""
        address = self.wifi_address.text().strip()
        if not address:
            return error_dialog(self, '错误', '请输入多看阅读WiFi地址', show=True)
        
        if not address.startswith('http://'):
            address = 'http://' + address
        
        try:
            import urllib.request
            
            # 创建请求
            request = urllib.request.Request(
                address,
                headers={'User-Agent': 'Calibre Duokan Plugin/1.0'}
            )
            
            # 发送请求
            response = urllib.request.urlopen(request, timeout=5)
            
            # 打印响应信息
            print(f"测试连接响应状态码: {response.status}")
            content = response.read().decode('utf-8')
            print(f"测试连接响应内容: {content}")
            
            if response.status == 200:
                QMessageBox.information(self, '成功', '成功连接到多看阅读WiFi服务')
            else:
                QMessageBox.warning(self, '连接失败', 
                                  f'无法连接到多看阅读WiFi服务。\n状态码: {response.status}\n响应: {content}')
        except Exception as e:
            import traceback
            error_msg = f'错误类型: {type(e).__name__}\n错误信息: {str(e)}\n\n详细追踪:\n{traceback.format_exc()}'
            QMessageBox.critical(self, '错误', f'连接失败：\n{error_msg}')
    
    def save_settings(self):
        """保存WiFi地址设置"""
        address = self.wifi_address.text().strip()
        if not address:
            return error_dialog(self, '错误', '请输入多看阅读WiFi地址', show=True)
        
        if not address.startswith('http://'):
            address = 'http://' + address
        
        self.plugin_action.duokan_wifi_address = address
        self.plugin_action.prefs['wifi_address'] = address
        QMessageBox.information(self, '成功', '设置已保存')
    
    def send_books(self):
        """发送选中的书籍到多看阅读"""
        # 获取选中的书籍
        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows:
            return error_dialog(self, '错误', '请先选择要发送的书籍', show=True)
        
        # 准备进度条
        total = len(rows)
        self.progress.setMaximum(total)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        
        # 获取书籍IDs
        ids = list(map(self.gui.library_view.model().id, rows))
        db = self.gui.current_db.new_api
        
        # 处理每本书
        success_count = 0
        failed_books = []
        
        for i, book_id in enumerate(ids):
            try:
                metadata = db.get_metadata(book_id)
                title = metadata.title
                
                # 更新进度条
                self.progress.setValue(i)
                self.progress.setFormat(f'正在处理: {title}')
                
                # 获取EPUB格式
                epub_path = db.format_abspath(book_id, 'EPUB')
                if not epub_path:
                    failed_books.append((title, "没有EPUB格式"))
                    continue
                
                # 发送书籍
                if self.plugin_action.send_book_to_duokan(epub_path, title):
                    success_count += 1
                else:
                    failed_books.append((title, "发送失败"))
                    
            except Exception as e:
                import traceback
                error_msg = f'错误类型: {type(e).__name__}\n错误信息: {str(e)}'
                failed_books.append((title, error_msg))
                print(f"发送书籍 {title} 时出错:\n{traceback.format_exc()}")
        
        # 完成处理
        self.progress.setVisible(False)
        
        # 显示结果
        result_message = f'成功发送 {success_count} 本书籍到多看阅读\n'
        if failed_books:
            result_message += '\n发送失败的书籍：\n'
            for book, reason in failed_books:
                result_message += f'• {book}: {reason}\n'
        
        if success_count > 0:
            QMessageBox.information(self, '完成', result_message)
        else:
            QMessageBox.warning(self, '失败', result_message)
