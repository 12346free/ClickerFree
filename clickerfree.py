import sys
import time
import json
import threading
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QDoubleSpinBox, QPushButton, 
                             QTextEdit, QGroupBox, QRadioButton, QLineEdit,
                             QListWidget, QListWidgetItem, QFileDialog, QSplitter,
                             QComboBox, QCheckBox) 
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from pynput.mouse import Button, Controller as MouseController, Listener as MouseListener
from pynput.keyboard import Key, Controller as KeyboardController, Listener as KeyboardListener
import pynput.keyboard

# --- QSS 样式 (Material Design 简洁风格) ---
MATERIAL_QSS = """
QMainWindow {
    background-color: #f0f0f0; 
}
QGroupBox {
    font-weight: bold;
    margin-top: 10px;
    border: 1px solid #ccc;
    border-radius: 5px;
    padding-top: 15px;
}
QPushButton {
    background-color: #0078D4; /* Accent Blue */
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #005A9E;
}
QLineEdit, QTextEdit, QListWidget, QDoubleSpinBox {
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 5px;
}
QCheckBox {
    padding: 2px;
}
#StartButton {
    background-color: #4CAF50; /* Green */
    font-size: 16px;
    padding: 12px;
}
#StartButton:hover {
    background-color: #45A049;
}
"""

# --- 核心工作线程 (执行连点/宏回放) ---
class ClickerThread(QThread):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = False
        self.mode = "simple_click" 
        self.interval = 0.1
        self.mouse_btn = Button.left
        self.key_content = ""
        self.auto_space = False 
        self.auto_enter = False 
        self.macro_actions = [] 
        
        self.mouse = MouseController()
        self.keyboard = KeyboardController()

    def stop(self):
        self.running = False
        
    def run(self):
        self.log_signal.emit(f"🚀 任务开始! 模式: {self.mode}")
        
        if self.mode == "macro_playback":
            self._playback_macro()
        else:
            self._simple_loop()

        self.log_signal.emit("⏸️ 任务已暂停.")

    def _simple_loop(self):
        while self.running:
            try:
                if self.mode == "simple_click":
                    self.mouse.click(self.mouse_btn)
                elif self.mode == "simple_type":
                    self.keyboard.type(self.key_content)
                    
                    if self.auto_space:
                        self.keyboard.press(pynput.keyboard.Key.space)
                        self.keyboard.release(pynput.keyboard.Key.space)
                        
                    if self.auto_enter:
                        self.keyboard.press(pynput.keyboard.Key.enter)
                        self.keyboard.release(pynput.keyboard.Key.enter)
                
                time.sleep(self.interval)
            except Exception as e:
                self.log_signal.emit(f"❌ 错误: {str(e)}")
                self.running = False

    def _playback_macro(self):
        if not self.macro_actions:
            self.log_signal.emit("❌ 宏脚本为空，无法回放.")
            return

        for action in self.macro_actions:
            if not self.running:
                break 
                
            time.sleep(action.get('delay', 0.0)) 
            
            action_type = action['type']
            
            if action_type == 'move':
                self.mouse.position = (action['x'], action['y'])
            elif action_type == 'click':
                btn = Button.left if action['button'] == 'Button.left' else Button.right
                self.mouse.click(btn)
            elif action_type == 'type':
                self.keyboard.type(action['content'])
            elif action_type == 'drag_start':
                self.mouse.press(Button.left)
            elif action_type == 'drag_end':
                self.mouse.release(Button.left)

# --- 宏录制线程 ---
class RecorderThread(QThread):
    log_signal = pyqtSignal(str)
    macro_completed_signal = pyqtSignal(list) 

    def __init__(self):
        super().__init__()
        self.actions = []
        self.is_recording = False
        self.last_time = None
        self.mouse_listener = None
        self.keyboard_listener = None

    def run(self):
        self.actions = []
        self.last_time = time.time()
        self.is_recording = True
        self.log_signal.emit("🔴 开始录制宏...")

        try:
            with MouseListener(on_click=self.on_mouse_click, on_move=self.on_mouse_move) as ml:
                with KeyboardListener(on_release=self.on_key_release) as kl:
                    self.mouse_listener = ml 
                    self.keyboard_listener = kl 
                    ml.join()
                    kl.join()
        except Exception:
            pass 

        self.log_signal.emit("⏹️ 录制结束。")
        self.macro_completed_signal.emit(self.actions)

    def stop_recording(self):
        self.is_recording = False
        if self.mouse_listener:
            try:
                self.mouse_listener.stop()
                self.keyboard_listener.stop()
            except Exception:
                pass 

    def _record_action(self, action_type, data):
        if not self.is_recording:
            return
            
        current_time = time.time()
        delay = current_time - self.last_time 
        self.last_time = current_time
        
        data['delay'] = round(delay, 4) 
        data['type'] = action_type
        self.actions.append(data)

    def on_mouse_click(self, x, y, button, pressed):
        if not self.is_recording: return
        
        btn_str = str(button)
        if pressed:
            self._record_action('drag_start' if btn_str == 'Button.left' else 'click', 
                                {'x': x, 'y': y, 'button': btn_str})
        else:
            if btn_str == 'Button.left':
                 self._record_action('drag_end', {'x': x, 'y': y, 'button': btn_str})

    def on_mouse_move(self, x, y):
        if self.is_recording:
            self._record_action('move', {'x': x, 'y': y})

    def on_key_release(self, key):
        if not self.is_recording: return
        try:
            char = key.char
        except AttributeError:
            char = str(key) 

        self._record_action('type', {'content': char})


# --- 主界面 UI ---
class ClickerFreeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClickerFree - 宏自动化 V0.4 (运行/停止: F8, 录制/停止: F10)")
        self.setGeometry(100, 100, 800, 600)
        self.setStyleSheet(MATERIAL_QSS) 

        self.worker = ClickerThread()
        self.worker.log_signal.connect(self.update_log)

        self.recorder = RecorderThread()
        self.recorder.log_signal.connect(self.update_log)
        self.recorder.macro_completed_signal.connect(self.add_recorded_macro) 

        self.current_macro_actions = []
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_splitter = QSplitter(Qt.Horizontal)
        
        # --- 宏词典管理 (左侧面板) ---
        macro_panel = QGroupBox("1. 宏词典管理")
        macro_layout = QVBoxLayout()
        self.macro_list = QListWidget()
        self.macro_list.itemClicked.connect(self.load_selected_macro)
        
        btn_layout = QHBoxLayout()
        self.btn_load_file = QPushButton("📂 从文件加载")
        self.btn_load_file.clicked.connect(self.open_macro_file)
        self.btn_save_file = QPushButton("💾 保存当前宏")
        self.btn_save_file.clicked.connect(self.save_macro_file)
        
        btn_layout.addWidget(self.btn_load_file)
        btn_layout.addWidget(self.btn_save_file)
        
        macro_layout.addWidget(self.macro_list)
        macro_layout.addLayout(btn_layout)
        macro_panel.setLayout(macro_layout)
        main_splitter.addWidget(macro_panel)

        # --- 设置与控制 (右侧面板) ---
        control_widget = QWidget()
        control_layout = QVBoxLayout()
        
        # 模式选择
        mode_group = QGroupBox("2. 模式选择")
        mode_layout = QVBoxLayout()
        self.radio_simple_click = QRadioButton("🖱️ 鼠标连点")
        self.radio_simple_type = QRadioButton("⌨️ 键盘输入")
        self.radio_macro = QRadioButton("⏯️ 宏脚本回放")
        self.radio_simple_click.setChecked(True)
        
        self.radio_simple_click.toggled.connect(self.update_settings_visibility)
        
        mode_layout.addWidget(self.radio_simple_click)
        mode_layout.addWidget(self.radio_simple_type)
        mode_layout.addWidget(self.radio_macro)
        mode_group.setLayout(mode_layout)
        control_layout.addWidget(mode_group)

        # 详细设置
        settings_group = QGroupBox("3. 参数设置")
        settings_layout = QVBoxLayout()
        
        # 间隔设置
        h_layout_time = QHBoxLayout()
        h_layout_time.addWidget(QLabel("执行间隔 (秒):"))
        self.spin_interval = QDoubleSpinBox()
        self.spin_interval.setRange(0.001, 60.0) 
        self.spin_interval.setValue(0.1)
        self.spin_interval.setSingleStep(0.01)
        h_layout_time.addWidget(self.spin_interval)
        settings_layout.addLayout(h_layout_time)

        # 鼠标/键盘 具体设置
        self.mouse_combo = QComboBox()
        self.mouse_combo.addItems(["Left", "Right"])

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("请输入要循环输入的文字/字符串 (如: Hello)")

        settings_layout.addWidget(self.mouse_combo)
        settings_layout.addWidget(self.key_input)
        
        # 自动空格/回车选项
        post_input_layout = QHBoxLayout()
        self.check_auto_space = QCheckBox("输入后自动加空格")
        self.check_auto_enter = QCheckBox("输入后自动回车 (Enter)")
        
        post_input_layout.addWidget(self.check_auto_space)
        post_input_layout.addWidget(self.check_auto_enter)
        settings_layout.addLayout(post_input_layout) 
        
        settings_group.setLayout(settings_layout)
        control_layout.addWidget(settings_group)
        
        # 录制控制
        record_group = QGroupBox("4. 宏录制 (热键: F10)")
        record_layout = QHBoxLayout()
        self.btn_record = QPushButton("🔴 录制")
        self.btn_record.clicked.connect(self.start_recording)
        self.btn_record.setStyleSheet("background-color: #E53935;")
        self.btn_stop_record = QPushButton("◼️ 停止")
        self.btn_stop_record.clicked.connect(self.stop_recording)
        self.btn_stop_record.setEnabled(False)
        
        record_layout.addWidget(self.btn_record)
        record_layout.addWidget(self.btn_stop_record)
        record_group.setLayout(record_layout)
        control_layout.addWidget(record_group)


        # 启动/停止按钮
        self.btn_start = QPushButton("▶️ 启动运行 (F8)")
        self.btn_start.setObjectName("StartButton")
        self.btn_start.clicked.connect(self.toggle_clicking)
        control_layout.addWidget(self.btn_start)

        # 日志区域
        log_group = QGroupBox("5. 日志输出")
        log_layout = QVBoxLayout()
        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        log_layout.addWidget(self.text_log)
        log_group.setLayout(log_layout)
        control_layout.addWidget(log_group)
        
        control_widget.setLayout(control_layout)
        main_splitter.addWidget(control_widget)

        central_widget.setLayout(QHBoxLayout(central_widget))
        central_widget.layout().addWidget(main_splitter)
        
        self.update_settings_visibility()
        
    def update_settings_visibility(self):
        is_simple_click = self.radio_simple_click.isChecked()
        is_simple_type = self.radio_simple_type.isChecked()
        is_macro = self.radio_macro.isChecked()

        self.mouse_combo.setVisible(is_simple_click)
        self.key_input.setVisible(is_simple_type)
        self.check_auto_space.setVisible(is_simple_type)
        self.check_auto_enter.setVisible(is_simple_type)
        self.spin_interval.setEnabled(not is_macro) 

    def start_recording(self):
        if not self.recorder.is_recording:
            self.btn_record.setEnabled(False)
            self.btn_stop_record.setEnabled(True)
            self.recorder = RecorderThread() 
            self.recorder.log_signal.connect(self.update_log)
            self.recorder.macro_completed_signal.connect(self.add_recorded_macro)
            self.recorder.start()
            self.update_log("INFO: 宏录制通过 F10 启动。")

    def stop_recording(self):
        if self.recorder.is_recording:
            self.recorder.stop_recording()
            self.btn_record.setEnabled(True)
            self.btn_stop_record.setEnabled(False)
            self.update_log("宏脚本已捕获，请在左侧将其命名保存。")
            self.update_log("INFO: 宏录制通过 F10 停止。")

    def add_recorded_macro(self, actions):
        """将录制好的宏添加到列表中（包含调试日志）"""
        self.update_log(f"DEBUG: 接收到宏脚本，共 {len(actions)} 个动作。正在添加到列表。") 
        
        self.current_macro_actions = actions
        
        macro_name = f"新录制宏 ({time.strftime('%H:%M:%S')})"
        item = QListWidgetItem(macro_name)
        item.setData(Qt.UserRole, actions)
        
        self.macro_list.addItem(item) 
        
        self.macro_list.setCurrentItem(item)
        self.radio_macro.setChecked(True) 
        
        self.update_log(f"DEBUG: 宏 '{macro_name}' 已成功添加到列表。")


    def open_macro_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "加载宏脚本", "", "JSON Files (*.json)")
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    if 'macro_name' in data and 'actions' in data:
                        item = QListWidgetItem(data['macro_name'])
                        item.setData(Qt.UserRole, data['actions'])
                        self.macro_list.addItem(item)
                        self.update_log(f"✅ 成功加载宏：{data['macro_name']}")
                    else:
                        self.update_log("❌ 文件格式不正确，不是有效的宏脚本。")
            except Exception as e:
                self.update_log(f"❌ 加载失败: {str(e)}")

    def save_macro_file(self):
        current_item = self.macro_list.currentItem()
        if not current_item:
            self.update_log("⚠️ 请先在左侧列表中选择或录制一个宏。")
            return

        actions = current_item.data(Qt.UserRole)
        macro_name = current_item.text()
        
        filename, _ = QFileDialog.getSaveFileName(self, "保存宏脚本", f"{macro_name}.json", "JSON Files (*.json)")
        if filename:
            data = {
                "macro_name": macro_name,
                "actions": actions
            }
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                self.update_log(f"✅ 宏脚本 '{macro_name}' 已保存到文件。")
            except Exception as e:
                self.update_log(f"❌ 保存失败: {str(e)}")

    def load_selected_macro(self, item):
        self.current_macro_actions = item.data(Qt.UserRole)
        self.radio_macro.setChecked(True)
        self.update_log(f"加载宏脚本 '{item.text()}' 成功。")

    def toggle_clicking(self):
        """切换 运行/停止 状态 (F8)"""
        if not self.worker.running:
            self._start_worker()
        else:
            self._stop_worker()
            
    def toggle_recording(self):
        """切换 录制/停止 状态 (F10) - 新增热键方法"""
        if not self.recorder.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def _start_worker(self):
        self.worker.interval = self.spin_interval.value()
        
        if self.radio_simple_click.isChecked():
            self.worker.mode = "simple_click"
            btn_str = self.mouse_combo.currentText()
            self.worker.mouse_btn = Button.left if btn_str == "Left" else Button.right
        elif self.radio_simple_type.isChecked():
            self.worker.mode = "simple_type"
            self.worker.key_content = self.key_input.text()
            self.worker.auto_space = self.check_auto_space.isChecked()
            self.worker.auto_enter = self.check_auto_enter.isChecked()
        elif self.radio_macro.isChecked():
            self.worker.mode = "macro_playback"
            if not self.current_macro_actions:
                self.update_log("❌ 宏脚本为空，请先录制或加载。")
                return
            self.worker.macro_actions = self.current_macro_actions
        
        self.worker.running = True
        self.worker.start()
        self.btn_start.setText("停止运行 (F8)")
        self.btn_start.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 12px;")
        self.btn_record.setEnabled(False)
        self.btn_load_file.setEnabled(False)

    def _stop_worker(self):
        self.worker.stop() 
        self.worker.wait() 
        self.btn_start.setText("▶️ 启动运行 (F8)")
        self.btn_start.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 12px;")
        self.btn_record.setEnabled(True)
        self.btn_load_file.setEnabled(True)

    def update_log(self, message):
        current_time = time.strftime("%H:%M:%S")
        self.text_log.append(f"[{current_time}] {message}")

    def setup_hotkey_listener(self):
        def on_release(key):
            try:
                # F8: 运行/停止
                if key == pynput.keyboard.Key.f8:
                    QTimer.singleShot(0, self.toggle_clicking)
                # F10: 录制/停止 (新增热键)
                elif key == pynput.keyboard.Key.f10:
                    QTimer.singleShot(0, self.toggle_recording) 
            except Exception:
                pass
        
        self.hotkey_listener = pynput.keyboard.Listener(on_release=on_release)
        self.hotkey_listener.start()

    def closeEvent(self, event):
        self.worker.stop()
        self.recorder.stop_recording()
        self.hotkey_listener.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ClickerFreeWindow()
    window.setup_hotkey_listener()
    window.show()
    sys.exit(app.exec_())