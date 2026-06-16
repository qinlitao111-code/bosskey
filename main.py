"""
main.py - 程序入口
初始化所有模块，启动托盘常驻，处理程序退出清理
"""

import sys
import os
import logging
import traceback

LOG_PATH = None


def setup_logging():
    """配置日志：输出到文件和控制台"""
    global LOG_PATH
    if getattr(sys, "frozen", False):
        log_dir = os.path.dirname(sys.executable)
    else:
        log_dir = os.path.dirname(os.path.abspath(__file__))

    LOG_PATH = os.path.join(log_dir, "BossKey.log")

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("BossKey")


def main():
    logger = setup_logging()
    logger.info("=== BossKey 启动 ===")

    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QTimer, QAbstractNativeEventFilter

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("BossKey")
    app.setApplicationDisplayName("BossKey 老板键")
    logger.info("QApplication 初始化完成")

    # 初始化模块
    from window_manager import WindowManager
    from hotkey_manager import HotkeyManager

    wm = WindowManager()
    hm = HotkeyManager(wm)
    hm.install_native_filter(app)  # 安装 Qt 原生事件过滤器接收 WM_HOTKEY
    logger.info("模块初始化完成")

    # 加载规则并注册快捷键
    import rule_manager as rm_module
    rules = rm_module.load_rules()
    logger.info(f"已加载 {len(rules)} 条规则")

    if rules:
        hm.register_all(rules)
    else:
        logger.warning("无规则，快捷键未注册")

    # ========== 休眠唤醒自动恢复快捷键 ==========
    def refresh_hotkeys():
        """刷新快捷键注册，用于休眠唤醒后恢复"""
        try:
            current_rules = rm_module.load_rules()
            if current_rules:
                if not hm.is_healthy():
                    logger.info("检测到热键系统异常，正在恢复...")
                    hm._recreate_message_infrastructure()
                    hm.register_all(current_rules)
                    logger.info(f"快捷键已恢复，共 {len(current_rules)} 条规则")
                else:
                    logger.debug("热键系统正常，无需刷新")
            else:
                logger.debug("无规则需要刷新")
        except Exception as e:
            logger.warning(f"刷新快捷键失败: {e}")

    # 方案1：Windows 电源广播消息
    try:
        import ctypes
        from ctypes.wintypes import DWORD, WPARAM, LPARAM, HANDLE, UINT

        class _MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", HANDLE), ("message", UINT), ("wParam", WPARAM),
                ("lParam", LPARAM), ("time", DWORD), ("pt", ctypes.wintypes.POINT),
            ]
        WM_POWERBROADCAST = 0x0218
        PBT_APMRESUMEAUTOMATIC = 0x0012

        class PowerEventFilter(QAbstractNativeEventFilter):
            def nativeEventFilter(self, eventType, message):
                if eventType == b'windows_generic_MSG':
                    try:
                        msg = _MSG.from_address(int(message))
                        if msg.message == WM_POWERBROADCAST and msg.wParam == PBT_APMRESUMEAUTOMATIC:
                            logger.info("检测到系统从休眠中恢复，将在 3 秒后检查快捷键")
                            # 延迟刷新，确保系统完全恢复
                            QTimer.singleShot(3000, refresh_hotkeys)
                    except Exception:
                        pass
                return False, 0

        app.installNativeEventFilter(PowerEventFilter())
        logger.info("电源事件监听已启用")
    except Exception as e:
        logger.warning(f"电源事件监听初始化失败: {e}")

    # 方案2：低频定时检查（每 5 分钟检查一次，仅在快捷键丢失时恢复）
    refresh_timer = QTimer()
    refresh_timer.timeout.connect(refresh_hotkeys)
    refresh_timer.start(300000)  # 5 分钟
    logger.info("定时检查已启用（每 5 分钟）")

    # ========== 开机自启：首次运行自动开启 ==========
    from ui.tray import get_autostart_status, set_autostart
    try:
        if not get_autostart_status():
            set_autostart(True)
            logger.info("首次运行，已自动开启开机自启")
        else:
            logger.info("开机自启已处于开启状态")
    except Exception as e:
        logger.warning(f"设置开机自启失败: {e}")

    # ========== 设置窗口（延迟创建） ==========
    settings_window = None

    def open_settings():
        nonlocal settings_window
        if settings_window is None:
            from ui.settings_window import SettingsWindow
            settings_window = SettingsWindow(rule_manager=rm_module, hotkey_manager=hm)
        settings_window.show()
        settings_window.raise_()
        settings_window.activateWindow()

    # 初始化托盘
    from ui.tray import TrayIcon
    tray = TrayIcon()
    tray.open_settings_signal.connect(open_settings)
    tray.show()
    logger.info("托盘图标已显示")

    # 退出时清理
    def cleanup():
        refresh_timer.stop()
        hm.cleanup()
        logger.info("BossKey 已退出")

    app.aboutToQuit.connect(cleanup)

    logger.info(f"启动完成，日志文件: {LOG_PATH}")
    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_msg = traceback.format_exc()
        try:
            with open("BossKey_crash.log", "w", encoding="utf-8") as f:
                f.write(error_msg)
        except Exception:
            pass
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox
            qapp = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "BossKey 启动失败",
                f"程序启动时发生错误，请查看 BossKey_crash.log\n\n{str(e)[:200]}")
        except Exception:
            pass
        print("CRASH:", error_msg)
        sys.exit(1)
