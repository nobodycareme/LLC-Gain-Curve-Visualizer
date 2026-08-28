# -*- coding: utf-8 -*-
"""验证冻结 EXE 的启动 + 主窗口渲染 + resize 重绘路径（纯 ctypes，无第三方依赖）。

用法：python scripts/verify_exe.py <exe_path> [wait_seconds]
返回 0 表示通过；非 0 表示失败。
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


def find_main_window(pid):
    """返回给定 PID 的可见顶层窗口句柄（或 None）。

    PyInstaller 6.x onefile 是双进程模型：父 bootloader 进程 + 子应用进程，
    窗口属于子进程，因此按标题匹配（标题唯一，避免误匹配其他窗口）。
    """
    found = []

    @EnumWindowsProc
    def cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            title = get_window_text(hwnd)
            if "谐振变换器交互式多增益曲线" in title:
                found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def get_window_text(hwnd):
    n = user32.GetWindowTextLengthW(hwnd) + 1
    buf = ctypes.create_unicode_buffer(n)
    user32.GetWindowTextW(hwnd, buf, n)
    return buf.value


def get_window_rect(hwnd):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def main():
    exe = sys.argv[1]
    wait = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
    proc = subprocess.Popen([exe])
    try:
        deadline = time.time() + wait
        hwnd = None
        while time.time() < deadline:
            if proc.poll() is not None:
                print(f"FAIL: EXE exited early with code {proc.returncode}")
                return 1
            hwnd = find_main_window(proc.pid)
            if hwnd:
                break
            time.sleep(0.3)
        if not hwnd:
            print("FAIL: main window not found within timeout")
            return 1
        title = get_window_text(hwnd)
        print(f"OK: main window found: '{title}'")
        # 触发 resize → 强制 QPainter 重绘路径
        r = get_window_rect(hwnd)
        w, h = r.right - r.left, r.bottom - r.top
        user32.MoveWindow(hwnd, r.left, r.top, w + 40, h + 30, True)
        time.sleep(1.5)
        if proc.poll() is not None:
            print(f"FAIL: EXE crashed after resize, code {proc.returncode}")
            return 1
        print("OK: survived resize/repaint")
        return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
