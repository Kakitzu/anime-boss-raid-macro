import sys
import threading
import time
import json
import os
import cv2
import numpy as np
import pydirectinput
import pyautogui
import keyboard
import win32api
import win32gui
import win32con
import math
import random
import mss

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QPushButton, QGridLayout,
                               QFrame)
from PySide6.QtCore import (QObject, Signal, Slot, QRunnable, QThreadPool, Qt, QTimer,
                           QPoint)
from PySide6.QtGui import (QFont, QColor, QKeySequence)

if sys.platform == "win32":
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

class WorkerSignals(QObject):
    log_updated = Signal(str, str)
    finished = Signal()


class MacroWorker(QRunnable):
    def __init__(self, backend_instance, selected_packs):
        super().__init__()
        self.backend = backend_instance
        self.selected_packs = selected_packs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        self.backend.macro_loop(self.signals, self.selected_packs)
        self.signals.finished.emit()

class PackButton(QPushButton):
    def __init__(self, text, color, parent=None):
        super().__init__(text, parent)
        self.pack_color = color
        self.is_selected = False
        self.setFixedSize(110, 40)

    def toggle_selection(self):
        self.is_selected = not self.is_selected
        self.update_style()

    def update_style(self):
        if self.is_selected:
            bg_color = self.pack_color
            border_color = self.adjust_brightness(self.pack_color, 40)
        else:
            bg_color = "#38384a"
            border_color = "#4a4a5f"
            
        hover_color = self.adjust_brightness(bg_color, 20)
        pressed_color = self.adjust_brightness(bg_color, -10)

        self.setStyleSheet(f"""
            PackButton {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 6px;
                color: white;
                font-weight: bold;
                font-size: 10px;
                text-transform: uppercase;
            }}
            PackButton:hover {{
                background-color: {hover_color};
                border: 1px solid {self.adjust_brightness(border_color, 20)};
            }}
            PackButton:pressed {{
                background-color: {pressed_color};
            }}
        """)

    def adjust_brightness(self, color, amount):
        try:
            if not color.startswith('#'):
                return color
            color_hex = color.lstrip('#')
            if len(color_hex) == 3:
                color_hex = "".join([c*2 for c in color_hex])
            if len(color_hex) != 6:
                return color
            rgb = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))
            rgb = tuple(max(0, min(255, c + amount)) for c in rgb)
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        except (ValueError, TypeError):
            return color

class HotkeyCaptureButton(QPushButton):
    hotkey_captured = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_capturing = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_capturing = True
            self.setText("Press any key...")
            self.setFocus()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if self.is_capturing:
            key_name = QKeySequence(event.key()).toString().lower()
            self.is_capturing = False
            self.hotkey_captured.emit(key_name)
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self.is_capturing = False
        super().focusOutEvent(event)

class RobloxMacroBackend:
    def __init__(self):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image_dir = os.path.join(self.script_dir, "images")
        self.image_files = {
            "SummonScreen": "SummonScreen.png",
            "NoStock": "NoStock.png",
            "XButton": "XButton.png",
            "SummonButton": "SummonButton.png",
            "SellButton": "SellButton.png",
            "DragonRealmPack": "DragonRealmPack.png",
            "SorcererRealmPack": "SorcererRealmPack.png",
            "PirateRealmPack": "PirateRealmPack.png",
            "DemonRealmPack": "DemonRealmPack.png",
            "HunterRealmPack": "HunterRealmPack.png",
            "ShinobiRealmPack": "ShinobiRealmPack.png",
        }
        self.running = False
        self.sct = None
        self.initial_search = True
        self.LastPackClicked = 0
        self.image_templates = {}
        self.load_image_templates()
        self.regions = {
            "PackFrame": (168, 242, 472, 654),
            "PurchaseLocation": (821, 800, 220, 48),
            "SummonScreen": (692, 218, 380, 79),
            "XButton": (1445, 181, 107, 127),
            "SummonButton": (360, 79, 537, 110),
            "SellButton": (972, 78, 537, 110),
            "SellInvClick": (1031, 517),
        }
        self.DefaultLocation = (799, 824)

    def load_image_templates(self):
        for key, filename in self.image_files.items():
            image_path = os.path.join(self.image_dir, filename)
            if os.path.exists(image_path):
                self.image_templates[key] = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)

    def human_like_movement(self, start_x, start_y, end_x, end_y):
        distance = math.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)
        total_duration = max(0.1, min(0.4, distance / 2000))
        steps = max(12, int(distance / 50))
        step_duration = total_duration / steps
        p0 = np.array([start_x, start_y])
        p3 = np.array([end_x, end_y])
        control_x_variance = max(10, int(distance * 0.15))
        control_y_variance = max(10, int(distance * 0.15))
        p1 = (p0 + (p3 - p0) * 0.3+ np.array(
                [
                    random.randint(-control_x_variance, control_x_variance),
                    random.randint(-control_y_variance, control_y_variance),
                ]
            )
        )
        p2 = (p3 - (p3 - p0) * 0.3 + np.array(
                [
                    random.randint(-control_x_variance, control_x_variance),
                    random.randint(-control_y_variance, control_y_variance),
                ]
            )
        )
        for i in range(steps + 1):
            if not self.running:
                break
            t = i / steps
            eased_t = 1 - (1 - t) ** 2
            point = ((1 - eased_t) ** 3 * p0
                + 3 * (1 - eased_t) ** 2 * eased_t * p1
                + 3 * (1 - eased_t) * eased_t**2 * p2
                + eased_t**3 * p3
            )
            pydirectinput.moveTo(int(point[0]), int(point[1]), duration=step_duration)

        if self.running:
            pydirectinput.moveTo(end_x, end_y, duration=step_duration)

    def human_like_key_press(self, key):
        pydirectinput.keyDown(key)
        time.sleep(random.uniform(0.06, 0.11))
        pydirectinput.keyUp(key)

    def move_cursor_to_default(self):
        pydirectinput.moveTo(self.DefaultLocation[0], self.DefaultLocation[1])
        self.responsive_sleep(0.1, None)

    def scroll_mouse_wheel(self, x, y, direction="down", clicks=3):
        current_pos = pydirectinput.position()
        self.human_like_movement(current_pos[0], current_pos[1], x, y)
        for _ in range(clicks):
            if not self.running:
                break

            if direction == "down":
                win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, x, y, -120, 0)
            else:
                win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, x, y, 120, 0)
            self.responsive_sleep(0.1, None)

    def scroll_in_pack_frame(self, direction="down", clicks=3):
        pack_frame_x = (
            self.regions["PackFrame"][0] + self.regions["PackFrame"][2] // 2
        )
        pack_frame_y = (
            self.regions["PackFrame"][1] + self.regions["PackFrame"][3] // 2
        )
        self.scroll_mouse_wheel(pack_frame_x, pack_frame_y, direction, clicks)
        self.responsive_sleep(0.5, None)

    def find_image_in_region(self, signals, image_filename, region, confidence=0.7):
        try:
            image_key = os.path.splitext(image_filename)[0]
            template = self.image_templates.get(image_key)

            if template is None:
                if signals: signals.log_updated.emit(f"Template '{image_key}' not in cache!", "error")
                return None

            monitor_region = {"top": region[1], "left": region[0], "width": region[2], "height": region[3]}
            sct_img = self.sct.grab(monitor_region)
            screenshot_cv = cv2.cvtColor(np.array(sct_img), cv2.COLOR_BGRA2BGR)
            
            use_mask = len(template.shape) > 2 and template.shape[2] == 4
            template_bgr = template[:,:,:3] if use_mask else template
            mask = template[:,:,3] if use_mask else None
            
            result = cv2.matchTemplate(screenshot_cv, template_bgr, cv2.TM_CCOEFF_NORMED, mask=mask)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val >= confidence:
                h, w = template.shape[:2]
                return (region[0] + max_loc[0] + w // 2, region[1] + max_loc[1] + h // 2)

        except Exception as e:
            if signals:
                signals.log_updated.emit(f"💥 Image search error for {image_filename}: {e}", "error")
        return None

    def search_and_click_pack(self, signals, pack_name):
        pack_image_key = pack_name.replace(" ", "")
        if pack_image_key not in self.image_files:
            return False            

        pack_location = self.find_image_in_region(
            signals,
            self.image_files[pack_image_key],
            self.regions["PackFrame"],
        )

        if pack_location:
            current_pos = pydirectinput.position()
            self.human_like_movement(
                current_pos[0], current_pos[1],
                pack_location[0], pack_location[1],
            )
            pydirectinput.click()
            return True
        return False

    def is_pack_out_of_stock(self, signals):
        return self.find_image_in_region(
            signals,
            self.image_files["NoStock"],
            self.regions["PurchaseLocation"],
        ) is not None

    def purchase_pack(self, signals, pack_name):
        purchase_x = self.regions["PurchaseLocation"][0] + self.regions["PurchaseLocation"][2] // 2
        purchase_y = self.regions["PurchaseLocation"][1] + self.regions["PurchaseLocation"][3] // 2
        
        current_pos = pydirectinput.position()
        self.human_like_movement(current_pos[0], current_pos[1], purchase_x, purchase_y)
        
        signals.log_updated.emit(f"Buying {pack_name.replace(' Realm Pack', '')}...", "action")
        while self.running:
            if self.is_pack_out_of_stock(signals):
                break
            
            pydirectinput.click()
            self.responsive_sleep(0.1, signals)

    def is_summon_screen_open(self, signals):
        return self.find_image_in_region(
            signals,
            self.image_files["SummonScreen"],
            self.regions["SummonScreen"],
        ) is not None

    def close_shop_with_image(self, signals):
        x_button_loc = self.find_image_in_region(
            signals,
            self.image_files["XButton"],
            self.regions["XButton"],
            confidence=0.7,
        )

        if x_button_loc:
            signals.log_updated.emit("Closing shop...", "action")
            current_pos = pydirectinput.position()
            self.human_like_movement(
                current_pos[0], current_pos[1],
                x_button_loc[0], x_button_loc[1],
            )
            pydirectinput.click()
            return True
        return False

    def logic_open_shop(self, signals):
        signals.log_updated.emit("Opening Shop...", "action")
        max_attempts, i = 3, 0
        while i < max_attempts and self.running:
            if self.is_summon_screen_open(signals):
                return True

            summon_btn = self.find_image_in_region(
                signals,
                self.image_files["SummonButton"],
                self.regions["SummonButton"],
            )

            if summon_btn:
                self.human_like_movement(
                    pydirectinput.position()[0], pydirectinput.position()[1],
                    summon_btn[0], summon_btn[1],
                )
                pydirectinput.click()
                self.responsive_sleep(0.5, signals)
                self.human_like_key_press("e")
                self.responsive_sleep(1.5, signals)
            else:
                signals.log_updated.emit(f"Cannot find Summon Button (attempt {i+1})", "error")
                i += 1
                self.responsive_sleep(1, signals)

        return self.is_summon_screen_open(signals)

    def logic_sell_items(self, signals):
        signals.log_updated.emit("Selling items...", "action")
        sell_btn = self.find_image_in_region(
            signals, self.image_files["SellButton"], self.regions["SellButton"]
        )

        if not sell_btn:
            signals.log_updated.emit("Cannot find Sell Button.", "error")
            return False

        self.human_like_movement(
            pydirectinput.position()[0], pydirectinput.position()[1],
            sell_btn[0], sell_btn[1],
        )
        pydirectinput.click()
        self.responsive_sleep(0.5, signals)
        self.human_like_key_press("e")
        self.responsive_sleep(1.0, signals)
        signals.log_updated.emit("Confirming sale...", "action")
        base_pos = self.regions["SellInvClick"]

        for i in range(3):
            if not self.running: break
            jitter_x = base_pos[0] + random.randint(-3, 3)
            jitter_y = base_pos[1] + random.randint(-3, 3)
            self.human_like_movement(
                pydirectinput.position()[0], pydirectinput.position()[1],
                jitter_x, jitter_y,
            )
            pydirectinput.click()
            self.responsive_sleep(0.1, signals)
        signals.log_updated.emit("Items sold.", "success")
        return True

    def wait_for_restock(self, signals):
        if not self.is_summon_screen_open(signals):
            if not self.logic_open_shop(signals):
                signals.log_updated.emit("Failed to open shop for restock check.", "error")
                self.responsive_sleep(5, signals)
                return

        pack_order = list(MainWindow.PACK_COLORS.keys())
        last_pack_name = pack_order[self.LastPackClicked]
        self.search_and_click_pack(signals, last_pack_name)
        self.responsive_sleep(1, signals)

        while self.running and self.is_pack_out_of_stock(signals):
            signals.log_updated.emit(f"Watching {last_pack_name}...", "wait")
            self.responsive_sleep(5, signals)

        if self.running:
            signals.log_updated.emit("SHOP RESTOCKED!", "success")
            self.responsive_sleep(1, signals)

    def responsive_sleep(self, duration_secs, signals):
        if duration_secs is None: return
        steps = int(duration_secs / 0.05)
        for _ in range(steps):
            if not self.running:
                return
            time.sleep(0.05)
        time.sleep(duration_secs % 0.05)

    def macro_loop(self, signals, selected_packs):
        self.sct = mss.mss()

        if not selected_packs:
            signals.log_updated.emit("No packs selected! Stopping.", "error")
            return

        pack_order = list(MainWindow.PACK_FULL_NAMES.values())
        cycle = 1

        while self.running:
            try:
                signals.log_updated.emit(f"Cycle #{cycle} - Purchase Phase", "system")
                if not self.logic_open_shop(signals):
                    signals.log_updated.emit("Shop failed to open. Retrying cycle.", "error")
                    self.responsive_sleep(5, signals)
                    continue

                temp_pack_order = {name: i for i, name in enumerate(pack_order)}
                packs_to_buy = sorted(selected_packs, key=lambda x: temp_pack_order.get(x, 99))
                start_index = 0
                if not self.initial_search:
                    for i, pack in enumerate(packs_to_buy):
                        if temp_pack_order.get(pack, 99) >= self.LastPackClicked:
                            start_index = i
                            break
                reordered_packs = packs_to_buy[start_index:] + packs_to_buy[:start_index]

                for pack_name in reordered_packs:
                    if not self.running: break
                    signals.log_updated.emit(f"Searching for {pack_name.replace(' Realm Pack', '')}...", "action")
                    pack_found, scroll_attempts, max_scrolls = False, 0, 10

                    if self.initial_search:
                        if not self.search_and_click_pack(signals, pack_name):
                            signals.log_updated.emit("Initial search failed. Resetting to top...", "info")
                            for _ in range(2): self.scroll_in_pack_frame("up", 3)
                            self.responsive_sleep(1, signals)

                    while not pack_found and scroll_attempts < max_scrolls and self.running:
                        pack_found = self.search_and_click_pack(signals, pack_name)
                        if not pack_found:
                            current_pack_index = pack_order.index(pack_name)
                            scroll_dir = "down" if current_pack_index >= self.LastPackClicked else "up"
                            signals.log_updated.emit(f"Scrolling {scroll_dir}...", "action")
                            self.scroll_in_pack_frame(scroll_dir)
                            scroll_attempts += 1
                            self.responsive_sleep(1, signals)

                    if not pack_found:
                        signals.log_updated.emit(f"{pack_name.replace(' Realm Pack', '')} not found.", "error")
                        continue

                    self.initial_search = False
                    self.LastPackClicked = pack_order.index(pack_name)
                    self.responsive_sleep(1, signals)

                    if self.is_pack_out_of_stock(signals):
                        signals.log_updated.emit(
                            f"{pack_name.replace(' Realm Pack', '')} is out of stock.",
                            "info",
                        )
                        continue

                    self.purchase_pack(signals, pack_name)

                    signals.log_updated.emit(
                        f"{pack_name.replace(' Realm Pack', '')} fully purchased.",
                        "success",
                    )

                    self.responsive_sleep(1, signals)

                if self.running:
                    signals.log_updated.emit("Purchase phase complete.", "success")
                    close_attempts, max_close_attempts = 0, 5
                    while self.running and self.is_summon_screen_open(signals) and close_attempts < max_close_attempts:
                        if self.close_shop_with_image(signals):
                            self.responsive_sleep(1.5, signals)
                            break
                        close_attempts += 1
                        self.responsive_sleep(1, signals)

                    if self.running:
                        if not self.logic_sell_items(signals):
                            signals.log_updated.emit("Failed to sell items.", "error")

                if self.running:
                    self.wait_for_restock(signals)
                cycle += 1
            except Exception as e:
                signals.log_updated.emit(f"An unexpected error occurred: {str(e)}", "error")
                self.responsive_sleep(5, signals)
        signals.log_updated.emit("Macro stopped by user.", "system")


class MainWindow(QMainWindow):
    PACK_COLORS = {
        'Dragon': "#d9534f", 'Sorcerer': '#6100ca', 'Pirate': '#f0ad4e',
        'Demon': '#00e53d', 'Hunter': '#db2100', 'Shinobi': '#bcbcbc'
    }
    PACK_FULL_NAMES = {
        'Dragon': 'Dragon Realm Pack', 'Sorcerer': 'Sorcerer Realm Pack', 'Pirate': 'Pirate Realm Pack',
        'Demon': 'Demon Realm Pack', 'Hunter': 'Hunter Realm Pack', 'Shinobi': 'Shinobi Realm Pack'
    }

    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.threadpool = QThreadPool()
        self.pack_vars = {name: False for name in self.PACK_FULL_NAMES.values()}
        self.current_start_hotkey = "f1"
        self.current_stop_hotkey = "f2"
        self.is_capturing_hotkey = None
        self.pack_buttons = {}
        self.dragPos = None
        self.start_hotkey_ref = None
        self.stop_hotkey_ref = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground) 

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(1, 1, 1, 1)
        self.setCentralWidget(self.container)

        self.initUI()
        self.apply_styles()
        QTimer.singleShot(0, self.deferred_init)

    def deferred_init(self):
        """Loads settings and sets up hotkeys after the UI is shown."""
        self.load_settings()
        self.setup_hotkeys()
        self.update_pack_buttons()

    def initUI(self):
        content_widget = QWidget()
        content_widget.setObjectName("ContentWidget")
        self.container_layout.addWidget(content_widget)

        main_layout = QVBoxLayout(content_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 0, 15, 15) 

        self.initTitleBar(main_layout)

        status_frame = QFrame()
        status_frame.setObjectName("StatusFrame")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(10, 5, 10, 5)
        
        self.log_icon = QLabel("🟢")
        self.log_icon.setFont(QFont("Segoe UI Emoji", 12))
        self.log_text = QLabel("Ready to summon")
        self.log_text.setObjectName("StatusText")
        
        status_layout.addWidget(self.log_icon)
        status_layout.addWidget(self.log_text, 1)
        main_layout.addWidget(status_frame)

        pack_frame = QFrame()
        pack_frame.setObjectName("SectionFrame")
        pack_layout = QVBoxLayout(pack_frame)
        pack_grid = QGridLayout()
        pack_grid.setSpacing(8)
        
        for i, (short_name, color) in enumerate(self.PACK_COLORS.items()):
            row, col = i // 2, i % 2
            full_name = self.PACK_FULL_NAMES[short_name]
            pack_btn = PackButton(short_name, color)
            pack_btn.clicked.connect(lambda c=False, p=full_name: self.toggle_pack(p))
            pack_grid.addWidget(pack_btn, row, col)
            self.pack_buttons[full_name] = pack_btn
            
        pack_layout.addLayout(pack_grid)
        main_layout.addWidget(pack_frame)

        hotkey_frame = QFrame()
        hotkey_frame.setObjectName("SectionFrame")
        hotkey_layout = QGridLayout(hotkey_frame)
        hotkey_layout.setSpacing(10)
        hotkey_layout.setColumnStretch(1, 1)

        hotkey_layout.addWidget(QLabel("Start Hotkey:"), 0, 0)
        self.start_hotkey_btn = HotkeyCaptureButton()
        self.start_hotkey_btn.setObjectName("HotkeySetBtn")
        self.start_hotkey_btn.hotkey_captured.connect(lambda key: self._finalize_hotkey_capture('start', key))
        hotkey_layout.addWidget(self.start_hotkey_btn, 0, 1)
        
        hotkey_layout.addWidget(QLabel("Stop Hotkey:"), 1, 0)
        self.stop_hotkey_btn = HotkeyCaptureButton()
        self.stop_hotkey_btn.setObjectName("HotkeySetBtn")
        self.stop_hotkey_btn.hotkey_captured.connect(lambda key: self._finalize_hotkey_capture('stop', key))
        hotkey_layout.addWidget(self.stop_hotkey_btn, 1, 1)
        
        main_layout.addWidget(hotkey_frame)

        self.control_btn = QPushButton()
        self.control_btn.setFixedHeight(40)
        self.control_btn.clicked.connect(self.toggle_macro)
        main_layout.addWidget(self.control_btn)

        self.update_control_button_style()

    def initTitleBar(self, parent_layout):
        self.title_bar = QWidget()
        self.title_bar.setObjectName("TitleBar")
        self.title_bar.setFixedHeight(35)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(10, 0, 5, 0)
        title_layout.setSpacing(5)

        title_label = QLabel("⚔️ Anime Boss Raid Macro")
        title_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        title_label.setStyleSheet("color: #a9a9d9;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        btn_size = 28
        
        self.minimize_btn = QPushButton("\uE921")
        self.minimize_btn.setObjectName("TitleBarButton")
        self.minimize_btn.setFixedSize(btn_size, btn_size)
        self.minimize_btn.clicked.connect(self.showMinimized)

        self.close_btn = QPushButton("\uE8BB")
        self.close_btn.setObjectName("TitleBarButton")
        self.close_btn.setFixedSize(btn_size, btn_size)
        self.close_btn.clicked.connect(self.close)

        title_layout.addWidget(self.minimize_btn)
        title_layout.addWidget(self.close_btn)

        parent_layout.addWidget(self.title_bar)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.title_bar.underMouse():
            self.dragPos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragPos and event.buttons() == Qt.LeftButton:
            self.move(self.pos() + event.globalPosition().toPoint() - self.dragPos)
            self.dragPos = event.globalPosition().toPoint()
            event.accept()

    def mouseReleaseEvent(self, event):
        self.dragPos = None
        event.accept()

    def apply_styles(self):
        self.setStyleSheet("""
            #ContentWidget {
                background-color: #1e1e2d;
                border: 1px solid #3c3c5a;
                border-radius: 8px;
            }
            #TitleBar { background-color: transparent; }
            #TitleBarButton {
                background-color: transparent;
                border: none; border-radius: 4px;
                color: #e0e0e0; 
                font-size: 10px;
                font-family: 'Segoe Fluent Icons';
            }
            #TitleBarButton:hover { background-color: #4a4a5f; }
            #TitleBarButton:pressed { background-color: #5a5a6f; }
            #SectionFrame, #StatusFrame {
                background-color: #2a2a3f;
                border: 1px solid #3c3c5a;
                border-radius: 8px; padding: 10px;
            }
            #StatusText, QLabel { font-size: 11px; font-weight: 500; }
            #HotkeySetBtn {
                background-color: #4a4a5f; border: 1px solid #666;
                border-radius: 6px; padding: 8px;
                font-size: 10px; font-weight: bold;
            }
            #HotkeySetBtn:hover { background-color: #5a5a6f; }
            #StartButton {
                background-color: #28a745; border: 1px solid #3cbf5d; color: white;
            }
            #StartButton:hover { background-color: #2ebf4f; }
            #StopButton {
                background-color: #dc3545; border: 1px solid #e45a66; color: white;
            }
            #StopButton:hover { background-color: #e44a59; }
            #StartButton, #StopButton {
                font-size: 11px; font-weight: bold;
                border-radius: 8px; padding: 10px;
                text-transform: uppercase;
            }
        """)

    def toggle_macro(self):
        if self.backend.running:
            self.stop_macro()
        else:
            self.start_macro()

    def update_control_button_style(self):
        if self.backend.running:
            self.control_btn.setObjectName("StopButton")
            self.control_btn.setText("STOP")
        else:
            self.control_btn.setObjectName("StartButton")
            self.control_btn.setText("START")
        self.style().polish(self.control_btn)

    @Slot(str, str)
    def update_log(self, message, tag):
        icons = {'success': '🟢', 'error': '🔴', 'action': '🔍', 'info': '📦', 'wait': '👀', 'system': '⚙️'}
        self.log_icon.setText(icons.get(tag, '⚙️'))
        self.log_text.setText(message)

    def toggle_pack(self, pack_name):
        self.pack_vars[pack_name] = not self.pack_vars[pack_name]
        self.pack_buttons[pack_name].toggle_selection()

    def update_pack_buttons(self):
        for full_name, button in self.pack_buttons.items():
            if self.pack_vars.get(full_name, False):
                button.is_selected = True
            button.update_style()

    def start_macro(self):
        if self.backend.running: return
        self.backend.running = True
        self.update_log("Macro started.", 'system')
        
        selected_packs = [name for name, selected in self.pack_vars.items() if selected]
        worker = MacroWorker(self.backend, selected_packs)
        worker.signals.log_updated.connect(self.update_log)
        worker.signals.finished.connect(self.on_macro_finished)
        self.threadpool.start(worker)
        self.update_control_button_style()

    def stop_macro(self):
        if self.backend.running:
            self.backend.running = False
            self.update_log("Stopping macro...", 'system')
    
    @Slot()
    def on_macro_finished(self):
        self.backend.running = False
        self.update_control_button_style()

    def _finalize_hotkey_capture(self, target, hotkey):
        if target == 'start' and hotkey == self.current_stop_hotkey:
            self.update_log("Hotkey is already in use for Stop.", 'error')
        elif target == 'stop' and hotkey == self.current_start_hotkey:
            self.update_log("Hotkey is already in use for Start.", 'error')
        else:
            if target == 'start':
                self.current_start_hotkey = hotkey
            else:
                self.current_stop_hotkey = hotkey
            self.update_log(f"{target.capitalize()} hotkey set to '{hotkey.upper()}'", 'success')
        
        self.setup_hotkeys()

    def setup_hotkeys(self):
        if self.start_hotkey_ref:
            try: keyboard.remove_hotkey(self.start_hotkey_ref)
            except (KeyError, ValueError): pass
        if self.stop_hotkey_ref:
            try: keyboard.remove_hotkey(self.stop_hotkey_ref)
            except (KeyError, ValueError): pass

        self.start_hotkey_ref = keyboard.add_hotkey(self.current_start_hotkey, self.start_macro)
        self.stop_hotkey_ref = keyboard.add_hotkey(self.current_stop_hotkey, self.stop_macro)
        
        self.start_hotkey_btn.setText(self.current_start_hotkey.upper())
        self.stop_hotkey_btn.setText(self.current_stop_hotkey.upper())

    def save_settings(self):
        settings = {
            'pack_vars': self.pack_vars,
            'hotkeys': {'start': self.current_start_hotkey, 'stop': self.current_stop_hotkey},
        }
        try:
            with open(os.path.join(self.backend.script_dir, 'config.json'), 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e: print(f"Failed to save settings: {e}")

    def load_settings(self):
        try:
            path = os.path.join(self.backend.script_dir, 'config.json')
            if os.path.exists(path):
                with open(path, 'r') as f:
                    settings = json.load(f)
                    self.pack_vars = settings.get('pack_vars', self.pack_vars)
                    hotkeys = settings.get('hotkeys', {})
                    self.current_start_hotkey = hotkeys.get('start', 'f1')
                    self.current_stop_hotkey = hotkeys.get('stop', 'f2')
        except Exception as e: print(f"Failed to load settings: {e}")

    def closeEvent(self, event):
        self.save_settings()
        self.backend.running = False
        
        if self.start_hotkey_ref:
            try: keyboard.remove_hotkey(self.start_hotkey_ref)
            except (KeyError, ValueError): pass
        if self.stop_hotkey_ref:
            try: keyboard.remove_hotkey(self.stop_hotkey_ref)
            except (KeyError, ValueError): pass
            
        event.accept()

def main():
    app = QApplication(sys.argv)
    backend = RobloxMacroBackend()
    window = MainWindow(backend)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()