#!/usr/bin/env python3
"""Install ScratchPy from the official GitHub repository on Windows.

The installer downloads the program, builds a standalone ScratchPy.exe with PyInstaller
and creates a desktop shortcut to it. If the .exe cannot be built (no network for pip,
antivirus, ...), the shortcut starts scratchpy.pyw with Python instead.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
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
EXE_NAME = "ScratchPy.exe"
HIDDEN_IMPORTS = ("random", "math", "time", "string", "datetime", "collections", "itertools",
                  "statistics", "turtle", "PIL.ImageTk", "PIL._tkinter_finder")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


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


def python_path():
    """python.exe (with a console), used to run pip and PyInstaller."""
    current = Path(sys.executable)
    candidates = [current.with_name("python.exe") if current.name.lower() == "pythonw.exe" else current,
                  Path(sys.base_prefix) / "python.exe"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    located = shutil.which("python.exe")
    if located:
        return Path(located)
    raise RuntimeError("Python 3 (python.exe) is required to build ScratchPy.exe.")


def run_quiet(command, cwd=None):
    result = subprocess.run(command, capture_output=True, text=True, cwd=cwd,
                            creationflags=NO_WINDOW, check=False)
    if result.returncode:
        tail = "\n".join((result.stderr or result.stdout or "").strip().splitlines()[-12:])
        raise RuntimeError("%s failed:\n%s" % (" ".join(str(c) for c in command[:4]), tail))
    return result


def build_exe(files, folder):
    """Build ScratchPy.exe with PyInstaller. Return the path of the new .exe (staged beside the
    installation, not yet in place), or raise RuntimeError."""
    python = python_path()
    print("Installing the build tools (PyInstaller, Pillow)...")
    run_quiet([str(python), "-m", "pip", "install", "--upgrade", "pyinstaller", "pillow"])
    work = Path(tempfile.mkdtemp(prefix="scratchpy-build-"))
    try:
        src = work / "src"
        src.mkdir()
        script, icon = src / "scratchpy.pyw", src / "scratchpy_logo.ico"
        script.write_bytes(files["scratchpy.pyw"])
        icon.write_bytes(files["scratchpy_logo.ico"])
        command = [str(python), "-m", "PyInstaller", "--noconsole", "--onefile", "--clean", "--noconfirm",
                   "--name", "ScratchPy", "--icon", str(icon),
                   "--add-data", "%s%s." % (icon, os.pathsep),
                   "--add-data", "%s%s." % (script, os.pathsep),
                   "--distpath", str(work / "dist"), "--workpath", str(work / "build"),
                   "--specpath", str(work)]
        for module in HIDDEN_IMPORTS:
            command += ["--hidden-import", module]
        command.append(str(script))
        print("Building ScratchPy.exe (this can take a few minutes)...")
        run_quiet(command, cwd=str(work))
        built = work / "dist" / EXE_NAME
        if not built.is_file() or built.stat().st_size < 1024 * 1024:
            raise RuntimeError("PyInstaller did not produce a valid %s." % EXE_NAME)
        fd, temp_path = tempfile.mkstemp(prefix=".ScratchPy.", suffix=".exe.new", dir=folder)
        os.close(fd)
        shutil.copyfile(built, temp_path)
        return Path(temp_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def replace_with_retry(source, target, attempts=40):
    """os.replace that waits while Windows still locks the old .exe."""
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.5)


def create_shortcut(folder, target, arguments, icon_path):
    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise RuntimeError("Windows PowerShell was not found; cannot create the shortcut.")
    command = r"""
$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
if ([string]::IsNullOrWhiteSpace($desktop)) { throw 'The Desktop folder was not found.' }
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $desktop 'ScratchPy.lnk'))
$shortcut.TargetPath = $env:SCRATCHPY_TARGET
$shortcut.Arguments = $env:SCRATCHPY_ARGS
$shortcut.WorkingDirectory = $env:SCRATCHPY_FOLDER
$shortcut.IconLocation = $env:SCRATCHPY_ICON
$shortcut.Description = 'ScratchPy - program in Python with blocks'
$shortcut.Save()
"""
    env = os.environ.copy()
    env.update({
        "SCRATCHPY_TARGET": str(target),
        "SCRATCHPY_ARGS": arguments,
        "SCRATCHPY_FOLDER": str(folder),
        "SCRATCHPY_ICON": str(icon_path),
    })
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, env=env, creationflags=NO_WINDOW, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError("Could not create the desktop shortcut: %s" % detail)


def install_folder():
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("The Windows LOCALAPPDATA folder could not be found.")
    return Path(local_app_data) / "ScratchPy"


def try_build(files, folder):
    """Return the staged .exe, or None (with a message) when it cannot be built."""
    try:
        return build_exe(files, folder)
    except Exception as error:
        print("Could not build ScratchPy.exe: %s" % error, file=sys.stderr)
        print("ScratchPy will start with Python (scratchpy.pyw) instead.", file=sys.stderr)
        return None


def remember_python(folder):
    """The app uses this file to run this installer again when it updates itself."""
    try:
        (folder / "python.txt").write_text(str(python_path()), encoding="utf-8")
    except Exception:
        pass


def install():
    if sys.platform != "win32":
        raise RuntimeError("This installer is for Windows only.")
    folder = install_folder()
    folder.mkdir(parents=True, exist_ok=True)

    print("Downloading ScratchPy from GitHub...")
    files = {name: download(url) for name, url in FILES.items()}
    validate_downloads(files)

    stage_files(folder, files)
    remember_python(folder)
    icon_path = folder / "scratchpy_logo.ico"
    script_path = folder / "scratchpy.pyw"

    staged_exe = try_build(files, folder)
    if staged_exe is not None:
        exe_path = folder / EXE_NAME
        replace_with_retry(staged_exe, exe_path)
        create_shortcut(folder, exe_path, "", icon_path)
        print("ScratchPy.exe built in: %s" % folder)
    else:
        create_shortcut(folder, pythonw_path(), '"%s"' % script_path, icon_path)
    print("ScratchPy installed in: %s" % folder)
    print("Desktop shortcut created: ScratchPy")


def update_existing(wait_pid=0, restart=False):
    if sys.platform != "win32":
        raise RuntimeError("This updater is for Windows only.")
    folder = install_folder()
    if not (folder / "scratchpy.pyw").is_file():
        raise RuntimeError("ScratchPy is not installed in %s." % folder)

    print("Downloading the ScratchPy update...")
    files = {name: download(url) for name, url in FILES.items()}
    validate_downloads(files)
    staged_exe = try_build(files, folder)                 # Built while ScratchPy is still open.
    wait_for_process(wait_pid)
    stage_files(folder, files)
    remember_python(folder)

    script_path = folder / "scratchpy.pyw"
    exe_path = folder / EXE_NAME
    if staged_exe is not None:
        replace_with_retry(staged_exe, exe_path)
        create_shortcut(folder, exe_path, "", folder / "scratchpy_logo.ico")
    if restart:
        command = ([str(exe_path)] if staged_exe is not None
                   else [str(pythonw_path()), str(script_path)])
        subprocess.Popen(
            command, cwd=str(folder),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=(getattr(subprocess, "DETACHED_PROCESS", 0) | NO_WINDOW))
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
