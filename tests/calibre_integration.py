#!/usr/bin/env python3
"""Calibre-hosted direct transport integration tests."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ipaddress
import os
import tempfile
import threading
from unittest.mock import patch

import calibre.customize.ui as plugin_ui

PAYLOAD = b"PK\x03\x04duokan-automation-test-epub"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = self.server.probe_body.encode('utf-8')
        self.send_response(200); self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        self.server.path = self.path
        self.server.body = self.rfile.read(int(self.headers['Content-Length']))
        self.server.headers_seen = self.headers
        self.send_response(200); self.end_headers()

    def log_message(self, *args): pass


def main():
    try:
        from qt.core import QApplication
    except ImportError:
        from PyQt5.Qt import QApplication
    app = QApplication.instance() or QApplication([])
    plugin_ui.initialize_plugins()
    from calibre_plugins.duokan_wifi_transfer.main import (
        DeviceManagerDialog, LookupWorker, ResolutionWorker, SendBooksWorker,
        assign_distinct_hosts, candidate_probe_plan, merge_discovered_devices)
    from calibre_plugins.duokan_wifi_transfer import transport
    from calibre_plugins.duokan_wifi_transfer.transport import (
        DirectHTTPConnection, WifiContext, WifiSetupError, endpoint,
        local_wifi_candidates, probe_receiver, saved_endpoint, upload_epub)
    from calibre_plugins.duokan_wifi_transfer.ui import normalize_devices

    assert all('finished' not in cls.__dict__ for cls in
               (ResolutionWorker, SendBooksWorker, LookupWorker))
    endpoint_snapshot = {'id': 'stable', 'name': 'test', 'host': '127.0.0.1', 'port': 1}
    worker = SendBooksWorker([endpoint_snapshot], [])
    endpoint_snapshot['host'] = 'changed'
    assert worker.endpoints[0]['host'] == '127.0.0.1'
    assert not hasattr(worker, 'plugin_action')
    assert 'upload_ready' in SendBooksWorker.__dict__
    assert 'resolution_ready' in ResolutionWorker.__dict__

    manager = DeviceManagerDialog(None, [
        {'id': 'gui-device', 'name': 'GUI 测试', 'host': '192.168.1.2', 'port': 8080},
    ], 'gui-device', ['gui-device'])
    assert manager.minimumWidth() >= 700
    assert manager.minimumHeight() >= 420
    assert manager.table.rowCount() == 1
    assert manager.result_data()[2] == ['gui-device']
    manager.close()
    manager.deleteLater()
    app.processEvents()

    assert endpoint('192.168.1.2') == ('192.168.1.2', 8080)
    assert endpoint('http://reader.local:9090/') == ('reader.local', 9090)
    for invalid in (
            None, '', 'https://192.168.1.2:8080', 'http://user@192.168.1.2:8080',
            'http://192.168.1.2:8080/files', 'http://192.168.1.2:8080/?x=1',
            '999.999.999.999', 'bad host', 'http://[::1]:8080'):
        try:
            endpoint(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid endpoint accepted: %r' % (invalid,))
    for invalid in ('127.0.0.1', '0.0.0.0', '224.0.0.1', '255.255.255.255'):
        try:
            saved_endpoint(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('unsafe saved endpoint accepted: %s' % invalid)

    normalized, active, selected = normalize_devices([
        {'id': 'same', 'name': '手机', 'host': '192.168.1.2', 'port': 8080},
        {'id': 'same', 'name': '手机', 'host': '192.168.1.3', 'port': 8080},
        {'name': '平板', 'host': '192.168.1.4', 'port': 8080},
        {'id': 'bad', 'name': '无效', 'host': '127.0.0.1', 'port': 8080},
    ], 'missing', ['missing', 'same'], iter(('new-1', 'new-2')).__next__)
    assert len(normalized) == 3
    assert [item['id'] for item in normalized] == ['same', 'new-1', 'new-2']
    assert active == 'same'
    assert selected == ['same']
    _normalized, _active, fallback = normalize_devices(normalized, 'same', ['stale'])
    assert fallback == ['same']

    context = WifiContext('en0', '192.168.2.1', ipaddress.IPv4Network('192.168.2.0/30'))
    assert local_wifi_candidates(10, context) == ['192.168.2.2']
    saved, scans = candidate_probe_plan([
        {'id': 'a', 'name': 'same', 'host': '192.168.2.2', 'port': 12121},
        {'id': 'b', 'name': 'same', 'host': '10.0.0.3', 'port': 9999},
        {'id': 'c', 'name': 'discover', 'host': '10.0.0.4', 'port': 12121,
         'discover': True},
    ], context, ['192.168.2.2'])
    assert saved == [
        ('a', '192.168.2.2', 12121),
        ('b', '10.0.0.3', 9999),
    ]
    assert scans == [('192.168.2.2', 12121), ('192.168.2.2', 9999)]
    ordered, _ = candidate_probe_plan([
        {'id': 'out', 'host': '10.0.0.2', 'port': 1},
        {'id': 'name', 'host': 'reader.local', 'port': 2},
        {'id': 'in', 'host': '192.168.2.2', 'port': 3},
    ], context, [])
    assert [item[0] for item in ordered] == ['in', 'out', 'name']

    duplicate_port = [
        {'id': 'one', 'port': 8080}, {'id': 'two', 'port': 8080},
    ]
    assigned, ambiguous = assign_distinct_hosts(
        duplicate_port, {8080: ['192.168.2.2', '192.168.2.3']})
    assert assigned == {}
    assert ambiguous == [('192.168.2.2', 8080), ('192.168.2.3', 8080)]
    assigned, ambiguous = assign_distinct_hosts(duplicate_port, {8080: ['192.168.2.2']})
    assert assigned == {}
    assert ambiguous == [('192.168.2.2', 8080)]
    assigned, ambiguous = assign_distinct_hosts(
        [{'id': 'only', 'port': 8080}], {8080: ['192.168.2.2', '192.168.2.3']})
    assert assigned == {}
    assert ambiguous == [('192.168.2.2', 8080), ('192.168.2.3', 8080)]
    assigned, ambiguous = assign_distinct_hosts(
        [{'id': 'only', 'port': 8080}], {8080: ['192.168.2.2']})
    assert assigned == {'only': '192.168.2.2'}
    assert ambiguous == []
    assigned, ambiguous = assign_distinct_hosts(
        [{'id': 'only', 'port': 8080}],
        {8080: ['192.168.2.2', '192.168.2.3']},
        {8080: {'192.168.2.2'}})
    assert assigned == {'only': '192.168.2.3'}
    assert ambiguous == []
    assigned, ambiguous = assign_distinct_hosts(
        [{'id': 'lookup', 'port': 8080, 'discover': True}],
        {8080: ['192.168.2.2', '192.168.2.3']})
    assert assigned == {}
    assert ambiguous == [('192.168.2.2', 8080), ('192.168.2.3', 8080)]

    originals = [{'id': 'saved', 'name': '手机', 'host': '192.168.2.2', 'port': 8080}]
    additions = [
        {'host': '192.168.2.2', 'port': 8080},
        {'host': '192.168.2.3', 'port': 8080, 'name': '发现设备'},
    ]
    merged, merge_selected = merge_discovered_devices(
        originals, set(), additions, iter(('new',)).__next__)
    assert [item['id'] for item in merged] == ['saved', 'new']
    assert merge_selected == {'saved', 'new'}
    merged[0]['host'] = 'changed'
    assert originals[0]['host'] == '192.168.2.2'
    oversized = WifiContext('en0', '10.0.0.1', ipaddress.IPv4Network('10.0.0.0/16'))
    try:
        local_wifi_candidates(10, oversized)
    except WifiSetupError:
        pass
    else:
        raise AssertionError('oversized subnet was silently truncated')

    class FakeSocket(object):
        def __init__(self, fail_binding=False):
            self.calls = []
            self.fail_binding = fail_binding

        def settimeout(self, timeout):
            self.calls.append(('timeout', timeout))

        def setsockopt(self, level, option, value):
            self.calls.append(('setsockopt', level, option, value))
            if self.fail_binding:
                raise OSError('binding denied')

        def bind(self, address):
            self.calls.append(('bind', address))

        def connect(self, address):
            self.calls.append(('connect', address))

        def close(self):
            self.calls.append(('close',))

    wifi = WifiContext('en0', '192.168.0.130', ipaddress.IPv4Network('192.168.0.0/24'))
    fake = FakeSocket()
    with patch.object(transport.sys, 'platform', 'darwin'), \
            patch.object(transport.socket, 'socket', return_value=fake), \
            patch.object(transport.socket, 'gethostbyname', return_value='192.168.0.100'), \
            patch.object(transport.socket, 'if_nametoindex', return_value=15):
        DirectHTTPConnection('192.168.0.100', 8080, timeout=1, wifi_context=wifi).connect()
    operations = [call[0] for call in fake.calls]
    assert operations.index('setsockopt') < operations.index('bind') < operations.index('connect')

    failed = FakeSocket(fail_binding=True)
    with patch.object(transport.sys, 'platform', 'darwin'), \
            patch.object(transport.socket, 'socket', return_value=failed), \
            patch.object(transport.socket, 'gethostbyname', return_value='192.168.0.100'), \
            patch.object(transport.socket, 'if_nametoindex', return_value=15):
        try:
            DirectHTTPConnection('192.168.0.100', 8080, timeout=1,
                                 wifi_context=wifi).connect()
        except WifiSetupError:
            pass
        else:
            raise AssertionError('Wi-Fi binding failure did not fail closed')
    assert 'connect' not in [call[0] for call in failed.calls]

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.probe_body = '<title>WiFi 传书</title><a href="https://www.duokan.com">duokan.com</a>'
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        # A broken proxy must be irrelevant to custom direct sockets.
        old_proxy = os.environ.get('http_proxy'); os.environ['http_proxy'] = 'http://127.0.0.1:1'
        with patch('calibre_plugins.duokan_wifi_transfer.transport._darwin_wifi',
                   side_effect=AssertionError('loopback must not bind Wi-Fi')):
            ok, status, _, error = probe_receiver('127.0.0.1', server.server_port)
            assert ok and status == 200, error
            server.probe_body = 'ordinary web server duokan.com'
            assert probe_receiver('127.0.0.1', server.server_port)[0] is False
            with tempfile.TemporaryDirectory() as temp:
                epub = Path(temp) / '自动化"测试.epub'; epub.write_bytes(PAYLOAD)
                ok, error = upload_epub('127.0.0.1', server.server_port, str(epub), 'test')
                assert ok, error
        if old_proxy is None: os.environ.pop('http_proxy', None)
        else: os.environ['http_proxy'] = old_proxy
        assert server.path == '/files'
        assert int(server.headers_seen['Content-Length']) == len(server.body)
        assert b'name="newfile"' in server.body
        assert 'filename="自动化\\\"测试.epub"'.encode('utf-8') in server.body
        assert PAYLOAD in server.body
        print('TRANSPORT OK: endpoints, devices, subnet cap, Wi-Fi binding, fingerprints, '
              'proxy bypass, multipart, snapshots, signals, loopback binding')
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == '__main__': main()
