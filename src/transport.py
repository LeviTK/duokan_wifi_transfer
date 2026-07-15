#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Direct (proxy-free) Duokan HTTP transport."""

import http.client
import ipaddress
import mimetypes
import os
import re
import socket
import subprocess
import sys
import uuid
from collections import namedtuple
from urllib.parse import urlsplit

FINGERPRINTS = ('WiFi 传书', 'duokan.com')
MAX_RESPONSE = 256 * 1024
WifiContext = namedtuple('WifiContext', 'interface address network')


class WifiSetupError(OSError):
    """The operation could not be constrained to the active Wi-Fi network."""


def endpoint(value, port=8080):
    """Parse a bare host[:port] or an HTTP endpoint without a URL path."""
    if value is None:
        raise ValueError('地址无效')
    raw = str(value).strip()
    if not raw:
        raise ValueError('地址无效')
    if '://' not in raw:
        raw = 'http://' + raw
    try:
        parsed = urlsplit(raw)
        parsed_port = parsed.port
    except ValueError as err:
        raise ValueError('地址或端口无效：%s' % err)
    if (parsed.scheme.lower() != 'http' or parsed.username is not None or
            parsed.password is not None or parsed.query or parsed.fragment or
            parsed.path not in ('', '/') or not parsed.hostname):
        raise ValueError('仅支持 http://主机:端口，不允许凭据、路径、查询或片段')
    host = parsed.hostname
    # The receiver protocol and discovery are IPv4-only. Hostnames remain valid.
    if ':' in host:
        raise ValueError('不支持 IPv6 地址')
    if any(ch.isspace() for ch in host):
        raise ValueError('主机名无效')
    try:
        ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        if re.fullmatch(r'[0-9.]+', host):
            raise ValueError('IPv4 地址无效')
        labels = host.rstrip('.').split('.')
        if (not all(labels) or len(host) > 253 or
                any(len(label) > 63 or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?', label)
                    for label in labels)):
            raise ValueError('主机名无效')
    result_port = parsed_port if parsed_port is not None else int(port)
    if not 1 <= result_port <= 65535:
        raise ValueError('端口无效')
    return host, result_port


def saved_endpoint(value, port=8080):
    """Validate an endpoint suitable for persistence in the receiver list."""
    host, result_port = endpoint(value, port)
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        return host, result_port
    if (address.is_loopback or address.is_unspecified or address.is_multicast or
            address.is_reserved or
            int(address) == 0xffffffff):
        raise ValueError('接收设备必须是可单播的非回环 IPv4 地址')
    return host, result_port


def resolve_wifi_context():
    """Resolve one immutable native Wi-Fi interface/address/network snapshot."""
    if sys.platform != 'darwin':
        raise WifiSetupError('此平台不支持可靠的自动 Wi-Fi 查找，请手动配置接收设备')
    try:
        ports = subprocess.check_output(
            ['/usr/sbin/networksetup', '-listallhardwareports'],
            stderr=subprocess.STDOUT, timeout=3, universal_newlines=True)
    except Exception as err:
        raise WifiSetupError('无法检测 Wi-Fi 接口：%s' % err)
    names = []
    for block in ports.split('\n\n'):
        if re.search(r'^Hardware Port: (Wi-Fi|AirPort)$', block, re.MULTILINE):
            match = re.search(r'^Device:\s*(\S+)', block, re.MULTILINE)
            if match:
                names.append(match.group(1))
    for name in names:
        try:
            output = subprocess.check_output(
                ['/sbin/ifconfig', name], stderr=subprocess.STDOUT, timeout=3,
                universal_newlines=True)
            match = re.search(r'^\s*inet\s+(\d+(?:\.\d+){3})\s+netmask\s+(0x[0-9a-fA-F]+|\d+(?:\.\d+){3})',
                              output, re.MULTILINE)
            if not match:
                continue
            address, mask = match.groups()
            if mask.lower().startswith('0x'):
                mask = str(ipaddress.IPv4Address(int(mask, 16)))
            network = ipaddress.IPv4Network('%s/%s' % (address, mask), strict=False)
            return WifiContext(name, address, network)
        except Exception:
            continue
    raise WifiSetupError('未找到具有有效 IPv4 和子网掩码的活动 Wi-Fi 接口')


# Kept as a compatibility seam for older tests/extensions.
def _darwin_wifi():
    context = resolve_wifi_context()
    return context.interface, context.address


class DirectHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
                 wifi_context=None):
        self.wifi_context = wifi_context
        super(DirectHTTPConnection, self).__init__(host, port, timeout=timeout)

    def connect(self):
        target = ipaddress.ip_address(socket.gethostbyname(self.host))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            if (sys.platform == 'darwin' and not target.is_loopback and
                    (self.wifi_context is not None or target.is_private)):
                context = self.wifi_context or resolve_wifi_context()
                try:
                    sock.setsockopt(socket.IPPROTO_IP, getattr(socket, 'IP_BOUND_IF', 25),
                                    socket.if_nametoindex(context.interface))
                    sock.bind((context.address, 0))
                except Exception as err:
                    raise WifiSetupError('无法绑定活动 Wi-Fi 接口 %s：%s' %
                                         (context.interface, err))
            sock.connect((str(target), self.port))
            self.sock = sock
        except Exception:
            sock.close()
            raise


def _error(action, err):
    if isinstance(err, WifiSetupError):
        return '%s失败（Wi-Fi 设置/绑定）：%s' % (action, err)
    if isinstance(err, ConnectionRefusedError):
        return '%s失败：连接被拒绝，请确认多看已开启 WiFi 传书' % action
    if isinstance(err, socket.timeout):
        return '%s失败：连接超时' % action
    return '%s失败：%s' % (action, err)


def probe_receiver(host, port=8080, timeout=2.0, wifi_context=None):
    conn = None
    try:
        host, port = endpoint(host, port)
        conn = DirectHTTPConnection(host, port, timeout=timeout, wifi_context=wifi_context)
        conn.request('GET', '/', headers={'User-Agent': 'Calibre Duokan Plugin/1.3'})
        response = conn.getresponse()
        content = response.read(MAX_RESPONSE + 1)
        if len(content) > MAX_RESPONSE:
            return False, response.status, '', '响应内容过大'
        text = content.decode('utf-8', errors='replace')
        success = response.status == 200 and all(mark in text for mark in FINGERPRINTS)
        return success, response.status, text, '' if success else '响应不是多看 WiFi 传书服务'
    except WifiSetupError:
        # Discovery supplies an operation context and must not turn a binding
        # failure into an ordinary per-host negative result.
        if wifi_context is not None:
            raise
        err = sys.exc_info()[1]
        return False, 0, '', _error('连接', err)
    except Exception as err:
        return False, 0, '', _error('连接', err)
    finally:
        if conn:
            conn.close()


def _multipart_filename(path):
    filename = os.path.basename(path)
    if '\r' in filename or '\n' in filename:
        raise ValueError('文件名不能包含换行符')
    return filename.replace('\\', '\\\\').replace('"', '\\"')


def upload_epub(host, port, epub_path, title='', timeout=30, wifi_context=None,
                cancel_event=None):
    conn = None
    try:
        if cancel_event is not None and cancel_event.is_set():
            return False, '上传已取消'
        host, port = endpoint(host, port)
        boundary = uuid.uuid4().hex
        filename = _multipart_filename(epub_path)
        content_type = mimetypes.guess_type(os.path.basename(epub_path))[0] or 'application/epub+zip'
        head = ('--%s\r\nContent-Disposition: form-data; name="newfile"; filename="%s"\r\n'
                'Content-Type: %s\r\n\r\n' % (boundary, filename, content_type)).encode('utf-8')
        tail = ('\r\n--%s--\r\n' % boundary).encode('ascii')
        length = len(head) + os.path.getsize(epub_path) + len(tail)
        conn = DirectHTTPConnection(host, port, timeout=timeout, wifi_context=wifi_context)
        conn.putrequest('POST', '/files')
        conn.putheader('User-Agent', 'Calibre Duokan Plugin/1.3')
        conn.putheader('Content-Type', 'multipart/form-data; boundary=%s' % boundary)
        conn.putheader('Content-Length', str(length))
        conn.endheaders()
        conn.send(head)
        with open(epub_path, 'rb') as stream:
            for chunk in iter(lambda: stream.read(64 * 1024), b''):
                if cancel_event is not None and cancel_event.is_set():
                    return False, '上传已取消'
                conn.send(chunk)
        if cancel_event is not None and cancel_event.is_set():
            return False, '上传已取消'
        conn.send(tail)
        response = conn.getresponse()
        response.read(MAX_RESPONSE)
        if response.status != 200:
            return False, '上传失败：HTTP 状态码 %s' % response.status
        return True, None
    except Exception as err:
        return False, _error('上传《%s》' % title if title else '上传', err)
    finally:
        if conn:
            conn.close()


def local_wifi_candidates(cap=1024, wifi_context=None):
    context = wifi_context or resolve_wifi_context()
    candidates = []
    for ip in context.network.hosts():
        address = str(ip)
        if address == context.address:
            continue
        if len(candidates) >= cap:
            raise WifiSetupError('Wi-Fi 子网候选地址超过安全上限 %s；请手动配置设备' % cap)
        candidates.append(address)
    return candidates
