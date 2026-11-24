"""PySide6 application shell. All system input is dispatched on the UI thread."""
import os
import sys
from datetime import datetime
from pathlib import Path
from time import monotonic

from AppKit import NSWorkspace
from PySide6.QtCore import QCameraPermission, QEasingCurve, QPropertyAnimation, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QTabWidget,
    QTextBrowser, QVBoxLayout, QWidget,
)

from .camera import Camera, MODEL
from .engine import ACTIONS, DEFAULTS, MODES, Command, Engine
from .gestures import POSES
from .macos import EmergencyHotkey, MacInput, camera_permission, parse_shortcut
from .safety import Safety
from .widgets import ModeSurface, Preview

ROOT = Path(__file__).resolve().parents[1]
MODE_HELP = {
    "Pointer": "Point to move. Tap an index pinch to click, or hold to drag.",
    "Media": "Index pinch toggles playback. Thumb up or down adjusts the volume.",
    "Shortcuts": "Index pinch runs your shortcut. Middle pinch switches apps.",
    "Keyboard": "Point to a key and pinch to select it. Compose text in AirControl.",
    "Drawing": "Point to position the pen. Pinch and move to draw a stroke.",
    "Presentation": "Index pinch advances. Middle pinch goes back.",
}

STYLE = """
QWidget { background: #0e1522; color: #e8f2fc; font-family: "Helvetica Neue"; font-size: 13px; }
QFrame#card { background: #121d2e; border: 1px solid #24344b; border-radius: 12px; }
QLabel { background: transparent; }
QLabel#title { font-size: 29px; font-weight: 700; }
QLabel#subtitle { color: #91a4be; }
QLabel#section { color: #6be5f3; font-weight: 700; }
QLabel#number { font-size: 20px; font-weight: 650; }
QLabel#state { color: #68e4f0; font-weight: 700; }
QLabel#state[armed="true"] { color: #ffca87; }
QPushButton, QComboBox, QLineEdit, QDoubleSpinBox { background: #18263a; border: 1px solid #304460;
  border-radius: 7px; padding: 7px 11px; min-height: 19px; }
QPushButton:hover, QComboBox:hover { border-color: #55cfe0; }
QPushButton:disabled { color: #61728a; }
QPushButton#primary { background: #62e0ed; color: #08202d; font-weight: 700; border-color: #62e0ed; }
QPushButton#stop { color: #ffc1b2; border-color: #79505a; }
QTabWidget::pane { border: 1px solid #24344b; border-radius: 9px; top: -1px; }
QTabBar::tab { background: #111a28; padding: 9px 16px; color: #9eafc5; }
QTabBar::tab:selected { background: #192b40; color: #6be5f3; }
QListWidget, QPlainTextEdit, QTextBrowser { background: #0a111d; border: 1px solid #24344b;
  border-radius: 8px; padding: 7px; }
QComboBox QAbstractItemView { background: #172436; selection-background-color: #274965; }
QToolTip { color: #e8f2fc; background: #18263a; }
"""


def label(value, name=""):
    widget = QLabel(value)
    widget.setObjectName(name)
    return widget


def button(value, callback, style=""):
    widget = QPushButton(value)
    widget.setObjectName(style)
    widget.clicked.connect(callback)
    return widget


class Window(QMainWindow):
    camera_authorized = Signal(int, bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AirControl AI — Touchless Computer Controller")
        self.setMinimumSize(800, 660)
        self.resize(1080, 770)
        self.settings = QSettings("AirControlAI", "AirControlAI")
        self.engine = Engine()
        self.native = MacInput()
        self.safety = Safety(self.native)
        self.worker = None
        self.camera_request = 0
        self.pending_camera = False
        self.last_frame = None
        self.last_event = ""
        self.stop_generation = 0
        self.build()
        self.hotkey = EmergencyHotkey(lambda: self.stop("Emergency stop"))
        self.safety.hotkey_ready = self.hotkey.ready
        self.arm_button.setEnabled(False)
        if not self.hotkey.ready:
            self.log("Emergency shortcut is unavailable. Live control is locked.")
        self.local_hotkey = QShortcut(QKeySequence("Ctrl+Alt+Meta+Esc"), self)
        self.local_hotkey.activated.connect(lambda: self.stop("Emergency stop"))
        self.camera_authorized.connect(self.permission_result, Qt.ConnectionType.QueuedConnection)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(25)

    def build(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        headings = QVBoxLayout()
        headings.setSpacing(2)
        headings.addWidget(label("AirControl AI", "title"))
        headings.addWidget(label("Touchless Computer Controller", "subtitle"))
        header.addLayout(headings, 1)
        self.camera_button = button("Start camera", self.toggle_camera)
        self.arm_button = button("Enable live control", self.toggle_arm, "primary")
        header.addWidget(self.camera_button)
        header.addWidget(self.arm_button)
        header.addWidget(button("Stop", lambda: self.stop("Stopped by user"), "stop"))
        layout.addLayout(header)

        strip = QFrame()
        strip.setObjectName("card")
        stats = QHBoxLayout(strip)
        self.metrics = {}
        for title, value in (("OUTPUT", "Simulation"), ("TRACKING FPS", "—"),
                             ("HAND CONFIDENCE", "—"), ("CURRENT GESTURE", "—")):
            col = QVBoxLayout()
            col.addWidget(label(title, "section"))
            widget = label(value, "state" if title == "OUTPUT" else "number")
            self.metrics[title] = widget
            col.addWidget(widget)
            stats.addLayout(col, 1)
        layout.addWidget(strip)

        controls = QHBoxLayout()
        controls.addWidget(label("Control mode", "section"))
        self.mode = QComboBox()
        self.mode.addItems(MODES)
        controls.addWidget(self.mode)
        self.hint = label(MODE_HELP["Pointer"], "subtitle")
        self.hint.setWordWrap(True)
        self.hint_opacity = QGraphicsOpacityEffect(self.hint)
        self.hint_opacity.setOpacity(1.0)
        self.hint.setGraphicsEffect(self.hint_opacity)
        self.fade = QPropertyAnimation(self.hint_opacity, b"opacity", self)
        self.fade.setStartValue(0.35)
        self.fade.setEndValue(1.0)
        self.fade.setDuration(170)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        controls.addWidget(self.hint, 1)
        layout.addLayout(controls)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        workspace = QWidget()
        work = QVBoxLayout(workspace)
        self.preview = Preview()
        work.addWidget(self.preview, 3)
        self.surface = ModeSurface()
        self.surface.hide()
        work.addWidget(self.surface, 3)
        self.compose = QPlainTextEdit()
        self.compose.setMaximumHeight(72)
        self.compose.setPlaceholderText("Text selected with the virtual keyboard appears here.")
        self.compose.hide()
        work.addWidget(self.compose)
        self.clear = button("Clear canvas", self.clear_canvas)
        self.clear.hide()
        work.addWidget(self.clear, 0, Qt.AlignmentFlag.AlignRight)
        self.tabs.addTab(workspace, "Workspace")
        self.build_settings()
        tutorial = QTextBrowser()
        tutorial.setMarkdown((ROOT / "docs" / "GESTURES.md").read_text(encoding="utf-8"))
        self.tabs.addTab(tutorial, "Gesture guide")
        self.history = QListWidget()
        self.tabs.addTab(self.history, "Activity")
        self.status = label("Start the camera to practice gestures in simulation.", "subtitle")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addWidget(label("Emergency stop   ⌃ ⌥ ⌘ Esc", "subtitle"))
        self.mode.currentTextChanged.connect(self.change_mode)

    def build_settings(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(22, 18, 22, 18)
        self.hand = QComboBox()
        self.hand.addItems(("Auto", "Left", "Right"))
        side = self.settings.value("hand", "Auto", str)
        self.hand.setCurrentText(side if side in ("Auto", "Left", "Right") else "Auto")
        self.engine.side = self.hand.currentText()
        form.addRow("Control hand", self.hand)
        self.hand.currentTextChanged.connect(self.change_hand)
        for title, attr, minimum, maximum, step in (
            ("Pointer sensitivity", "sensitivity", 0.5, 2.5, 0.05),
            ("Movement smoothing", "smoothing", 0.0, 0.95, 0.05),
            ("Action cooldown (seconds)", "cooldown", 0.20, 2.0, 0.05),
        ):
            spin = QDoubleSpinBox()
            spin.setRange(minimum, maximum)
            spin.setSingleStep(step)
            spin.setValue(self.settings.value(attr, getattr(self.engine, attr), float))
            setattr(self.engine, attr, spin.value())
            spin.valueChanged.connect(lambda value, key=attr: self.tune(key, value))
            form.addRow(title, spin)
        self.shortcut = QLineEdit(self.settings.value("shortcut", "Cmd+Space", str))
        try:
            self.native.shortcut = parse_shortcut(self.shortcut.text())
        except ValueError:
            self.shortcut.setText("Cmd+Space")
        form.addRow("Keyboard shortcut", self.shortcut)
        self.shortcut.editingFinished.connect(self.save_shortcut)
        self.external_typing = QCheckBox("Type into the focused application when live control is enabled")
        self.external_typing.stateChanged.connect(lambda _: self.stop("Keyboard output changed"))
        form.addRow("Virtual keyboard", self.external_typing)
        form.addRow(button("Configure gesture bindings", self.edit_binding),
                    button("Recalibrate tracking", self.recalibrate))
        for mode in MODES:
            for pose in POSES:
                value = self.settings.value(f"bindings/{mode}/{pose}", "", str)
                if value in ACTIONS:
                    self.engine.bindings[mode, pose] = value
                if value == "Shortcut":
                    shortcut = self.settings.value(f"bindingShortcuts/{mode}/{pose}", "", str)
                    if shortcut:
                        try:
                            parse_shortcut(shortcut)
                        except ValueError:
                            continue
                        self.engine.shortcuts[mode, pose] = shortcut
        self.tabs.addTab(page, "Settings")

    def log(self, message):
        self.history.insertItem(0, f"{datetime.now():%H:%M:%S}    {message}")
        if self.history.count() > 250:
            self.history.takeItem(250)

    def set_status(self, message):
        if message != self.last_event:
            self.status.setTextFormat(Qt.TextFormat.PlainText)
            self.status.setText(message)
            self.last_event = message

    def tune(self, key, value):
        setattr(self.engine, key, value)
        self.settings.setValue(key, value)

    def save_shortcut(self):
        try:
            self.native.shortcut = parse_shortcut(self.shortcut.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Shortcut", str(exc))
            self.shortcut.setText(self.settings.value("shortcut", "Cmd+Space", str))
        else:
            self.stop("Shortcut updated")
            self.settings.setValue("shortcut", self.shortcut.text())

    def change_hand(self, side):
        self.engine.side = side
        self.settings.setValue("hand", side)
        self.recalibrate()

    def recalibrate(self):
        self.stop("Calibration reset")
        self.engine.calibrate()

    def edit_binding(self):
        self.stop("Gesture settings opened")
        dialog = QDialog(self)
        dialog.setWindowTitle("Gesture bindings")
        form = QFormLayout(dialog)
        mode = QComboBox()
        mode.addItems(MODES)
        mode.setCurrentText(self.engine.mode)
        pose = QComboBox()
        pose.addItems(POSES)
        action = QComboBox()
        action.addItems(("Use mode default", *ACTIONS))
        form.addRow("Mode", mode)
        form.addRow("Pose", pose)
        form.addRow("Action", action)
        shortcut = QLineEdit()
        shortcut.setPlaceholderText("Use the default shortcut")
        form.addRow("Key combination", shortcut)
        action.currentTextChanged.connect(lambda value: shortcut.setEnabled(value == "Shortcut"))
        default = label("", "subtitle")
        form.addRow(default)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons)
        def validate():
            if action.currentText() == "Shortcut" and shortcut.text().strip():
                try:
                    parse_shortcut(shortcut.text())
                except ValueError as exc:
                    default.setText(str(exc))
                    return
            dialog.accept()

        buttons.accepted.connect(validate)
        buttons.rejected.connect(dialog.reject)

        def load():
            key = mode.currentText(), pose.currentText()
            action.setCurrentText(self.engine.bindings.get(key, "Use mode default"))
            shortcut.setText(self.engine.shortcuts.get(key, ""))
            shortcut.setEnabled(action.currentText() == "Shortcut")
            builtin = DEFAULTS.get(key[0], {}).get(key[1], "See the gesture guide")
            default.setText(f"Mode default · {builtin}")

        mode.currentTextChanged.connect(load)
        pose.currentTextChanged.connect(load)
        load()
        if dialog.exec():
            key = mode.currentText(), pose.currentText()
            setting = f"bindings/{key[0]}/{key[1]}"
            if action.currentIndex() == 0:
                self.engine.bindings.pop(key, None)
                self.settings.remove(setting)
            else:
                self.engine.bindings[key] = action.currentText()
                self.settings.setValue(setting, action.currentText())
            shortcut_setting = f"bindingShortcuts/{key[0]}/{key[1]}"
            if action.currentText() == "Shortcut" and shortcut.text().strip():
                self.engine.shortcuts[key] = shortcut.text().strip()
                self.settings.setValue(shortcut_setting, shortcut.text().strip())
            else:
                self.engine.shortcuts.pop(key, None)
                self.settings.remove(shortcut_setting)
            self.log(f"Updated {key[0]} · {key[1]}")

    def clear_canvas(self):
        self.surface.strokes.clear()
        self.surface.active = None
        self.surface.update()

    def change_mode(self, mode):
        self.stop(f"{mode} mode")
        self.engine.mode = mode
        self.hint.setText(MODE_HELP[mode])
        self.surface.mode = mode
        self.surface.setVisible(mode in ("Drawing", "Keyboard"))
        self.compose.setVisible(mode == "Keyboard")
        self.clear.setVisible(mode == "Drawing")
        self.preview.setMinimumHeight(150 if mode in ("Drawing", "Keyboard") else 290)
        self.setMinimumHeight(760 if mode in ("Drawing", "Keyboard") else 660)
        self.tabs.setCurrentIndex(0)
        self.fade.stop()
        self.fade.start()

    def refresh_output(self):
        state = self.metrics["OUTPUT"]
        armed = self.safety.armed
        state.setText("Live control" if armed else "Simulation")
        if hasattr(self, "hotkey"):
            self.arm_button.setEnabled(self.hotkey.ready and self.last_frame is not None)
        state.setProperty("armed", armed)
        state.style().unpolish(state)
        state.style().polish(state)
        self.arm_button.setText("Return to simulation" if armed else "Enable live control")

    def stop(self, message):
        self.stop_generation += 1
        self.safety.stop()
        self.engine.reset()
        self.surface.active = self.surface.cursor = self.preview.cursor = None
        self.surface.update()
        self.preview.update()
        self.refresh_output()
        self.log(message)
        self.set_status(message)

    def toggle_arm(self):
        if self.safety.armed:
            self.stop("Returned to simulation")
            return
        if not self.worker or self.last_frame is None or monotonic() - self.last_frame >= 0.27:
            self.set_status("Start the camera and wait for the live preview before enabling control.")
            return
        try:
            if not self.native.trusted() and not self.native.request_access():
                self.log("Accessibility permission required")
                QMessageBox.information(
                    self, "Accessibility permission",
                    "Allow this copy of AirControl in System Settings → Privacy & Security → Accessibility, then try again.",
                )
                return
            generation = self.stop_generation
            answer = QMessageBox.question(
                self, "Enable live control?",
                "Gestures can send input to the focused application. Press Control–Option–Command–Escape to stop instantly.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes or generation != self.stop_generation:
                return
            if self.last_frame is None or monotonic() - self.last_frame >= 0.27:
                self.log("Live control could not start because the camera feed paused.")
                QMessageBox.information(self, "Camera feed paused", "Wait for the camera preview, then try again.")
                return
            if not self.safety.arm():
                self.log("Live control requires Accessibility permission and the emergency shortcut.")
                QMessageBox.warning(
                    self, "Live control unavailable",
                    "Check Accessibility permission and quit any other open copy of AirControl before trying again.",
                )
                return
        except Exception as exc:
            self.stop("Live control could not start")
            QMessageBox.warning(self, "Live control error", str(exc))
            return
        self.engine.reset()
        self.refresh_output()
        self.log("Live control enabled")
        self.set_status("Point steadily to resume gesture commands.")

    def toggle_camera(self):
        if self.worker:
            self.stop("Camera stopped")
            self.worker.requestInterruption()
            self.camera_button.setEnabled(False)
        else:
            if not MODEL.is_file():
                self.set_status("Hand model missing. Run scripts/download-model.sh.")
                return
            self.camera_button.setEnabled(False)
            self.pending_camera = True
            self.set_status("Checking camera permission…")
            self.camera_request += 1
            request = self.camera_request

            def complete(allowed):
                self.camera_authorized.emit(request, bool(allowed))

            try:
                if getattr(sys, "frozen", False):
                    QApplication.instance().requestPermission(
                        QCameraPermission(), self,
                        lambda result: complete(result.status() == Qt.PermissionStatus.Granted),
                    )
                else:
                    camera_permission(complete)
            except Exception as exc:
                self.pending_camera = False
                self.camera_button.setEnabled(True)
                self.set_status(f"Could not request camera access · {exc}")
                return
            QTimer.singleShot(20000, self, lambda: self.permission_timeout(request))

    def permission_timeout(self, request):
        if self.pending_camera and request == self.camera_request:
            self.pending_camera = False
            self.camera_button.setEnabled(True)
            self.set_status("Camera permission is waiting. Check for the macOS prompt, then try Start camera again.")

    def permission_result(self, request, allowed):
        if not self.pending_camera or request != self.camera_request:
            return
        self.pending_camera = False
        if not allowed:
            self.camera_button.setEnabled(True)
            self.set_status("Allow Camera access in System Settings → Privacy & Security → Camera.")
            self.log("Camera permission unavailable")
            return
        self.worker = Camera()
        self.worker.failed.connect(self.camera_failed)
        self.worker.finished.connect(self.camera_finished)
        self.preview.message = "Starting camera…"
        self.preview.update()
        self.camera_button.setText("Stop camera")
        self.camera_button.setEnabled(True)
        self.worker.start()
        self.engine.calibrate()
        self.set_status("Starting camera…")

    def camera_failed(self, message):
        self.stop(f"Camera error · {message}")

    def camera_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.last_frame = None
        self.arm_button.setEnabled(False)
        self.preview.image = None
        self.preview.message = "Camera off"
        self.preview.update()
        self.metrics["TRACKING FPS"].setText("—")
        self.metrics["HAND CONFIDENCE"].setText("—")
        self.metrics["CURRENT GESTURE"].setText("—")
        self.camera_button.setText("Start camera")
        self.camera_button.setEnabled(True)

    def tick(self):
        if self.worker is None:
            return
        if self.safety.armed and not self.native.trusted():
            self.stop("Accessibility permission was removed")
        frame = self.worker.take()
        now = monotonic()
        if frame is None:
            if self.last_frame is not None and now - self.last_frame >= 0.27:
                self.last_frame = None
                self.arm_button.setEnabled(self.safety.armed)
                self.safety.pause()
                self.engine.reset()
                self.surface.active = self.surface.cursor = self.preview.cursor = None
                self.preview.image = None
                self.preview.message = "Waiting for camera frames…"
                self.preview.update()
                self.surface.update()
                for metric in ("TRACKING FPS", "HAND CONFIDENCE", "CURRENT GESTURE"):
                    self.metrics[metric].setText("—")
                self.set_status("Tracking paused · Camera frames are delayed.")
            return
        self.last_frame = frame.timestamp
        self.arm_button.setEnabled(self.hotkey.ready and (self.safety.armed or now - frame.timestamp < 0.27))
        image = frame.image
        h, w = image.shape[:2]
        self.preview.image = QImage(image.data, w, h, image.strides[0], QImage.Format.Format_RGB888).copy()
        self.preview.cursor = self.surface.cursor = None
        commands, hand, pose = self.engine.step(frame.hands, now, frame.timestamp)
        self.metrics["TRACKING FPS"].setText(str(round(frame.fps)))
        self.metrics["HAND CONFIDENCE"].setText(f"{hand.score:.0%} · {hand.side}" if hand else "—")
        self.metrics["CURRENT GESTURE"].setText(pose.capitalize() if hand else "—")
        if hand is None:
            self.set_status("Tracking paused · Show your control hand to the camera.")
        elif self.engine.calibrating:
            self.set_status("Calibrating · Hold an index point where you want the center of your tracking area.")
        elif not self.engine.ready:
            self.set_status("Point steadily to resume gesture commands.")
        else:
            self.set_status("Tracking active")
        # Modal dialogs have nested event loops. Keep tracking visible while suppressing input.
        if QApplication.activeModalWidget():
            self.safety.pause()
            self.engine.reset()
            self.surface.active = None
        else:
            try:
                for command in commands:
                    self.apply_command(command)
            except Exception as exc:
                self.stop(f"Input error · {exc}")
        self.preview.update()
        if self.surface.isVisible():
            self.surface.update()

    def apply_command(self, command):
        name, value = command.name, command.value
        if name == "cursor":
            self.preview.cursor = value
            if self.engine.mode in ("Keyboard", "Drawing"):
                self.surface.cursor = value
                return
        if name == "stroke":
            self.surface.stroke(value)
            return
        if name == "stroke end":
            self.surface.active = None
            return
        if name == "keyboard select":
            key = self.surface.select(value)
            if key:
                self.select_key(key)
            return
        sent = self.safety.dispatch(command)
        if name not in ("cursor", "scroll", "drag end"):
            self.log(f"{'Live' if sent else 'Simulated'} · {name}")

    def select_key(self, key):
        value = {"Space": " ", "Enter": "\n"}.get(key, key)
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if (self.external_typing.isChecked() and self.safety.armed and front
                and front.processIdentifier() != os.getpid()):
            self.safety.dispatch(Command("type", key if key in ("Enter", "Backspace") else value))
        elif key == "Backspace":
            cursor = self.compose.textCursor()
            cursor.deletePreviousChar()
            self.compose.setTextCursor(cursor)
        else:
            self.compose.insertPlainText(value)

    def closeEvent(self, event):
        self.safety.stop()
        if self.worker:
            self.worker.requestInterruption()
            event.ignore()
            self.worker.finished.connect(self.close, Qt.ConnectionType.QueuedConnection)
        else:
            self.hotkey.close()
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AirControl AI")
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(ROOT / "assets" / "icon.png")))
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    return app.exec()
