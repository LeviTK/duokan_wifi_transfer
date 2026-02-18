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
                        QLabel, QProgressBar, QLineEdit, QMessageBox,
                        QThread, pyqtSignal)
except ImportError:
    from PyQt5.Qt import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                         QLabel, QProgressBar, QLineEdit, QMessageBox,
                         QThread, pyqtSignal)


class ConnectionTestWorker(QThread):
    """后台线程测试连接，避免阻塞 Calibre 主界面。"""
    finished = pyqtSignal(bool, int, str, str)  # success, status_code, content, error_message

    def __init__(self, address):
        super(ConnectionTestWorker, self).__init__()
        self.address = address

    def run(self):
        import urllib.request
        import traceback

        try:
            request = urllib.request.Request(
                self.address,
                headers={'User-Agent': 'Calibre Duokan Plugin/1.0'}
            )
            response = urllib.request.urlopen(request, timeout=5)
            content = response.read().decode('utf-8', errors='replace')
            print(f"测试连接响应状态码: {response.status}")
            print(f"测试连接响应内容: {content}")
            self.finished.emit(response.status == 200, response.status, content, '')
        except Exception as e:
            error_msg = f'错误类型: {type(e).__name__}\n错误信息: {str(e)}\n\n详细追踪:\n{traceback.format_exc()}'
            self.finished.emit(False, 0, '', error_msg)


class SendBooksWorker(QThread):
    """后台线程顺序发送书籍，减轻主线程压力。"""
    progress = pyqtSignal(int, int, str)  # current_index, total, title
    finished = pyqtSignal(int, list)  # success_count, failed_books

    def __init__(self, plugin_action, books):
        super(SendBooksWorker, self).__init__()
        self.plugin_action = plugin_action
        self.books = books

    def run(self):
        success_count = 0
        failed_books = []
        total = len(self.books)

        for index, book in enumerate(self.books, start=1):
            title = book['title']
            epub_path = book['path']

            self.progress.emit(index, total, title)

            try:
                result = self.plugin_action.send_book_to_duokan(epub_path, title)
                if isinstance(result, tuple):
                    success, error_message = result
                else:
                    success = bool(result)
                    error_message = None if success else '发送失败'
            except Exception as e:
                import traceback
                error_msg = f'错误类型: {type(e).__name__}\n错误信息: {str(e)}\n\n详细追踪:\n{traceback.format_exc()}'
                failed_books.append((title, error_msg))
                continue

            if success:
                success_count += 1
            else:
                failed_books.append((title, error_message or '发送失败'))

        self.finished.emit(success_count, failed_books)

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
        self.test_button = QPushButton('测试连接')
        self.test_button.clicked.connect(self.test_connection)
        wifi_group.addWidget(self.test_button)
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
        self.connection_thread = None
        self.send_thread = None
        self.initial_failed_books = []
    
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
        raw_address = self.wifi_address.text().strip()
        if not raw_address:
            return error_dialog(self, '错误', '请输入多看阅读WiFi地址', show=True)
        
        address = raw_address
        if not address.startswith('http://'):
            address = 'http://' + address
            self.wifi_address.setText(address)
        
        if self.connection_thread and self.connection_thread.isRunning():
            return

        self.test_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setMaximum(0)
        self.progress.setFormat('正在测试连接...')

        self.connection_thread = ConnectionTestWorker(address)
        self.connection_thread.finished.connect(self.on_connection_test_finished)
        self.connection_thread.start()

    def on_connection_test_finished(self, success, status_code, content, error_message):
        """Handle completion of connection test."""
        self.progress.setVisible(False)
        self.progress.setMaximum(1)
        self.progress.setValue(0)
        self.progress.setFormat('')

        self.test_button.setEnabled(True)
        self.connection_thread = None

        if success:
            QMessageBox.information(self, '成功', '成功连接到多看阅读WiFi服务')
        else:
            if error_message:
                QMessageBox.critical(self, '错误', f'连接失败：\n{error_message}')
            else:
                QMessageBox.warning(
                    self, '连接失败',
                    f'无法连接到多看阅读WiFi服务。\n状态码: {status_code}\n响应: {content}'
                )

    def on_send_progress(self, current, total, title):
        """Update progress bar from background thread."""
        self.progress.setMaximum(total)
        self.progress.setValue(current)
        self.progress.setFormat(f'正在处理: {title}')

    def on_send_finished(self, success_count, worker_failed_books):
        """Handle completion of book sending."""
        self.progress.setVisible(False)
        self.progress.setValue(0)
        self.progress.setFormat('')

        self.send_button.setEnabled(True)
        self.test_button.setEnabled(True)

        self.send_thread = None

        failed_books = list(self.initial_failed_books)
        failed_books.extend(worker_failed_books)
        self.initial_failed_books = []

        result_message = f'成功发送 {success_count} 本书籍到多看阅读\n'
        if failed_books:
            result_message += '\n发送失败的书籍：\n'
            for book, reason in failed_books:
                result_message += f'- {book}: {reason}\n'

        if success_count > 0:
            QMessageBox.information(self, '完成', result_message)
        else:
            QMessageBox.warning(self, '失败', result_message)

    def save_settings(self):
        """保存WiFi地址设置"""
        raw_address = self.wifi_address.text().strip()
        if not raw_address:
            return error_dialog(self, '错误', '请输入多看阅读WiFi地址', show=True)
        
        address = raw_address
        if not address.startswith('http://'):
            address = 'http://' + address
            self.wifi_address.setText(address)
        
        self.plugin_action.duokan_wifi_address = address
        self.plugin_action.prefs['wifi_address'] = address
        QMessageBox.information(self, '成功', '设置已保存')
    
    def send_books(self):
        """发送选中的书籍到多看阅读"""
        if self.send_thread and self.send_thread.isRunning():
            return QMessageBox.information(self, '提示', '正在发送书籍，请稍候')

        # 确保目标地址有效
        raw_address = self.wifi_address.text().strip()
        if not raw_address:
            return error_dialog(self, '错误', '请输入多看阅读WiFi地址', show=True)

        current_address = raw_address
        if not current_address.startswith('http://'):
            current_address = 'http://' + current_address
            self.wifi_address.setText(current_address)

        self.plugin_action.duokan_wifi_address = current_address

        # 获取选中的书籍
        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows:
            return error_dialog(self, '错误', '请先选择要发送的书籍', show=True)
        
        # 获取书籍IDs
        ids = list(map(self.gui.library_view.model().id, rows))
        db = self.gui.current_db.new_api

        books_to_send = []
        self.initial_failed_books = []

        for book_id in ids:
            metadata = None
            title = f'ID {book_id}'
            try:
                metadata = db.get_metadata(book_id)
                if metadata:
                    title = metadata.title or title
            except Exception as e:
                import traceback
                error_msg = f'错误类型: {type(e).__name__}\n错误信息: {str(e)}'
                self.initial_failed_books.append((title, error_msg))
                print(f"准备书籍 {title} 时出错:\n{traceback.format_exc()}")
                continue

            epub_path = db.format_abspath(book_id, 'EPUB')
            if not epub_path:
                self.initial_failed_books.append((title, "没有EPUB格式"))
                continue

            books_to_send.append({'title': title, 'path': epub_path})

        if not books_to_send:
            result_message = '没有可发送的书籍。\n'
            if self.initial_failed_books:
                result_message += '\n发送失败的书籍：\n'
                for book, reason in self.initial_failed_books:
                    result_message += f'- {book}: {reason}\n'
            QMessageBox.warning(self, '失败', result_message)
            return

        # 准备进度条和按钮
        total = len(books_to_send)
        self.progress.setMaximum(total)
        self.progress.setValue(0)
        self.progress.setFormat('准备发送...')
        self.progress.setVisible(True)

        self.send_button.setEnabled(False)
        self.test_button.setEnabled(False)

        # 启动后台线程
        self.send_thread = SendBooksWorker(self.plugin_action, books_to_send)
        self.send_thread.progress.connect(self.on_send_progress)
        self.send_thread.finished.connect(self.on_send_finished)
        self.send_thread.start()
