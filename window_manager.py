"""
window_manager.py - 窗口管理模块
封装 Win32 窗口操作，提供最小化、还原、置顶、枚举接口
"""

import win32gui
import win32con
import win32process
import win32api
import os
import logging

logger = logging.getLogger(__name__)

# 需要过滤的系统窗口类名
SYSTEM_WINDOW_CLASSES = {
    "Shell_TrayWnd",              # 任务栏
    "NotifyIconOverflowWindow",   # 通知区域溢出
    "Windows.UI.Core.CoreWindow", # 系统UI
    "DV2ControlHost",             # 桌面图标
    "Progman",                    # 桌面
    "SysListView32",              # 桌面列表
    "WorkerW",                    # 桌面壁纸窗口
    "WindowsShell",               # Windows Shell
    "Shell_DllWindow",            # Shell 窗口
    "Shell_SecondaryTrayWnd",     # 副任务栏
    "Shell_TrayWndStatic",        # 任务栏静态部分
}

# BossKey 自身的窗口类名
SELF_WINDOW_CLASSES = {
    "BossKey_HotkeyWindow",       # 热键消息窗口
    "QWidget",                    # Qt 窗口（设置窗口等）
}


class WindowManager:
    """窗口管理器，封装所有 Win32 窗口操作"""

    @staticmethod
    def _is_system_window(hwnd):
        """判断是否为系统窗口（任务栏、桌面等）"""
        class_name = win32gui.GetClassName(hwnd)
        if class_name in SYSTEM_WINDOW_CLASSES:
            return True
        # 过滤 BossKey 自身的窗口
        if class_name in SELF_WINDOW_CLASSES:
            return True
        title = win32gui.GetWindowText(hwnd) or ""
        if not title.strip():
            return True
        return False

    def get_all_visible_windows(self):
        """返回当前所有可见非最小化窗口的 hwnd 列表，过滤系统窗口"""
        hwnds = []

        def callback(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if win32gui.IsIconic(hwnd):
                return True
            if self._is_system_window(hwnd):
                return True
            hwnds.append(hwnd)
            return True

        win32gui.EnumWindows(callback, None)
        return hwnds

    def minimize_windows(self, hwnd_list):
        """最小化指定 hwnd 列表中的窗口"""
        for hwnd in hwnd_list:
            try:
                if win32gui.IsWindow(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            except Exception as e:
                logger.warning(f"最小化窗口 {hwnd} 失败: {e}")

    def restore_windows(self, hwnd_list):
        """还原指定 hwnd 列表中的窗口"""
        for hwnd in hwnd_list:
            try:
                if win32gui.IsWindow(hwnd):
                    if win32gui.IsIconic(hwnd):
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    else:
                        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            except Exception as e:
                logger.warning(f"还原窗口 {hwnd} 失败: {e}")

    def find_windows_by_process_name(self, name: str):
        """
        按进程名查找所有匹配窗口 hwnd 列表
        支持：
        - 完整路径: D:\\program\\WeLink\\WeLink.exe
        - 文件名: WeLink.exe
        - 无后缀: WeLink
        """
        # 标准化输入
        name_lower = name.lower().strip()

        # 如果是完整路径，提取文件名
        if '\\' in name_lower or '/' in name_lower:
            exe_name = os.path.basename(name_lower)
        else:
            exe_name = name_lower

        # 确保有 .exe 后缀
        if not exe_name.endswith(".exe"):
            exe_name += ".exe"

        matched = []

        def callback(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if self._is_system_window(hwnd):
                return True
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid == 0:
                    return True

                handle = win32api.OpenProcess(
                    win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                    False,
                    pid,
                )
                try:
                    # 获取进程的可执行文件名
                    exe_path = win32process.GetModuleFileNameEx(handle, 0)
                    process_exe = os.path.basename(exe_path).lower()

                    if process_exe == exe_name:
                        matched.append(hwnd)
                finally:
                    win32api.CloseHandle(handle)
            except Exception:
                pass
            return True

        win32gui.EnumWindows(callback, None)

        if matched:
            logger.debug(f"找到 {len(matched)} 个 {exe_name} 窗口")
        else:
            logger.debug(f"未找到 {exe_name} 窗口")

        return matched

    def bring_to_front(self, hwnd):
        """将窗口置顶并聚焦"""
        try:
            if not win32gui.IsWindow(hwnd):
                return
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            # 尝试多种方式置顶
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                # 如果 SetForegroundWindow 失败（Windows 限制），尝试其他方法
                try:
                    win32gui.BringWindowToTop(hwnd)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"置顶窗口 {hwnd} 失败: {e}")
