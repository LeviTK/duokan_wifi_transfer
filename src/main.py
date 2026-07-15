#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import ipaddress
import sys
import threading
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

try:
    from qt.core import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox,
                         QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                         QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                         QThread, QTimer, QVBoxLayout, Qt, pyqtSignal, QProgressBar,
                         QHeaderView)
except ImportError:
    from PyQt5.Qt import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox,
                          QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                          QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                          QThread, QTimer, QVBoxLayout, Qt, pyqtSignal, QProgressBar,
                          QHeaderView)

from calibre_plugins.duokan_wifi_transfer.transport import (
    local_wifi_candidates, probe_receiver, resolve_wifi_context, saved_endpoint,
    upload_epub)


def candidate_probe_plan(devices, context, candidates):
    """Build saved-address-first probes using only selected devices' known ports."""
    network = context.network
    inside = []
    outside = []
    ports = []
    for device in devices:
        if device.get('discover'):
            if int(device['port']) not in ports:
                ports.append(int(device['port']))
            continue
        probe = (device['id'], device['host'], int(device['port']))
        try:
            address = ipaddress.IPv4Address(device['host'])
            target = inside if address in network and str(address) != context.address else outside
        except (ipaddress.AddressValueError, KeyError):
            target = outside
        target.append(probe)
        if int(device['port']) not in ports:
            ports.append(int(device['port']))
    scans = [(host, port) for port in ports for host in candidates]
    return inside + outside, scans


def assign_distinct_hosts(unreachable, found_by_port, used_by_port=None):
    """Assign only a single unambiguous host; never infer device identity by order."""
    used_by_port = used_by_port or {}
    assignments = {}
    ambiguous = []
    for port in dict.fromkeys(int(item['port']) for item in unreachable):
        devices = [item for item in unreachable if int(item['port']) == port]
        used = set(used_by_port.get(port, ()))
        hosts = [host for host in dict.fromkeys(found_by_port.get(port, ()))
                 if host not in used]
        ordinary = [item for item in devices if not item.get('discover')]
        if len(ordinary) == 1 and len(devices) == 1 and len(hosts) == 1:
            assignments[devices[0]['id']] = hosts[0]
        else:
            ambiguous.extend((host, port) for host in hosts)
    return assignments, ambiguous


def merge_discovered_devices(devices, selected_ids, endpoints, id_factory=None):
    """Pure host+port de-duplicating merge used by the manager and tests."""
    id_factory = id_factory or (lambda: uuid.uuid4().hex)
    merged = [dict(item) for item in devices]
    selected = set(selected_ids)
    known = {(item['host'].lower(), int(item['port'])): item for item in merged}
    for endpoint in endpoints:
        key = (endpoint['host'].lower(), int(endpoint['port']))
        existing = known.get(key)
        if existing is not None:
            selected.add(existing['id'])
            continue
        identifier = id_factory()
        item = {'id': identifier, 'name': endpoint.get('name') or endpoint['host'],
                'host': endpoint['host'], 'port': int(endpoint['port'])}
        merged.append(item)
        known[key] = item
        selected.add(identifier)
    return merged, selected


class DeviceEditDialog(QDialog):
    def __init__(self, parent, device=None):
        super(DeviceEditDialog, self).__init__(parent)
        device = device or {}
        self.setWindowTitle('编辑接收设备' if device else '添加接收设备')
        form = QFormLayout(self)
        self.name_edit = QLineEdit(device.get('name', ''))
        self.host_edit = QLineEdit(device.get('host', ''))
        self.port_edit = QSpinBox()
        self.port_edit.setRange(1, 65535)
        self.port_edit.setValue(int(device.get('port', 8080)))
        form.addRow('自定义名称：', self.name_edit)
        form.addRow('主机 / IPv4：', self.host_edit)
        form.addRow('端口：', self.port_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def value(self, identifier):
        host, port = saved_endpoint(self.host_edit.text(), self.port_edit.value())
        name = self.name_edit.text().strip() or host
        return {'id': identifier, 'name': name, 'host': host, 'port': port}


class DeviceManagerDialog(QDialog):
    """Single native manager; identity is always the hidden stable device ID."""
    def __init__(self, parent, devices, active_id, selected_ids, find_callback=None):
        super(DeviceManagerDialog, self).__init__(parent)
        self.devices = [dict(item) for item in devices]
        self.active_id = active_id
        self.selected_ids = set(selected_ids)
        self.find_callback = find_callback
        self.setWindowTitle('管理多看接收设备')
        self.setMinimumSize(700, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('勾选工具栏主按钮要发送到的接收设备。名称可以重复。'))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(('发送', '名称', '主机:端口', '默认'))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        header = self.table.horizontalHeader()
        resize_mode = getattr(QHeaderView, 'ResizeMode', QHeaderView)
        header.setSectionResizeMode(1, resize_mode.Stretch)
        header.setSectionResizeMode(2, resize_mode.Stretch)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        for text, slot in (('添加', self.add_device), ('编辑', self.edit_device),
                           ('删除', self.delete_device), ('设为默认', self.set_default),
                           ('测试 / 自动查找', self.find_device)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self):
        self.table.setRowCount(len(self.devices))
        for row, device in enumerate(self.devices):
            check = QCheckBox()
            check.setChecked(device['id'] in self.selected_ids)
            check.toggled.connect(
                lambda checked, did=device['id']: self.toggle_selected(did, checked))
            self.table.setCellWidget(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(device['name']))
            self.table.setItem(row, 2, QTableWidgetItem('%s:%s' %
                                                       (device['host'], device['port'])))
            self.table.setItem(row, 3, QTableWidgetItem(
                '默认' if device['id'] == self.active_id else ''))
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(3)

    def merge_discovered(self, endpoints):
        self.devices, self.selected_ids = merge_discovered_devices(
            self.devices, self.selected_ids, endpoints)
        if self.active_id is None and self.devices:
            self.active_id = self.devices[0]['id']
        self.refresh()

    def toggle_selected(self, device_id, checked):
        if checked:
            self.selected_ids.add(device_id)
        else:
            self.selected_ids.discard(device_id)

    def current_index(self):
        row = self.table.currentRow()
        return row if 0 <= row < len(self.devices) else None

    def _edit(self, index=None):
        import uuid
        old = self.devices[index] if index is not None else None
        dialog = DeviceEditDialog(self, old)
        if getattr(dialog, 'exec', dialog.exec_)() != QDialog.Accepted:
            return
        identifier = old['id'] if old else uuid.uuid4().hex
        try:
            value = dialog.value(identifier)
        except ValueError as err:
            QMessageBox.warning(self, '地址无效', str(err))
            return
        if index is None:
            self.devices.append(value)
            self.selected_ids.add(identifier)
            if self.active_id is None:
                self.active_id = identifier
        else:
            self.devices[index] = value
        self.refresh()

    def add_device(self):
        self._edit()

    def edit_device(self):
        index = self.current_index()
        if index is not None:
            self._edit(index)

    def delete_device(self):
        index = self.current_index()
        if index is None:
            return
        identifier = self.devices[index]['id']
        del self.devices[index]
        self.selected_ids.discard(identifier)
        if self.active_id == identifier:
            self.active_id = self.devices[0]['id'] if self.devices else None
        self.refresh()

    def set_default(self):
        index = self.current_index()
        if index is not None:
            self.active_id = self.devices[index]['id']
            self.selected_ids.add(self.active_id)
            self.refresh()

    def find_device(self):
        if self.find_callback:
            self.find_callback(self.devices)

    def result_data(self):
        valid = {item['id'] for item in self.devices}
        selected = [item['id'] for item in self.devices if item['id'] in self.selected_ids]
        active = self.active_id if self.active_id in valid else (
            self.devices[0]['id'] if self.devices else None)
        if not selected and active:
            selected = [active]
        return self.devices, active, selected


class ResolutionWorker(QThread):
    resolution_progress = pyqtSignal(str)
    resolution_ready = pyqtSignal(list, list, list, list, str)

    def __init__(self, devices):
        super(ResolutionWorker, self).__init__()
        self.devices = tuple(dict(item) for item in devices)
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        resolved = {}
        changes = []
        candidates_found = []
        try:
            context = None
            candidates = []
            discovery_error = ''
            if sys.platform == 'darwin':
                context = resolve_wifi_context()
                candidates = local_wifi_candidates(1024, context)
            else:
                discovery_error = '此平台不支持自动 Wi-Fi 子网查找；请手动修正无法连接的地址'
            if context is None:
                class AnyNetwork(object):
                    network = ipaddress.IPv4Network('0.0.0.0/0')
                    address = ''
                plan_context = AnyNetwork()
            else:
                plan_context = context
            saved, _scans = candidate_probe_plan(self.devices, plan_context, candidates)
            by_id = {item['id']: item for item in self.devices}
            unreachable = [item for item in self.devices if item.get('discover')]
            for identifier, host, port in saved:
                if self._cancel.is_set():
                    break
                device = by_id[identifier]
                self.resolution_progress.emit('正在测试 %s（%s:%s）' %
                                              (device['name'], host, port))
                if probe_receiver(host, port, 1.2, context)[0]:
                    resolved[identifier] = dict(device)
                else:
                    unreachable.append(device)
            # One bounded pass per distinct known port; result is reusable by
            # duplicate-port devices and no other port can enter this list.
            found_by_port = {}
            if context is not None:
                for port in dict.fromkeys(item['port'] for item in unreachable):
                    found_by_port[port] = self._find_port(port, candidates, context)
            used_by_port = {}
            for snapshot in resolved.values():
                used_by_port.setdefault(int(snapshot['port']), set()).add(snapshot['host'])
            assignments, ambiguous = assign_distinct_hosts(
                unreachable, found_by_port, used_by_port)
            candidates_found = [
                {'id': 'discovered-%s-%s' % (host, port), 'name': '%s:%s' % (host, port),
                 'host': host, 'port': port}
                for host, port in ambiguous]
            for device in unreachable:
                host = assignments.get(device['id'])
                if host:
                    snapshot = dict(device)
                    snapshot['host'] = host
                    resolved[device['id']] = snapshot
                    if host != device['host']:
                        changes.append((device['id'], device['name'], device['host'], host,
                                        device['port']))
            unresolved = [item['name'] for item in self.devices if item['id'] not in resolved]
            snapshots = [resolved[item['id']] for item in self.devices if item['id'] in resolved]
            state = 'cancelled' if self._cancel.is_set() else ''
            if not state and unresolved and discovery_error:
                state = discovery_error
            self.resolution_ready.emit(snapshots, unresolved, changes, candidates_found, state)
        except Exception as err:
            self.resolution_ready.emit([], [item['name'] for item in self.devices], [],
                                       candidates_found, str(err))

    def _find_port(self, port, candidates, context):
        pool = ThreadPoolExecutor(max_workers=20)
        jobs = {}
        iterator = iter(candidates)
        found = []
        try:
            while not self._cancel.is_set():
                while len(jobs) < 40:
                    try:
                        host = next(iterator)
                    except StopIteration:
                        break
                    jobs[pool.submit(probe_receiver, host, port, 0.7, context)] = host
                if not jobs:
                    return found
                done, _ = wait(tuple(jobs), timeout=0.1, return_when=FIRST_COMPLETED)
                for job in done:
                    host = jobs.pop(job)
                    if job.result()[0]:
                        found.append(host)
            return found
        finally:
            for job in jobs:
                job.cancel()
            pool.shutdown(wait=True)


class LookupWorker(ResolutionWorker):
    """Explicit lookup uses the same saved-first resolver implementation."""


class SendBooksWorker(QThread):
    upload_progress = pyqtSignal(int, int, str, str)
    upload_ready = pyqtSignal(list)

    def __init__(self, endpoints, books):
        super(SendBooksWorker, self).__init__()
        self.endpoints = tuple(dict(item) for item in endpoints)
        self.books = tuple(dict(item) for item in books)
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        total = len(self.endpoints) * len(self.books)
        current = 0
        results = []
        for endpoint in self.endpoints:
            if self._cancel.is_set():
                break
            successes = []
            failures = []
            for book in self.books:
                if self._cancel.is_set():
                    break
                current += 1
                self.upload_progress.emit(current, total, endpoint['name'], book['title'])
                ok, error = upload_epub(endpoint['host'], endpoint['port'],
                                        book['path'], book['title'],
                                        cancel_event=self._cancel)
                if ok:
                    successes.append(book['title'])
                else:
                    failures.append((book['title'], error or '发送失败'))
            results.append({'id': endpoint['id'], 'name': endpoint['name'],
                            'successes': successes, 'failures': failures})
        self.upload_ready.emit(results)


class DuokanWiFiDialog(QDialog):
    def __init__(self, gui, endpoints, unresolved=None, auto_start=False):
        super(DuokanWiFiDialog, self).__init__(gui)
        self.gui = gui
        self.endpoints = tuple(dict(item) for item in endpoints)
        self.unresolved = list(unresolved or [])
        self.worker = None
        self.shutting_down = False
        self.setWindowTitle('发送到多看接收设备')
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('接收设备：%s' % '、'.join(x['name'] for x in self.endpoints)))
        self.status = QLabel('准备发送')
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.send_button = QPushButton('发送选中的 EPUB')
        self.send_button.clicked.connect(self.send_books)
        layout.addWidget(self.send_button)
        self.close_button = QPushButton('关闭')
        self.close_button.clicked.connect(self.close)
        layout.addWidget(self.close_button)
        if auto_start:
            QTimer.singleShot(0, self.send_books)

    def reject(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, '任务进行中', '请等待上传完成。')
        else:
            super(DuokanWiFiDialog, self).reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super(DuokanWiFiDialog, self).closeEvent(event)

    def send_books(self):
        if self.worker and self.worker.isRunning():
            return
        rows = self.gui.library_view.selectionModel().selectedRows()
        db = self.gui.current_db.new_api
        books = []
        skipped = []
        for book_id in map(self.gui.library_view.model().id, rows):
            metadata = db.get_metadata(book_id)
            title = metadata.title or 'ID %s' % book_id
            path = db.format_abspath(book_id, 'EPUB')
            if path:
                books.append({'title': title, 'path': path})
            else:
                skipped.append(title)
        if not books:
            QMessageBox.warning(self, '没有 EPUB', '所选书籍均没有 EPUB 格式。')
            return
        self.skipped = skipped
        self.send_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.worker = SendBooksWorker(self.endpoints, books)
        self.progress.setMaximum(len(self.endpoints) * len(books))
        self.progress.setValue(0)
        self.worker.upload_progress.connect(self.on_progress)
        self.worker.upload_ready.connect(self.on_result)
        self.worker.finished.connect(self.on_stopped)
        self.worker.start()

    def on_progress(self, current, total, device, title):
        self.progress.setMaximum(total)
        self.progress.setValue(current)
        self.status.setText('%s / %s：%s → %s' % (current, total, title, device))

    def on_result(self, results):
        if self.shutting_down:
            return
        lines = []
        for result in results:
            lines.append('%s：成功 %s，失败 %s' %
                         (result['name'], len(result['successes']), len(result['failures'])))
            lines.extend('  %s：%s' % item for item in result['failures'])
        if self.unresolved:
            lines.extend('%s：未连接，已跳过全部所选书籍' % name
                         for name in self.unresolved)
        if self.skipped:
            for endpoint in self.endpoints:
                lines.append('%s：无 EPUB，已跳过 %s' %
                             (endpoint['name'], '、'.join(self.skipped)))
        QMessageBox.information(self, '发送结果', '\n'.join(lines))

    def on_stopped(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()
        self.send_button.setEnabled(True)
        self.close_button.setEnabled(True)

    def cancel_and_wait(self):
        self.shutting_down = True
        worker = self.worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait()
