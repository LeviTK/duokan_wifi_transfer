#!/usr/bin/env python3
"""Build, verify, and install the Duokan WiFi calibre plugin."""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
DIST_DIR = ROOT / "dist"
TEST_SCRIPT = ROOT / "tests" / "calibre_integration.py"
PLUGIN_NAME = "WiFi传书"
LEGACY_PLUGIN_NAMES = ("多看阅读WiFi传书",)
PLUGIN_IMPORT_NAME = "duokan_wifi_transfer"
ARCHIVE_PREFIX = "duokan_wifi_transfer_v"
CALIBRE_APP_BIN = Path("/Applications/calibre.app/Contents/MacOS")
REQUIRED_FILES = {
    "__init__.py",
    "main.py",
    "transport.py",
    "ui.py",
    "plugin-import-name-duokan_wifi_transfer.txt",
    "images/icon.png",
    "images/plugin.png",
}


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def plugin_version() -> str:
    tree = ast.parse((SRC_DIR / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "DuokanWifiBase":
            continue
        for item in node.body:
            if not isinstance(item, ast.Assign):
                continue
            if any(isinstance(target, ast.Name) and target.id == "version" for target in item.targets):
                value = ast.literal_eval(item.value)
                if not isinstance(value, tuple) or not all(isinstance(part, int) for part in value):
                    fail("DuokanWifiBase.version 必须是整数元组")
                return ".".join(str(part) for part in value)
    fail("无法从 src/__init__.py 读取 DuokanWifiBase.version")


def source_files() -> list[Path]:
    files: list[Path] = []
    for path in SRC_DIR.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(SRC_DIR)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"} or path.name == ".DS_Store":
            continue
        files.append(path)
    return sorted(files, key=lambda path: path.relative_to(SRC_DIR).as_posix())


def archive_path() -> Path:
    return DIST_DIR / f"{ARCHIVE_PREFIX}{plugin_version()}.zip"


def build_archive() -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    output = archive_path()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in source_files():
            relative = path.relative_to(SRC_DIR).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"BUILD OK: {output}")
    print(f"SHA256: {digest}")
    return output


def static_verify(output: Path) -> None:
    actual_files = {path.relative_to(SRC_DIR).as_posix() for path in source_files()}
    missing = REQUIRED_FILES - actual_files
    if missing:
        fail(f"源码缺少必要文件: {', '.join(sorted(missing))}")

    python_files = sorted(SRC_DIR.glob("*.py")) + sorted((ROOT / "tests").glob("*.py"))
    for path in python_files:
        compile(path.read_bytes(), str(path), "exec")

    with zipfile.ZipFile(output) as archive:
        bad_file = archive.testzip()
        if bad_file:
            fail(f"ZIP 完整性检查失败: {bad_file}")
        packaged_files = {name for name in archive.namelist() if not name.endswith("/")}
    if packaged_files != actual_files:
        missing_from_zip = actual_files - packaged_files
        unexpected = packaged_files - actual_files
        fail(
            "ZIP 内容与 src 不一致；"
            f"缺少={sorted(missing_from_zip)}，多出={sorted(unexpected)}"
        )
    print(f"STATIC OK: {len(python_files)} 个 Python 文件通过语法检查")
    print(f"PACKAGE OK: {len(packaged_files)} 个文件与 src 一致")


def calibre_command(name: str) -> str:
    configured = os.environ.get("CALIBRE_BIN")
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser() / name)
    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
    candidates.append(CALIBRE_APP_BIN / name)
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    fail(
        f"找不到 {name}；请把 /Applications/calibre.app/Contents/MacOS 加入 PATH，"
        "或设置 CALIBRE_BIN"
    )


def run(command: list[str], *, env: dict[str, str] | None = None, capture: bool = False) -> subprocess.CompletedProcess[str]:
    printable = " ".join(command)
    print(f"RUN: {printable}")
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def isolated_environment(base: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key, directory in {
        "CALIBRE_CONFIG_DIRECTORY": base / "config",
        "CALIBRE_CACHE_DIRECTORY": base / "cache",
        "CALIBRE_TEMP_DIR": base / "temp",
    }.items():
        directory.mkdir(parents=True, exist_ok=True)
        env[key] = str(directory)
    return env


def assert_plugin_listed(output: str) -> None:
    version_tuple = str(tuple(int(part) for part in plugin_version().split(".")))
    if PLUGIN_NAME not in output or version_tuple not in output:
        fail(f"Calibre 插件列表未显示预期插件和版本:\n{output}")


def calibre_verify(output: Path) -> None:
    customize = calibre_command("calibre-customize")
    debug = calibre_command("calibre-debug")
    with tempfile.TemporaryDirectory(prefix="duokan-calibre-test.") as temp:
        env = isolated_environment(Path(temp))

        # Validate calibre's official development build/update path.
        run([customize, "-b", str(SRC_DIR)], env=env)
        listed = run([customize, "-l"], env=env, capture=True).stdout
        assert_plugin_listed(listed)

        # Validate the exact release ZIP as a fresh installation.
        run([customize, "-r", PLUGIN_NAME], env=env)
        run([customize, "-a", str(output)], env=env)
        listed = run([customize, "-l"], env=env, capture=True).stdout
        assert_plugin_listed(listed)

        import_check = (
            "import calibre.customize.ui as u; "
            "u.initialize_plugins(); "
            f"p=u.find_plugin({PLUGIN_NAME!r}); "
            "assert p is not None; "
            f"from calibre_plugins.{PLUGIN_IMPORT_NAME}.ui import InterfacePlugin; "
            f"from calibre_plugins.{PLUGIN_IMPORT_NAME}.main import "
            "DeviceManagerDialog, DuokanWiFiDialog, ResolutionWorker, SendBooksWorker; "
            f"from calibre_plugins.{PLUGIN_IMPORT_NAME}.transport import probe_receiver; "
            "print('IMPORT OK:', p.name, p.version, InterfacePlugin.name, "
            "DeviceManagerDialog.__name__, DuokanWiFiDialog.__name__, "
            "ResolutionWorker.__name__, SendBooksWorker.__name__)"
        )
        run([debug, "-c", import_check], env=env)
        run([debug, "-e", str(TEST_SCRIPT)], env=env)
    print("CALIBRE OK: 隔离构建、ZIP 安装、插件导入和模拟上传全部通过")


def verify() -> Path:
    output = build_archive()
    static_verify(output)
    calibre_verify(output)
    print("VERIFY OK")
    return output


def calibre_config_dir(debug: str) -> Path:
    result = run(
        [debug, "-c", "from calibre.constants import config_dir; print(config_dir)"],
        capture=True,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        fail("无法确定 Calibre 配置目录")
    return Path(lines[-1]).expanduser()


def backup_installed_plugin(config_dir: Path, plugin_name: str) -> Path | None:
    installed = config_dir / "plugins" / f"{plugin_name}.zip"
    if not installed.exists():
        print(f"BACKUP: 未发现 {plugin_name}，跳过")
        return None
    backup_dir = DIST_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"{plugin_name}_{timestamp}.zip"
    shutil.copy2(installed, backup)
    print(f"BACKUP OK: {backup}")
    return backup


def calibre_is_running() -> bool:
    result = subprocess.run(
        ["pgrep", "-x", "calibre"],
        check=False,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        return True
    if result.returncode not in {1}:
        print("WARNING: 无法读取 Calibre 进程状态，请确认已正常退出 Calibre。")
    return False


def install(*, shutdown: bool) -> None:
    customize = calibre_command("calibre-customize")
    debug = calibre_command("calibre-debug")
    if not shutdown and calibre_is_running():
        fail("Calibre 正在运行；请正常退出后重试，或明确执行 make install-shutdown")

    output = verify()
    if shutdown:
        print("正在请求 Calibre 安全关闭；请确认没有正在执行的重要任务。")
        subprocess.run([debug, "-s"], cwd=ROOT, check=False)
    else:
        print("Calibre 未运行，继续安装。")

    config_dir = calibre_config_dir(debug)
    for plugin_name in (PLUGIN_NAME, *LEGACY_PLUGIN_NAMES):
        backup_installed_plugin(config_dir, plugin_name)
    for legacy_name in LEGACY_PLUGIN_NAMES:
        legacy_zip = config_dir / "plugins" / f"{legacy_name}.zip"
        if legacy_zip.exists():
            run([customize, "-r", legacy_name])
            print(f"MIGRATION: 已移除旧名称插件 {legacy_name}")
    run([customize, "-a", str(output)])
    listed = run([customize, "-l"], capture=True).stdout
    assert_plugin_listed(listed)
    print(f"INSTALL OK: {PLUGIN_NAME} {plugin_version()}")
    print("下一步运行 make user-test 进入人工验收。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build", help="生成可重复的版本化 ZIP")
    subparsers.add_parser("verify", help="运行静态、打包和隔离 Calibre 测试")
    install_parser = subparsers.add_parser("install", help="验证、备份并安装到日常 Calibre")
    install_parser.add_argument(
        "--shutdown",
        action="store_true",
        help="安装前调用 calibre-debug -s 关闭正在运行的 Calibre",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "build":
        static_verify(build_archive())
    elif args.command == "verify":
        verify()
    elif args.command == "install":
        install(shutdown=args.shutdown)
    else:
        fail(f"未知命令: {args.command}")


if __name__ == "__main__":
    main()
