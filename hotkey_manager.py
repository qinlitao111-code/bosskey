"""
hotkey_manager.py - 全局快捷键监听模块（基于 Windows 原生 RegisterHotKey API）
使用系统级热键注册，比 keyboard 库更稳定可靠
"""

import ctypes
import ctypes.wintypes
import threading
import logging
import subprocess
import time

logger = logging.getLogger(__name__)


# ========== Qt 原生事件过滤器：接收 WM_HOTKEY 消息 ==========
try:
    from PyQt5.QtCore import QAbstractNativeEventFilter

    class _HotkeyNativeFilter(QAbstractNativeEventFilter):
        """在 Qt 主事件循环中拦截 WM_HOTKEY，避免独立线程方案的多线程窗口归属问题"""

        def __init__(self, manager):
            super().__init__()
            self._manager = manager

        def nativeEventFilter(self, eventType, message):
            if eventType != b'windows_generic_MSG':
                return False, 0
            try:
                import ctypes
                class _MSG(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", ctypes.c_void_p),
                        ("message", ctypes.c_uint),
                        ("wParam", ctypes.c_void_p),
                        ("lParam", ctypes.c_void_p),
                        ("time", ctypes.c_uint),
                        ("pt_x", ctypes.c_long),
                        ("pt_y", ctypes.c_long),
                    ]
                msg = _MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    hotkey_id = int(msg.wParam)
                    logger.info(f"收到 WM_HOTKEY 消息，hotkey_id={hotkey_id}")
                    handler = self._manager._handlers.get(hotkey_id)
                    if handler:
                        try:
                            handler()
                        except Exception as e:
                            logger.error(f"热键处理异常: {e}", exc_info=True)
            except Exception as e:
                logger.debug(f"nativeEventFilter 异常: {e}")
            return False, 0
except ImportError:
    logger.warning("PyQt5 不可用，原生事件过滤器无法安装")

# Windows 消息常量
WM_HOTKEY = 0x0312
WM_DESTROY = 0x0002
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
HWND_MESSAGE = ctypes.c_void_p(-3).value  # 消息专用窗口的父窗口句柄

# 虚拟键码映射
VK_MAP = {
    'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
    'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
    'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F,
    'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
    'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59,
    'z': 0x5A, '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33,
    '4': 0x34, '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38,
    '9': 0x39, 'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
    'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77, 'f9': 0x78,
    'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B, 'space': 0x20,
    'esc': 0x1B, 'escape': 0x1B, 'tab': 0x09, 'enter': 0x0D,
    'backspace': 0x08, 'delete': 0x2E, 'insert': 0x2D,
    'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22,
    'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28,
    '-': 0xBD, '=': 0xBB, '[': 0xDB, ']': 0xDD, '\\': 0xDC,
    ';': 0xBA, "'": 0xDE, ',': 0xBC, '.': 0xBE, '/': 0xBF,
    '`': 0xC0,
}


# 定义 WNDCLASS 结构体（某些 Python 版本不在 ctypes.wintypes 中）
class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.wintypes.UINT),
        ("lpfnWndProc", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.wintypes.HWND,
                                            ctypes.c_uint, ctypes.wintypes.WPARAM,
                                            ctypes.wintypes.LPARAM)),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.wintypes.HINSTANCE),
        ("hIcon", ctypes.wintypes.HICON),
        ("hCursor", ctypes.wintypes.HCURSOR),
        ("hbrBackground", ctypes.wintypes.HBRUSH),
        ("lpszMenuName", ctypes.wintypes.LPCWSTR),
        ("lpszClassName", ctypes.wintypes.LPCWSTR),
    ]


class HotkeyManager:
    """全局快捷键管理器，基于 Windows RegisterHotKey API"""

    def __init__(self, window_manager):
        self._wm = window_manager
        self._states = {}  # hotkey_id -> state dict
        self._handlers = {}  # hotkey_id -> handler function
        self._hotkey_map = {}  # hotkey_string -> hotkey_id
        self._reverse_map = {}  # hotkey_id -> hotkey_string
        self._lock = threading.Lock()
        self._next_id = 1
        self._hwnd = None
        self._msg_thread = None
        self._running = False
        self._wnd_proc_func = None  # 保持引用防止被回收

    def _parse_hotkey(self, hotkey_str):
        """解析快捷键字符串，返回 (modifiers, vk)"""
        parts = hotkey_str.lower().strip().split('+')
        modifiers = 0
        vk = None

        for part in parts:
            part = part.strip()
            if part == 'ctrl' or part == 'control':
                modifiers |= MOD_CONTROL
            elif part == 'alt':
                modifiers |= MOD_ALT
            elif part == 'shift':
                modifiers |= MOD_SHIFT
            elif part == 'win' or part == 'meta':
                modifiers |= MOD_WIN
            elif part in VK_MAP:
                vk = VK_MAP[part]
            else:
                logger.warning(f"未知的按键: {part}")
                return None, None

        if vk is None:
            logger.warning(f"快捷键缺少普通按键: {hotkey_str}")
            return None, None

        return modifiers, vk

    def _create_message_window(self):
        """创建一个隐藏的消息窗口用于接收热键消息"""
        # 保持回调函数引用
        self._wnd_proc_func = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.wintypes.HWND, ctypes.c_uint,
            ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
        )(self._wnd_proc)

        wc = WNDCLASS()
        wc.lpfnWndProc = self._wnd_proc_func
        wc.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
        wc.lpszClassName = "BossKey_HotkeyWindow"

        atom = ctypes.windll.user32.RegisterClassW(ctypes.byref(wc))
        if not atom:
            logger.error("注册窗口类失败")
            return None

        # 显式声明 argtypes，避免 64 位系统上 c_void_p 默认转换导致 OverflowError
        ctypes.windll.user32.CreateWindowExW.argtypes = [
            ctypes.c_ulong,      # dwExStyle
            ctypes.c_wchar_p,    # lpClassName
            ctypes.c_wchar_p,    # lpWindowName
            ctypes.c_ulong,      # dwStyle
            ctypes.c_int,        # X
            ctypes.c_int,        # Y
            ctypes.c_int,        # nWidth
            ctypes.c_int,        # nHeight
            ctypes.c_void_p,     # hWndParent
            ctypes.c_void_p,     # hMenu
            ctypes.c_void_p,     # hInstance
            ctypes.c_void_p,     # lpParam
        ]
        ctypes.windll.user32.CreateWindowExW.restype = ctypes.c_void_p

        hwnd = ctypes.windll.user32.CreateWindowExW(
            0,
            "BossKey_HotkeyWindow",
            "BossKey_Hotkey",
            0, 0, 0, 0, 0,
            ctypes.c_void_p(-3).value,  # HWND_MESSAGE
            ctypes.c_void_p(0).value,
            ctypes.c_void_p(wc.hInstance).value,
            ctypes.c_void_p(0).value,
        )

        if not hwnd:
            logger.error("创建消息窗口失败")
            return None

        return hwnd

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        """窗口消息处理函数（WM_HOTKEY 由 nativeEventFilter 统一处理，这里不再重复）"""
        if msg == WM_HOTKEY:
            # WM_HOTKEY 已由 _HotkeyNativeFilter.nativeEventFilter 处理，
            # 这里直接返回 0，避免 handler 被调用两次导致状态错乱
            return 0
        if msg == WM_DESTROY:
            ctypes.windll.user32.PostQuitMessage(0)
            return 0
        # 显式声明 argtypes，避免 64 位上 lparam 溢出
        ctypes.windll.user32.DefWindowProcW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p
        ]
        ctypes.windll.user32.DefWindowProcW.restype = ctypes.c_void_p
        return int(ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam) or 0)

    def _message_loop(self):
        """空的消息循环占位（保留向后兼容，不再使用独立线程）"""
        pass

    def install_native_filter(self, qapp):
        """安装 Qt 原生事件过滤器，在 Qt 事件循环中处理 WM_HOTKEY"""
        self._qapp = qapp
        if not hasattr(self, '_native_filter') or self._native_filter is None:
            self._native_filter = _HotkeyNativeFilter(self)
            qapp.installNativeEventFilter(self._native_filter)
            logger.info("Qt 原生事件过滤器已安装")

    def register_all(self, rules, retry=3):
        """根据规则列表注册所有快捷键"""
        # 先注销所有
        self.unregister_all()

        # 在主线程创建消息窗口（Qt 主线程，兼容 64 位）
        if self._hwnd is None:
            self._hwnd = self._create_message_window()
            if self._hwnd is None:
                logger.error("无法创建消息窗口，热键功能不可用")
                return
            logger.info("热键消息窗口已创建（主线程）")

        # 注册每个快捷键
        for rule in rules:
            hotkey = rule.get("hotkey", "").strip()
            if not hotkey:
                continue

            modifiers, vk = self._parse_hotkey(hotkey)
            if modifiers is None or vk is None:
                logger.warning(f"跳过无效快捷键: {hotkey}")
                continue

            hotkey_id = self._next_id
            self._next_id += 1

            # 带重试的注册
            success = False
            logger.debug(f"准备注册热键: hwnd={self._hwnd}, id={hotkey_id}, mod={modifiers | MOD_NOREPEAT}, vk={vk}")
            for attempt in range(retry):
                # 显式声明 argtypes，避免 64 位上 wparam 溢出
                ctypes.windll.user32.RegisterHotKey.argtypes = [
                    ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint
                ]
                ctypes.windll.user32.RegisterHotKey.restype = ctypes.c_bool

                # 确保 hwnd 是有效的 c_void_p
                hwnd_arg = ctypes.c_void_p(int(self._hwnd)) if self._hwnd else ctypes.c_void_p(0)
                logger.debug(f"  尝试 {attempt+1}: hwnd={hwnd_arg.value}")

                if ctypes.windll.user32.RegisterHotKey(hwnd_arg, hotkey_id, modifiers | MOD_NOREPEAT, vk):
                    success = True
                    logger.info(f"热键 {hotkey} 注册成功!")
                    break
                else:
                    error = ctypes.windll.kernel32.GetLastError()
                    # 1409=ERROR_HOTKEY_ALREADY_REGISTERED, 87=ERROR_INVALID_PARAMETER
                    error_msg = f"错误码 {error}"
                    if error == 1409:
                        error_msg = "热键已被注册(自身)"
                    elif error == 87:
                        error_msg = "参数无效"
                    elif error == 1442:
                        error_msg = "窗口句柄无效"
                    logger.warning(f"注册热键 {hotkey} 失败 (尝试 {attempt + 1}/{retry}): {error_msg}")
                    if attempt < retry - 1:
                        time.sleep(0.5)

            if success:
                self._states[hotkey_id] = {
                    "active": False,
                    "minimized_hwnds": [],
                    "apps": rule.get("apps", []),
                }

                def make_handler(hid, h=hotkey):
                    def handler():
                        # 关键修复：把耗时操作放到 worker 线程，
                        # 避免在 nativeEventFilter 中阻塞 Qt 主事件循环
                        threading.Thread(
                            target=self._do_hotkey_action,
                            args=(hid, h),
                            daemon=True,
                        ).start()
                    return handler

                self._handlers[hotkey_id] = make_handler(hotkey_id)
                self._hotkey_map[hotkey] = hotkey_id
                self._reverse_map[hotkey_id] = hotkey
                logger.info(f"已注册热键: {hotkey} -> {rule.get('apps')}")
            else:
                logger.error(f"注册热键 {hotkey} 最终失败")

        logger.info(f"热键注册完成，共 {len(self._handlers)} 个")

    def _do_hotkey_action(self, hid, hotkey):
        """在工作线程中执行热键动作，避免阻塞 Qt 主事件循环导致 UI 卡死"""
        with self._lock:
            state = self._states.get(hid)
            if state is None:
                logger.warning(f"handler: state 为 None, hotkey_id={hid}")
                return
            logger.info(f"handler 触发: hotkey={hotkey}, state.active={state['active']}, 已最小化窗口数={len(state.get('minimized_hwnds', []))}")
            try:
                if not state["active"]:
                    self._activate(hotkey, state)
                else:
                    self._deactivate(hotkey, state)
                logger.info(f"handler 完成: state.active={state['active']}")
            except Exception as e:
                logger.error(f"快捷键处理异常: {e}", exc_info=True)

    def unregister_all(self):
        """注销所有已注册的热键"""
        for hotkey_id in list(self._handlers.keys()):
            try:
                ctypes.windll.user32.UnregisterHotKey(self._hwnd, hotkey_id)
                hotkey_str = self._reverse_map.get(hotkey_id, str(hotkey_id))
                logger.debug(f"已注销热键: {hotkey_str}")
            except Exception as e:
                logger.debug(f"注销热键时出错: {e}")

        self._handlers.clear()
        self._states.clear()
        self._hotkey_map.clear()
        self._reverse_map.clear()

    def is_registered(self):
        """检查是否有热键已注册"""
        return len(self._handlers) > 0

    def is_healthy(self):
        """
        检查热键系统是否真正可用。
        不仅检查是否有已注册的 handler，还检查消息窗口是否仍然有效。
        这是修复"运行一段时间后热键失效"的关键：
        如果消息窗口被系统销毁（休眠唤醒、会话切换等），
        热键消息无法送达，但 is_registered() 仍返回 True。
        """
        if len(self._handlers) == 0:
            return False
        if self._hwnd is None:
            return False
        return bool(ctypes.windll.user32.IsWindow(self._hwnd))

    def _recreate_message_infrastructure(self):
        """
        完全重建消息窗口和消息循环线程。
        用于当检测到消息窗口失效时的恢复操作。
        """
        # 1. 停止旧的消息循环并销毁旧窗口
        self._running = False
        if self._hwnd:
            try:
                ctypes.windll.user32.DestroyWindow(self._hwnd)
            except Exception:
                pass
            self._hwnd = None
        # 等待旧线程退出（最多等待 2 秒）
        if self._msg_thread and self._msg_thread.is_alive():
            self._msg_thread.join(timeout=2.0)

        # 2. 创建新消息窗口
        self._hwnd = self._create_message_window()
        if self._hwnd is None:
            logger.error("重建消息窗口失败，热键功能不可用")
            return False

        # 3. 启动新消息循环线程
        self._running = True
        self._msg_thread = threading.Thread(target=self._message_loop, daemon=True)
        self._msg_thread.start()
        logger.info("消息窗口和消息循环已重建")
        return True

    def _launch_app(self, app_name):
        """启动目标应用"""
        try:
            # CREATE_NO_WINDOW 避免启动时弹出黑窗口
            subprocess.Popen(
                f'start "" "{app_name}"',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
            logger.info(f"已启动应用: {app_name}")
            return True
        except Exception as e:
            logger.warning(f"启动 {app_name} 失败: {e}")
            return False

    def _activate(self, hotkey, state):
        """激活快捷键：最小化其他窗口，调出/启动目标应用"""
        logger.info(f"触发快捷键: {hotkey} -> 切换模式")

        apps = state.get("apps", [])

        # 1. 收集目标应用的所有窗口句柄
        app_hwnds = set()
        for app in apps:
            for hwnd in self._wm.find_windows_by_process_name(app):
                app_hwnds.add(hwnd)

        # 2. 获取所有可见窗口，排除目标应用窗口
        all_visible = self._wm.get_all_visible_windows()
        to_minimize = [hwnd for hwnd in all_visible if hwnd not in app_hwnds]

        # 3. 最小化非目标窗口
        self._wm.minimize_windows(to_minimize)
        state["minimized_hwnds"] = to_minimize

        # 4. 调出或启动目标应用
        for app in apps:
            app_windows = self._wm.find_windows_by_process_name(app)
            if app_windows:
                self._wm.bring_to_front(app_windows[0])
                logger.info(f"已置顶: {app}")
            else:
                logger.info(f"{app} 未运行，正在启动...")
                self._launch_app(app)

        state["active"] = True
        logger.info(f"切换完成: 最小化 {len(to_minimize)} 个窗口, 目标应用: {apps}")

    def _deactivate(self, hotkey, state):
        """取消激活：还原之前最小化的窗口"""
        logger.info(f"触发快捷键: {hotkey} -> 还原模式")

        self._wm.restore_windows(state["minimized_hwnds"])
        state["minimized_hwnds"] = []
        state["active"] = False

        logger.info("还原完成")

    def cleanup(self):
        """清理资源"""
        self._running = False
        if self._hwnd:
            try:
                ctypes.windll.user32.DestroyWindow(self._hwnd)
            except Exception:
                pass
            self._hwnd = None
        self.unregister_all()
        logger.info("热键管理器已清理")
