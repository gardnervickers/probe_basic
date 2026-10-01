#!/usr/bin/env python

import os
import time

from mymill_vcp.mdi import abort_and_wait, wait_for_completion

try:
    import linuxcnc
except ImportError:  # Allows off-machine UI rendering and syntax checks.
    linuxcnc = None

try:
    from qtpy.QtCore import Qt, QThread, QTimer, Signal
    from qtpy.QtGui import QIcon, QPixmap
    from qtpy.QtWidgets import (
        QAbstractSpinBox,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # Off-machine render environment may have PyQt5 without qtpy.
    from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal as Signal
    from PyQt5.QtGui import QIcon, QPixmap
    from PyQt5.QtWidgets import (
        QAbstractSpinBox,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )


if linuxcnc is not None:
    STATE_LABELS = {
        linuxcnc.STATE_ESTOP: "ESTOP",
        linuxcnc.STATE_ESTOP_RESET: "READY",
        linuxcnc.STATE_ON: "ON",
        linuxcnc.STATE_OFF: "OFF",
    }
    MODE_LABELS = {
        linuxcnc.MODE_MANUAL: "MANUAL",
        linuxcnc.MODE_AUTO: "AUTO",
        linuxcnc.MODE_MDI: "MDI",
    }
else:
    STATE_LABELS = {}
    MODE_LABELS = {}


WCS_OPTIONS = [
    ("G54", 1),
    ("G55", 2),
    ("G56", 3),
    ("G57", 4),
    ("G58", 5),
    ("G59", 6),
    ("G59.1", 7),
    ("G59.2", 8),
    ("G59.3", 9),
]
WCS_BY_INDEX = {index: code for code, index in WCS_OPTIONS}


def _ini_file():
    if linuxcnc is None or not os.getenv("INI_FILE_NAME"):
        return None
    return linuxcnc.ini(os.getenv("INI_FILE_NAME"))


def _configured_joint_count(ini_file, default=3):
    if ini_file is None:
        return default
    try:
        return int(ini_file.find("KINS", "JOINTS"))
    except (TypeError, ValueError):
        return default


class MdiWorker(QThread):
    finished_action = Signal(bool, str)

    def __init__(self, mdi_commands, success_message, timeout=300.0, parent=None):
        super(MdiWorker, self).__init__(parent)
        if isinstance(mdi_commands, str):
            mdi_commands = [mdi_commands]
        self._mdi_commands = list(mdi_commands)
        self._success_message = success_message
        self._timeout = timeout

    def run(self):
        if linuxcnc is None:
            self.finished_action.emit(False, "LinuxCNC Python module unavailable")
            return

        command = linuxcnc.command()
        stat = linuxcnc.stat()
        previous_mode = None
        success = False
        message = "MDI command failed"

        try:
            stat.poll()
            previous_mode = getattr(stat, "task_mode", linuxcnc.MODE_MANUAL)
            if previous_mode != linuxcnc.MODE_MDI:
                command.mode(linuxcnc.MODE_MDI)
                self._wait_for_idle(command, stat, allow_in_position_skip=True)

            for mdi_command in self._mdi_commands:
                command.mdi(mdi_command)
                self._wait_for_idle(command, stat)
            success = True
            message = self._success_message
        except RuntimeError as exc:
            message = str(exc)
        except Exception:
            message = "MDI command failed"
        finally:
            can_restore = success or abort_and_wait(command, stat)
            try:
                if can_restore and previous_mode is not None and previous_mode != linuxcnc.MODE_MDI:
                    command.mode(previous_mode)
                    self._wait_for_idle(command, stat, allow_in_position_skip=True)
            except Exception:
                if success:
                    success = False
                    message = "Command finished but mode restore failed"

        self.finished_action.emit(success, message)

    def _wait_for_idle(self, command, stat, allow_in_position_skip=False):
        wait_for_completion(
            command, stat, self._timeout,
            allow_in_position_skip=allow_in_position_skip,
        )


class RotaryProbePanel(QWidget):
    def __init__(self, parent=None):
        super(RotaryProbePanel, self).__init__(parent)
        self.setObjectName("rotary_probe_panel")

        self._ini_file = _ini_file()
        self._joint_count = _configured_joint_count(self._ini_file)
        self._stat = linuxcnc.stat() if linuxcnc is not None else None
        self._worker = None
        self._worker_action = None
        self._last_message = "Checking rotary probing state"
        self._last_message_hold_until = 0.0
        self._selected_wcs_initialized = False

        self._build_ui()
        self._connect_signals()
        self._set_selected_wcs(1, user_selected=False)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(250)
        self._refresh()

    def _build_ui(self):
        self.setStyleSheet(
            """
QWidget#rotary_probe_panel {
    background: rgb(153, 158, 154);
    font-family: "Bebas Kai", "DejaVu Sans";
}
QFrame[section="true"] {
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1,
                                      stop:0 rgb(81, 86, 85),
                                      stop:0.160246 rgb(83, 84, 91),
                                      stop:0.489795 rgb(99, 102, 102),
                                      stop:0.699799 rgb(85, 88, 94),
                                      stop:0.90444 rgb(77, 84, 86),
                                      stop:1 rgb(109, 115, 118));
    border: 2px solid black;
    border-radius: 0px;
}
QLabel[title="true"] {
    color: white;
    font: 15pt "Bebas Kai";
}
QLabel[fieldLabel="true"] {
    color: white;
    font: 15pt "Bebas Kai";
}
QLabel[status="true"] {
    color: white;
    padding: 0px 4px;
    font: 13pt "Bebas Kai";
}
QLabel[routineTitle="true"] {
    color: white;
    font: 16pt "Bebas Kai";
}
QPushButton[routineButton="true"] {
    color: white;
    border-color: black;
    border-style: solid;
    border-radius: 7px;
    border-width: 2px;
    background: rgb(214, 215, 212);
}
QPushButton[stripButton="true"], QPushButton[wcsButton="true"] {
    color: white;
    border-color: black;
    border-style: solid;
    border-radius: 5px;
    border-width: 2px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #4e4e4e, stop:1 #3a3a3a);
    font: 14pt "Bebas Kai";
}
QPushButton:hover {
    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                stop: 0 #A19E9E, stop: 1.0 #5C5959);
}
QPushButton:pressed, QPushButton:checked {
    background: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(85, 85, 238, 255),
                                stop:0.544974 rgba(90, 91, 239, 255),
                                stop:1 rgba(126, 135, 243, 255));
}
QPushButton:disabled {
    color: rgba(255, 255, 255, 0.48);
    border-color: gray;
}
QPushButton[routineButton="true"]:disabled {
    border-color: black;
    background: rgb(214, 215, 212);
}
QDoubleSpinBox {
    background: white;
    color: black;
    border: 2px solid black;
    border-radius: 4px;
    padding: 2px 5px;
    font: 14pt "Bebas Kai";
}
QComboBox {
    background: white;
    color: black;
    border: 2px solid black;
    border-radius: 4px;
    padding: 2px 5px;
    font: 14pt "Bebas Kai";
}
QCheckBox {
    color: white;
    font: 12pt "Bebas Kai";
}
"""
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        content = QWidget()
        content.setFixedSize(465, 461)
        content.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        root.addWidget(content, 0, Qt.AlignCenter)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        routine_area = QWidget()
        routine_area.setFixedSize(465, 396)
        routine_area.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        content_layout.addWidget(routine_area)

        routine_grid = QGridLayout(routine_area)
        routine_grid.setContentsMargins(50, 0, 50, 0)
        routine_grid.setHorizontalSpacing(55)
        routine_grid.setVerticalSpacing(10)
        routine_grid.setAlignment(Qt.AlignCenter)

        self.setup_find_center_button = self._routine_button("rotary_center_setup.png")
        self.probe_a_rotary_button = self._routine_button("rotary_a0_from_flat.png")

        routine_grid.addWidget(
            self._routine_tile(
                self.setup_find_center_button,
                "CENTER",
            ),
            0,
            0,
        )
        routine_grid.addWidget(
            self._routine_tile(
                self.probe_a_rotary_button,
                "FLAT",
            ),
            0,
            1,
        )
        routine_grid.setColumnStretch(0, 0)
        routine_grid.setColumnStretch(1, 0)

        strip = QFrame()
        strip.setProperty("section", True)
        strip.setFixedSize(460, 65)
        strip_layout = QHBoxLayout(strip)
        strip_layout.setContentsMargins(10, 8, 10, 8)
        strip_layout.setSpacing(4)

        self._wcs_combo = QComboBox()
        self._wcs_combo.setFixedSize(72, 40)
        for code, index in WCS_OPTIONS:
            self._wcs_combo.addItem(code, index)

        self.setup_stock_diameter_input = self._spin_box(0.0, 200.0, 25.4, 0.1)
        self.setup_verify_checkbox = QCheckBox("VERIFY")
        self.setup_verify_checkbox.setChecked(True)

        strip_layout.addWidget(self._field_label("WCS"))
        strip_layout.addWidget(self._wcs_combo)
        strip_layout.addWidget(self._field_label("REF"))
        strip_layout.addWidget(self.setup_stock_diameter_input)
        strip_layout.addWidget(self.setup_verify_checkbox)
        strip_layout.addStretch(1)
        self.status_label = QLabel(self._last_message)
        self.status_label.setObjectName("rotary_probe_status")
        self.status_label.setProperty("status", True)
        self.status_label.setFixedSize(92, 40)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.hide()
        content_layout.addWidget(strip, 0, Qt.AlignHCenter)

    def _connect_signals(self):
        self._wcs_combo.currentIndexChanged.connect(self._wcs_combo_changed)
        self.setup_find_center_button.clicked.connect(self._probe_a_setup_center)
        self.probe_a_rotary_button.clicked.connect(self._probe_a_rotary)
        self.setup_stock_diameter_input.valueChanged.connect(self._input_changed)

    def _field_label(self, text):
        label = QLabel(text)
        label.setProperty("fieldLabel", True)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return label

    def _routine_tile(self, button, title):
        tile = QWidget()
        tile.setFixedWidth(140)
        tile_layout = QVBoxLayout(tile)
        tile_layout.setContentsMargins(0, 0, 0, 0)
        tile_layout.setSpacing(6)
        tile_layout.addWidget(button, 0, Qt.AlignHCenter)

        title_label = QLabel(title)
        title_label.setProperty("routineTitle", True)
        title_label.setAlignment(Qt.AlignCenter)
        tile_layout.addWidget(title_label)
        return tile

    def _routine_button(self, filename):
        button = QPushButton()
        button.setProperty("routineButton", True)
        button.setFixedSize(140, 140)
        button.setFocusPolicy(Qt.NoFocus)
        image_path = os.path.join(os.path.dirname(__file__), "images", filename)
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            button.setIconSize(pixmap.size().scaled(120, 120, Qt.KeepAspectRatio))
            icon = QIcon()
            icon.addPixmap(pixmap, QIcon.Normal, QIcon.Off)
            icon.addPixmap(pixmap, QIcon.Disabled, QIcon.Off)
            button.setIcon(icon)
        return button

    def _wcs_combo_changed(self, _index=None):
        self._selected_wcs_initialized = True

    def _spin_box(self, minimum, maximum, value, step):
        spin = QDoubleSpinBox()
        spin.setAlignment(Qt.AlignCenter)
        spin.setDecimals(4)
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        spin.setFixedSize(80, 40)
        spin.setValue(value)
        return spin

    def _set_selected_wcs(self, wcs_index, user_selected=False):
        for index in range(self._wcs_combo.count()):
            if self._wcs_combo.itemData(index) == wcs_index:
                self._wcs_combo.setCurrentIndex(index)
                break
        if user_selected:
            self._selected_wcs_initialized = True

    def _refresh(self):
        if self._stat is None:
            self._set_rotary_button_state(False, "NOT READY")
            return

        try:
            self._stat.poll()
        except Exception:
            self._set_rotary_button_state(False, "NOT READY")
            return

        if not self._selected_wcs_initialized:
            active_wcs_index = getattr(self._stat, "g5x_index", None)
            if active_wcs_index in WCS_BY_INDEX:
                self._set_selected_wcs(active_wcs_index)
                self._selected_wcs_initialized = True

        enabled, reason = self._rotary_setup_readiness()
        if self._worker is not None:
            running_messages = {
                "rotary_setup_center": "Setup center probing routine running",
                "rotary_a": "A0 probing routine running",
            }
            self._set_rotary_button_state(
                False,
                running_messages.get(self._worker_action, "Rotary probing routine running"),
            )
        else:
            self._set_rotary_button_state(enabled, self._ready_message() if enabled else reason)

    def _set_status_message(self, text, hold_seconds=0.0):
        self._last_message = text
        self._last_message_hold_until = time.time() + hold_seconds if hold_seconds > 0.0 else 0.0
        self.status_label.setText(text)

    def _set_rotary_button_state(self, enabled, status_text):
        setup_ok = self._setup_stock_diameter() > 0

        self.setup_find_center_button.setEnabled(enabled and setup_ok)
        self.probe_a_rotary_button.setEnabled(enabled)

        if enabled and time.time() < self._last_message_hold_until:
            self.status_label.setText(self._last_message)
        elif enabled:
            self._set_status_message(status_text)
        else:
            self.status_label.setText(status_text)

    def _rotary_setup_readiness(self):
        if linuxcnc is None:
            return False, "LinuxCNC unavailable"
        if self._joint_count < 4:
            return False, "A axis is not configured"
        if getattr(self._stat, "task_state", None) != linuxcnc.STATE_ON:
            return False, "Machine must be ON"
        if getattr(self._stat, "interp_state", None) != linuxcnc.INTERP_IDLE:
            return False, "Interpreter must be idle"
        if not bool(getattr(self._stat, "inpos", True)):
            return False, "Machine must be in position"
        return True, "Ready - writes {}".format(self._selected_wcs_code())

    def _selected_wcs_code(self):
        wcs_index = self._wcs_combo.currentData()
        if wcs_index in WCS_BY_INDEX:
            return WCS_BY_INDEX[wcs_index]
        return WCS_OPTIONS[0][0]

    def _ready_message(self):
        return "Ready - writes {}".format(self._selected_wcs_code())

    def _setup_stock_diameter(self):
        return float(self.setup_stock_diameter_input.value())

    def _setup_rotary_direction(self):
        return 1.0

    def _input_changed(self, _value=None):
        if self._worker is None:
            self._refresh()

    def _probe_a_setup_center(self):
        if self._setup_stock_diameter() <= 0:
            self._set_rotary_button_state(False, "Reference size estimate must be positive")
            return

        self._run_rotary_probe(
            "rotary_setup_center",
            "o<probe_a_setup_cylinder_center> call [{:.6f}] [{:.1f}] [{:.1f}]".format(
                self._setup_stock_diameter(),
                self._setup_rotary_direction(),
                1.0 if self.setup_verify_checkbox.isChecked() else 0.0,
            ),
            "Setup center probing complete",
            "Running setup center probing routine",
        )

    def _probe_a_rotary(self):
        self._run_rotary_probe(
            "rotary_a",
            "o<probe_a_rotary> call [{:.1f}]".format(self._setup_rotary_direction()),
            "A0 probing complete",
            "Running A0 probing routine",
        )

    def _run_rotary_probe(self, action, mdi_command, success_message, running_message):
        if self._stat is None:
            self._set_rotary_button_state(False, "LinuxCNC unavailable")
            return

        try:
            self._stat.poll()
        except Exception:
            self._set_rotary_button_state(False, "LinuxCNC disconnected")
            return

        enabled, reason = self._rotary_setup_readiness()
        if not enabled:
            self._set_rotary_button_state(False, reason)
            return

        selected_wcs = self._selected_wcs_code()
        self._worker = MdiWorker(
            [selected_wcs, mdi_command],
            "{} in {}".format(success_message, selected_wcs),
            timeout=300.0,
            parent=self,
        )
        self._worker_action = action
        self._worker.finished_action.connect(self._rotary_probe_finished)
        self._set_rotary_button_state(False, "{} in {}".format(running_message, selected_wcs))
        self._worker.start()

    def _rotary_probe_finished(self, success, message):
        self._worker = None
        self._worker_action = None
        self._refresh()
        self._set_status_message(message, hold_seconds=8.0)
