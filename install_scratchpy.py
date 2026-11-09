#!/usr/bin/env python3
"""Install ScratchPy from the official GitHub repository on Windows."""
import os
import shutil
import subprocess
import sys
import tempfile
import ctypes
from ctypes import wintypes
import urllib.error
import urllib.request
from pathlib import Path


BASE_URL = "https://raw.githubusercontent.com/redcat67400-rgb/ScratchPy/program/"
FILES = {
    "scratchpy.pyw": BASE_URL + "scratchpy.pyw",
    "scratchpy_logo.ico": BASE_URL + "scratchpy_logo.ico",
    "install_scratchpy.py": BASE_URL + "install_scratchpy.py",
}
MAX_DOWNLOAD_SIZE = 5 * 1024 * 1024
MAX_INSTALLER_SIZE = 1024 * 1024


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "ScratchPy installer"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(MAX_DOWNLOAD_SIZE + 1)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise RuntimeError(
                "GitHub does not contain %s yet. Publish the app and icon files "
                "in the program branch, then run this installer again." % url) from None
        raise RuntimeError("GitHub download failed with HTTP %d: %s" %
                           (error.code, url)) from None
    if not data or len(data) > MAX_DOWNLOAD_SIZE:
        raise RuntimeError("Invalid or oversized download: %s" % url)
    return data


def validate_downloads(files):
    source = files["scratchpy.pyw"].decode("utf-8-sig")
    compile(source, "scratchpy.pyw", "exec")
    installer_source = files["install_scratchpy.py"].decode("utf-8-sig")
    if len(files["install_scratchpy.py"]) > MAX_INSTALLER_SIZE:
        raise RuntimeError("The downloaded installer is too large.")
    compile(installer_source, "install_scratchpy.py", "exec")
    icon = files["scratchpy_logo.ico"]
    if len(icon) < 6 or icon[:4] != b"\x00\x00\x01\x00":
        raise RuntimeError("The downloaded application icon is not a valid ICO file.")


def stage_files(folder, files):
    staged = {}
    try:
        for name, data in files.items():
            fd, temp_path = tempfile.mkstemp(prefix="." + name + ".", dir=folder)
            staged[name] = Path(temp_path)
            with os.fdopen(fd, "wb") as output:
                output.write(data)
        for name, temp_path in staged.items():
            os.replace(temp_path, folder / name)
    finally:
        for temp_path in staged.values():
            temp_path.unlink(missing_ok=True)


def wait_for_process(pid):
    if not pid:
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x00100000, False, pid)
    if not handle:
        return
    try:
        result = kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
        if result != 0:
            raise RuntimeError("Could not wait for the running ScratchPy process to close.")
    finally:
        kernel32.CloseHandle(handle)


def pythonw_path():
    current = Path(sys.executable)
    if current.name.lower() == "pythonw.exe":
        return current
    base_pythonw = Path(sys.base_prefix) / "pythonw.exe"
    if base_pythonw.is_file():
        return base_pythonw
    sibling = current.with_name("pythonw.exe")
    if sibling.is_file():
        return sibling
    located = shutil.which("pythonw.exe")
    if located:
        return Path(located)
    raise RuntimeError("Python 3 with pythonw.exe is required to run ScratchPy.")


def create_shortcut(folder, script_path, icon_path, interpreter):
    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise RuntimeError("Windows PowerShell was not found; cannot create the shortcut.")
    command = r"""
$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
if ([string]::IsNullOrWhiteSpace($desktop)) { throw 'The Desktop folder was not found.' }
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $desktop 'ScratchPy.lnk'))
$shortcut.TargetPath = $env:SCRATCHPY_INTERPRETER
$shortcut.Arguments = '"' + $env:SCRATCHPY_SCRIPT + '"'
$shortcut.WorkingDirectory = $env:SCRATCHPY_FOLDER
$shortcut.IconLocation = $env:SCRATCHPY_ICON
$shortcut.Description = 'ScratchPy - program in Python with blocks'
$shortcut.Save()
"""
    env = os.environ.copy()
    env.update({
        "SCRATCHPY_INTERPRETER": str(interpreter),
        "SCRATCHPY_SCRIPT": str(script_path),
        "SCRATCHPY_FOLDER": str(folder),
        "SCRATCHPY_ICON": str(icon_path),
    })
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError("Could not create the desktop shortcut: %s" % detail)


def install():
    if sys.platform != "win32":
        raise RuntimeError("This installer is for Windows only.")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("The Windows LOCALAPPDATA folder could not be found.")
    folder = Path(local_app_data) / "ScratchPy"
    folder.mkdir(parents=True, exist_ok=True)

    print("Downloading ScratchPy from GitHub...")
    files = {name: download(url) for name, url in FILES.items()}
    validate_downloads(files)

    stage_files(folder, files)

    script_path = folder / "scratchpy.pyw"
    icon_path = folder / "scratchpy_logo.ico"
    interpreter = pythonw_path()
    create_shortcut(folder, script_path, icon_path, interpreter)
    print("ScratchPy installed in: %s" % folder)
    print("Desktop shortcut created: ScratchPy")


def update_existing(wait_pid=0, restart=False):
    if sys.platform != "win32":
        raise RuntimeError("This updater is for Windows only.")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("The Windows LOCALAPPDATA folder could not be found.")
    folder = Path(local_app_data) / "ScratchPy"
    if not (folder / "scratchpy.pyw").is_file():
        raise RuntimeError("ScratchPy is not installed in %s." % folder)

    print("Downloading the ScratchPy update...")
    files = {name: download(url) for name, url in FILES.items()}
    validate_downloads(files)
    wait_for_process(wait_pid)
    stage_files(folder, files)

    script_path = folder / "scratchpy.pyw"
    if restart:
        interpreter = pythonw_path()
        subprocess.Popen(
            [str(interpreter), str(script_path)], cwd=str(folder),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=(getattr(subprocess, "DETACHED_PROCESS", 0) |
                           getattr(subprocess, "CREATE_NO_WINDOW", 0)))
    print("ScratchPy updated in: %s" % folder)


def main():
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--update":
            wait_pid = 0
            restart = False
            args = iter(sys.argv[2:])
            for arg in args:
                if arg == "--wait-pid":
                    wait_pid = int(next(args))
                elif arg == "--restart":
                    restart = True
            update_existing(wait_pid, restart)
        else:
            install()
    except Exception as error:
        print("ScratchPy installation failed: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
