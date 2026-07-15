#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import uuid

from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.utils.config import JSONConfig
try:
    from qt.core import QDialog, QInputDialog, QMenu, QMessageBox, QProgressDialog, Qt
except ImportError:
    from PyQt5.Qt import QDialog, QInputDialog, QMenu, QMessageBox, QProgressDialog, Qt

from calibre_plugins.duokan_wifi_transfer.transport import saved_endpoint, upload_epub


def normalize_devices(raw_devices, active_id=None, selected_ids=None, id_factory=None):
    """Validate identities and normalize active and recipient selections."""
    id_factory = id_factory or (lambda: uuid.uuid4().hex)
    devices = []
    used = set()
    for raw in raw_devices if isinstance(raw_devices, (list, tuple)) else []:
        if not isinstance(raw, dict):
            continue
        try:
            host, port = saved_endpoint(raw.get('host', ''), raw.get('port', 8080))
        except (TypeError, ValueError):
            continue
        identifier = raw.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in used:
            identifier = id_factory()
            while identifier in used:
                identifier = id_factory()
        used.add(identifier)
        devices.append({'id': identifier, 'name': str(raw.get('name') or host).strip() or host,
                        'host': host, 'port': port})
    active = active_id if active_id in used else (devices[0]['id'] if devices else None)
    requested = selected_ids if isinstance(selected_ids, (list, tuple)) else []
    selected = [item['id'] for item in devices if item['id'] in requested]
    if not selected and active:
        selected = [active]
    return devices, active, selected


class InterfacePlugin(InterfaceAction):
    name = 'WiFi传书'
    action_spec = (name, None, '发送到选中的多看设备', 'Ctrl+Shift+D')

    def genesis(self):
        self.prefs = JSONConfig('plugins/duokan_wifi_transfer')
        self._migrate()
        devices, active, selected = normalize_devices(
            self.prefs.get('devices', []), self.prefs.get('active_device_id'),
            self.prefs.get('selected_device_ids', []))
        self._save_devices(devices, active, selected)
        # get_icons is injected by Calibre's plugin loader for ZIP resources.
        icon = get_icons('images/icon.png', self.name)
        self.qaction.setIcon(icon)
        clone = getattr(self, 'menuless_qaction', None)
        if clone is not None:
            clone.setIcon(icon)
        self.qaction.triggered.connect(self.send_selected)
        self.menu = QMenu(self.gui)
        self.qaction.setMenu(self.menu)
        self.resolution_worker = None
        self.resolution_progress = None
        self.current_manager = None
        self.current_send_dialog = None
        self._resolution_result = None
        self._resolution_origin_manager = None
        self._shutting_down = False
        self.rebuild_menu()

    def _migrate(self):
        if self.prefs.get('devices'):
            return
        legacy = self.prefs.get('wifi_address')
        if not isinstance(legacy, str) or not legacy.strip():
            return
        if legacy.strip().rstrip('/') == 'http://192.168.1.100:8080':
            del self.prefs['wifi_address']
            return
        try:
            host, port = saved_endpoint(legacy)
        except ValueError:
            return
        device = {'id': uuid.uuid4().hex, 'name': '原有设备', 'host': host, 'port': port}
        self.prefs['devices'] = [device]
        self.prefs['active_device_id'] = device['id']
        self.prefs['selected_device_ids'] = [device['id']]
        del self.prefs['wifi_address']

    def _save_devices(self, devices, active, selected):
        self.prefs['devices'] = devices
        self.prefs['active_device_id'] = active
        self.prefs['selected_device_ids'] = selected

    def devices(self):
        return list(self.prefs.get('devices', []))

    def selected_devices(self):
        selected = set(self.prefs.get('selected_device_ids', []))
        result = [item for item in self.devices() if item['id'] in selected]
        if result:
            return result
        active = self.prefs.get('active_device_id')
        return [item for item in self.devices() if item['id'] == active]

    def rebuild_menu(self):
        self.menu.clear()
        self.menu.addAction('发送到勾选的接收设备', self.send_selected)
        self.menu.addSeparator()
        selected = set(self.prefs.get('selected_device_ids', []))
        active = self.prefs.get('active_device_id')
        for device in self.devices():
            text = '%s%s（%s:%s）' % ('[默认] ' if device['id'] == active else '',
                                     device['name'], device['host'], device['port'])
            action = self.menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(device['id'] in selected)
            action.toggled.connect(
                lambda checked, did=device['id']: self.toggle_recipient(did, checked))
        self.menu.addSeparator()
        self.menu.addAction('自动查找…', self.lookup)
        self.menu.addAction('管理接收设备…', self.configure)

    def toggle_recipient(self, device_id, checked):
        selected = list(self.prefs.get('selected_device_ids', []))
        if checked and device_id not in selected:
            selected.append(device_id)
        elif not checked and device_id in selected:
            selected.remove(device_id)
        self.prefs['selected_device_ids'] = selected

    def configure(self, discovered=None):
        from calibre_plugins.duokan_wifi_transfer.main import DeviceManagerDialog
        dialog = DeviceManagerDialog(self.gui, self.devices(),
                                     self.prefs.get('active_device_id'),
                                     self.prefs.get('selected_device_ids', []))
        dialog.find_callback = (
            lambda devices, manager=dialog: self.lookup(devices, origin_manager=manager))
        if discovered:
            dialog.merge_discovered(discovered)
        self.current_manager = dialog
        try:
            if getattr(dialog, 'exec', dialog.exec_)() == QDialog.Accepted:
                self._save_devices(*dialog.result_data())
                self.rebuild_menu()
        finally:
            if self.current_manager is dialog:
                self.current_manager = None

    def send_selected(self):
        devices = self.selected_devices()
        if not devices:
            self.configure()
            if not self.devices():
                QMessageBox.information(self.gui, '尚无接收设备',
                                        '请手动添加设备，或使用“自动查找”。')
            return
        self._start_resolution(devices, True)

    def _start_resolution(self, devices, send_after, origin_manager=None):
        if self.resolution_worker is not None:
            return
        from calibre_plugins.duokan_wifi_transfer.main import ResolutionWorker
        worker = ResolutionWorker(devices)
        self.resolution_worker = worker
        self._send_after_resolution = send_after
        self._resolution_result = None
        self._resolution_origin_manager = (
            origin_manager if origin_manager is self.current_manager else None)
        parent = self._resolution_origin_manager or self.gui
        self.resolution_progress = QProgressDialog(
            '正在解析接收设备…', '取消', 0, 0, parent)
        self.resolution_progress.setWindowTitle('连接接收设备')
        self.resolution_progress.setAutoClose(False)
        self.resolution_progress.setWindowModality(Qt.WindowModal)
        self.resolution_progress.canceled.connect(worker.cancel)
        worker.resolution_progress.connect(self.resolution_progress.setLabelText)
        worker.resolution_ready.connect(self._resolution_ready)
        worker.finished.connect(self._resolution_stopped)
        worker.start()
        self.resolution_progress.show()

    def _resolution_ready(self, endpoints, unresolved, changes, candidates, error):
        if self.sender() is self.resolution_worker:
            self._resolution_result = (endpoints, unresolved, changes, candidates, error)

    def _resolution_stopped(self):
        worker = self.sender()
        if worker is not self.resolution_worker:
            return
        self.resolution_worker = None
        if self.resolution_progress:
            self.resolution_progress.close()
            self.resolution_progress.deleteLater()
            self.resolution_progress = None
        worker.deleteLater()
        result = self._resolution_result
        self._resolution_result = None
        origin_manager = self._resolution_origin_manager
        self._resolution_origin_manager = None
        endpoints, unresolved, changes, candidates, error = result or (
            [], [], [], [], '解析未返回结果')
        if self._shutting_down:
            return
        if error == 'cancelled':
            return
        origin_is_current = (
            origin_manager is not None and origin_manager is self.current_manager)
        if origin_manager is not None and not origin_is_current:
            return
        if error:
            error_dialog(origin_manager if origin_is_current else self.gui,
                         '设备解析失败', error, show=True)
            if not endpoints:
                if origin_is_current:
                    origin_manager.merge_discovered(candidates)
                elif origin_manager is None:
                    self.configure(candidates)
                return
        if changes:
            lines = ['%s：%s → %s（端口 %s）' % (name, old, new, port)
                     for _did, name, old, new, port in changes]
            info_dialog(self.gui, '发现设备地址变化',
                        '本次将使用已验证的新地址，不会改写保存设置：\n' + '\n'.join(lines), show=True)
        if not endpoints:
            QMessageBox.warning(self.gui, '没有可连接的设备',
                                '选中的接收设备均无法连接，请手动检查或添加地址。')
            if origin_is_current:
                origin_manager.merge_discovered(candidates)
            else:
                self.configure(candidates)
            return
        if self._send_after_resolution:
            from calibre_plugins.duokan_wifi_transfer.main import DuokanWiFiDialog
            dialog = DuokanWiFiDialog(self.gui, endpoints, unresolved, auto_start=True)
            self.current_send_dialog = dialog
            try:
                getattr(dialog, 'exec', dialog.exec_)()
            finally:
                if self.current_send_dialog is dialog:
                    self.current_send_dialog = None
        else:
            discovered = candidates or endpoints
            if origin_is_current:
                origin_manager.merge_discovered(discovered)
            elif discovered:
                self.configure(discovered)
            else:
                info_dialog(self.gui, '自动查找', '没有找到接收设备。', show=True)

    def lookup(self, devices=None, origin_manager=None):
        devices = list(devices if devices is not None else self.devices())
        if not devices:
            port, ok = QInputDialog.getInt(self.gui, '自动查找',
                                           '输入多看页面显示的端口：', 8080, 1, 65535)
            if not ok:
                return
            devices = [{'id': 'lookup', 'name': '待发现设备',
                        'host': '192.168.0.1', 'port': port, 'discover': True}]
        self._start_resolution(devices, False, origin_manager)

    def shutting_down(self):
        self._shutting_down = True
        worker = self.resolution_worker
        if worker:
            worker.cancel()
            worker.wait()
        dialog = self.current_send_dialog
        if dialog is not None:
            dialog.cancel_and_wait()
            dialog.close()

    def send_book_to_duokan(self, epub_path, title, endpoint_snapshot=None):
        target = endpoint_snapshot or (self.selected_devices() or [None])[0]
        if target is None:
            return False, '未配置接收设备'
        return upload_epub(target['host'], target['port'], epub_path, title)

    show_dialog = send_selected
