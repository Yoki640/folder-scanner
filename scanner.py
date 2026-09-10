import sys
import os
import heapq
import hashlib
import threading
import shutil
import subprocess
import time
from datetime import datetime
from concurrent.futures import (
    ThreadPoolExecutor, wait, FIRST_COMPLETED, as_completed
)
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

sys.setrecursionlimit(10000)

try:
    sys.setswitchinterval(0.005)
except Exception:
    pass

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

if IS_WIN:
    SYSTEM_FOLDERS = {
        "$Recycle.Bin", "System Volume Information", "Windows",
        "Program Files", "Program Files (x86)", "ProgramData",
        "boot", "Recovery", "PerfLogs", "MSOCache", "WinSxS",
        "WindowsApps", "$Windows.~BT", "$Windows.~WS", "Windows.old",
        "System32", "SysWOW64", "Installer", "assembly",
        "Microsoft", "Microsoft.NET", "NVIDIA", "AMD", "Intel",
        "Config.Msi", "Documents and Settings", "ServiceProfiles",
        "$SysReset", "$WinREAgent", "OneDriveTemp",
    }
elif IS_MAC:
    SYSTEM_FOLDERS = {
        "System", "Library", "private", ".Spotlight-V100", ".fseventsd",
        ".DocumentRevisions-V100", ".TemporaryItems", ".Trashes",
        "Volumes", "cores", "dev", "Network", "Applications",
    }
else:
    SYSTEM_FOLDERS = {
        "proc", "sys", "dev", "run", "boot", "lost+found",
        "snap", ".cache", ".local", "var", "srv", "mnt", "media",
    }
SYSTEM_FOLDERS |= {
    "node_modules", "__pycache__", ".git", ".svn", ".hg",
    ".idea", ".vscode", ".venv", "venv", "$RECYCLE.BIN",
}

SYSTEM_FILES = {
    "pagefile.sys", "hiberfil.sys", "swapfile.sys",
    "DumpStack.log", "DumpStack.log.tmp",
}

MIN_DUP_SIZE = 1024 * 1024
HASH_THREADS = 2
HASH_SAMPLE_BYTES = 4 * 1024 * 1024
SPLIT_THRESHOLD = 10

MAX_WORKERS = 4
PARALLEL_THRESHOLD = 1
MONO_FONT_CSS = "'Consolas', 'Menlo', 'DejaVu Sans Mono', 'Courier New', monospace"

try:
    import xxhash
    _HAS_XXHASH = True
except ImportError:
    _HAS_XXHASH = False


def format_size(size):
    if size >= (1024 * 1024 * 1024):
        return f"{size / (1024 * 1024 * 1024):.2f} ГБ"
    elif size >= (1024 * 1024):
        return f"{size / (1024 * 1024):.2f} МБ"
    elif size >= 1024:
        return f"{size / 1024:.2f} КБ"
    return f"{size} Б"


def is_drive_root(path):
    p = os.path.normpath(path)
    if IS_WIN:
        return len(p) >= 3 and p[1] == ':' and p[2] in ('\\', '/') and len(p) <= 3
    return p == os.path.normpath(os.sep)


def hash_file_sampled(path, size):
    if _HAS_XXHASH:
        h = xxhash.xxh3_128()
    else:
        h = hashlib.blake2b(digest_size=16)

    sample = HASH_SAMPLE_BYTES
    try:
        if size <= sample * 2:
            with open(path, "rb", buffering=0) as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
                    time.sleep(0)
        else:
            with open(path, "rb", buffering=0) as f:
                h.update(f.read(sample))
                time.sleep(0)
                f.seek(size - sample)
                h.update(f.read(sample))
                time.sleep(0)
    except (OSError, PermissionError):
        return None
    return h.hexdigest()


def hash_many_sampled(items):
    if not items:
        return {}
    result = {}
    if HASH_THREADS <= 1:
        for p, s in items:
            result[p] = hash_file_sampled(p, s)
            time.sleep(0)
        return result
    with ThreadPoolExecutor(max_workers=HASH_THREADS) as ex:
        futures = {ex.submit(hash_file_sampled, p, s): p for p, s in items}
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                result[p] = fut.result()
            except Exception:
                result[p] = None
    return result


def _is_hidden_or_system(path):
    if not IS_WIN:
        return False
    try:
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x2
        FILE_ATTRIBUTE_SYSTEM = 0x4
        INVALID = 0xFFFFFFFF
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs == INVALID:
            return True
        return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))
    except Exception:
        return False


def reveal_in_explorer(path):
    try:
        norm = os.path.normpath(path)
        if IS_WIN:
            import ctypes
            parent = os.path.dirname(norm)
            if _is_hidden_or_system(norm):
                if os.path.isdir(parent):
                    os.startfile(parent)
                return
            rc = ctypes.windll.shell32.ShellExecuteW(
                None, "open", "explorer.exe",
                f'/select,"{norm}"',
                None, 1
            )
            if rc <= 32:
                if os.path.isdir(parent):
                    os.startfile(parent)
        elif IS_MAC:
            subprocess.Popen(['open', '-R', norm])
        else:
            parent = os.path.dirname(norm) or "/"
            for cmd in (['nautilus', '--select', norm],
                        ['dolphin', '--select', norm],
                        ['thunar', norm]):
                try:
                    subprocess.Popen(cmd)
                    return
                except FileNotFoundError:
                    continue
            subprocess.Popen(['xdg-open', parent])
    except Exception:
        pass


def scan_worker(root_path, bucket, cancel_event, split_threshold=SPLIT_THRESHOLD):
    total_size = 0
    total_files = 0
    total_folders = 0
    extension_sizes = {}
    top_files = []
    dup_candidates = []
    system_skipped = False
    has_files = False
    split_dirs = []

    splitext = os.path.splitext
    scandir = os.scandir

    def scan(path):
        nonlocal total_size, total_files, total_folders
        nonlocal has_files, system_skipped

        if cancel_event.is_set():
            return

        files_here = []
        dirs_here = []
        try:
            with scandir(path) as it:
                for entry in it:
                    if cancel_event.is_set():
                        return
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_file():
                            files_here.append(entry)
                        elif entry.is_dir():
                            if entry.name in SYSTEM_FOLDERS:
                                system_skipped = True
                            else:
                                dirs_here.append(entry.path)
                    except OSError:
                        continue
        except (PermissionError, OSError):
            return

        total_folders += 1
        for entry in files_here:
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            total_size += size
            total_files += 1
            has_files = True
            ext = splitext(entry.name)[1]
            ext = ext.lower() if ext else "без расширения"
            extension_sizes[ext] = extension_sizes.get(ext, 0) + size
            if entry.name not in SYSTEM_FILES:
                item = (size, entry.path)
                if len(top_files) < 5:
                    heapq.heappush(top_files, item)
                elif size > top_files[0][0]:
                    heapq.heapreplace(top_files, item)
                if size >= MIN_DUP_SIZE:
                    dup_candidates.append((size, entry.path))

        if len(dirs_here) > split_threshold:
            for d in dirs_here:
                split_dirs.append((d, bucket))
        else:
            for d in dirs_here:
                scan(d)

    scan(root_path)
    return {
        "bucket": bucket,
        "total_size": total_size, "total_files": total_files,
        "total_folders": total_folders, "extension_sizes": extension_sizes,
        "top_files": top_files, "dup_candidates": dup_candidates,
        "system_skipped": system_skipped, "has_files": has_files,
        "split_dirs": split_dirs,
    }


class AnimatedPieChart(QWidget):
    MIN_ANGLE_DEG = 1.2
    TITLE_H = 26
    TITLE_PAD = 8
    LEGEND_GAP = 18
    TICK_MS = 8
    EASE = 0.11

    def __init__(self, title=""):
        super().__init__()
        self.title = title
        self._display = 0.0
        self._target = 0.0
        self.target_data = []
        self.colors = []
        self._title_font = QFont("Arial", 10, QFont.Weight.DemiBold)
        self._legend_font = QFont("Arial", 8)
        self._last_paint_data = None

        self._ticker = QTimer(self)
        self._ticker.setInterval(self.TICK_MS)
        self._ticker.timeout.connect(self._tick)

        self.setMinimumHeight(180)

    @staticmethod
    def color_for(i, total):
        hue = int((i * 360.0 / max(total, 1)) + 20) % 360
        return QColor.fromHsv(hue, 175, 230)

    @property
    def animation_value(self):
        return self._display

    def _tick(self):
        diff = self._target - self._display
        if abs(diff) < 0.002:
            self._display = self._target
            self.update()
            self._ticker.stop()
            return
        self._display += diff * self.EASE
        self.update()

    def set_data(self, data):
        data = list(data)
        MAX_SLICES = 8
        if len(data) > MAX_SLICES:
            head = data[:MAX_SLICES - 1]
            tail_sum = sum(v for _, v in data[MAX_SLICES - 1:])
            if tail_sum > 0:
                head.append(("Остальные", tail_sum))
            data = head

        if not data:
            self.target_data = []
            self.colors = []
            self._last_paint_data = None
            self._display = 0.0
            self._target = 0.0
            self._ticker.stop()
            self.update()
            return

        if self._last_paint_data is not None and len(data) == len(self._last_paint_data):
            same = True
            for (n1, v1), (n2, v2) in zip(data, self._last_paint_data):
                if n1 != n2 or abs(v1 - v2) > max(0.5, v2 * 0.0005):
                    same = False
                    break
            if same:
                return

        self._last_paint_data = list(data)
        self.target_data = data
        self.colors = [self.color_for(i, len(data)) for i in range(len(data))]

        self._display = 0.0
        self._target = 1.0
        self.update()
        if not self._ticker.isActive():
            self._ticker.start(self.TICK_MS)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        if not self.target_data:
            painter.setPen(QColor(80, 80, 100))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Нет данных")
            painter.end()
            return

        total = sum(v for _, v in self.target_data)
        if total == 0:
            painter.end()
            return

        progress = self._display

        painter.setPen(QColor(170, 170, 200))
        painter.setFont(self._title_font)
        painter.drawText(rect.left(), rect.top() + self.TITLE_PAD,
                         rect.width(), self.TITLE_H,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         self.title)

        offset_y = self.TITLE_PAD + self.TITLE_H + self.LEGEND_GAP
        size = min(rect.width() - 180, rect.height() - offset_y - 10)
        if size < 40:
            size = 40
        x, y = 5, offset_y

        raw = [(v / total) * 360.0 for _, v in self.target_data]
        adj = [max(a, self.MIN_ANGLE_DEG) for a in raw]
        s = sum(adj) or 1.0
        adj = [a * 360.0 / s for a in adj]

        start_angle = 0.0
        for i, _ in enumerate(self.target_data):
            angle = adj[i] * progress
            painter.setBrush(self.colors[i])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(x, y, size, size,
                            int(start_angle * 16), int(angle * 16))
            start_angle += angle

        legend_x = x + size + 10
        legend_y = y
        painter.setFont(self._legend_font)
        for i, (name, val) in enumerate(self.target_data):
            painter.setBrush(self.colors[i])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(legend_x, legend_y + i * 19, 11, 11)
            painter.setPen(QColor(210, 210, 220))
            pct = (val / total) * 100.0 if total else 0.0
            if val > 0 and pct < 0.05:
                pct_str = ">0%"
            else:
                pct_str = f"{pct:.1f}%"
            painter.drawText(legend_x + 16, legend_y + i * 19 + 10,
                             f"{name} — {pct_str}")
        painter.end()


class SlidingTabBar(QWidget):
    tab_changed = pyqtSignal(int)

    TAB_HEIGHT = 40
    TAB_WIDTH = 160
    MARGIN = 4
    FONT_SIZE = 12
    RADIUS_OUTER = 20
    RADIUS_INNER = 16

    def __init__(self, titles, parent=None):
        super().__init__(parent)
        self.titles = titles
        self.current_index = 0
        self.setObjectName("slidingTabBar")
        self.setFixedHeight(self.TAB_HEIGHT)
        self.setFixedWidth(self.TAB_WIDTH * len(titles) + self.MARGIN * 2)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setStyleSheet(f"""
            #slidingTabBar {{
                background-color: #1e1e36;
                border-radius: {self.RADIUS_OUTER}px;
                border: 1px solid #2d2d4e;
            }}
        """)

        self.indicator = QFrame(self)
        self.indicator.setObjectName("tabIndicator")
        self.indicator.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.indicator.setStyleSheet(f"""
            #tabIndicator {{
                background-color: #2a2a48;
                border-radius: {self.RADIUS_INNER}px;
                border: 1px solid #3a3a5e;
            }}
        """)

        self.anim = QPropertyAnimation(self.indicator, b"geometry", self)
        self.anim.setDuration(240)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        try:
            self.anim.setUpdateInterval(8)
        except Exception:
            pass

        layout = QHBoxLayout(self)
        layout.setContentsMargins(self.MARGIN, self.MARGIN,
                                  self.MARGIN, self.MARGIN)
        layout.setSpacing(0)

        self.labels = []
        for i, t in enumerate(titles):
            lbl = QLabel(t)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda e, idx=i: self._on_click(idx)
            layout.addWidget(lbl, 1)
            self.labels.append(lbl)

        self._update_label_styles()
        QTimer.singleShot(0, lambda: self._position_indicator(animate=False))

    def _update_label_styles(self):
        for i, lbl in enumerate(self.labels):
            if i == self.current_index:
                lbl.setStyleSheet(
                    f"color: #ffffff; font-size: {self.FONT_SIZE}px;"
                    "font-weight: 700; background: transparent;"
                )
            else:
                lbl.setStyleSheet(
                    f"color: #8888aa; font-size: {self.FONT_SIZE}px;"
                    "font-weight: 500; background: transparent;"
                )

    def _on_click(self, idx):
        if idx == self.current_index:
            return
        self.current_index = idx
        self._update_label_styles()
        self._position_indicator(animate=True)
        self.tab_changed.emit(idx)

    def set_current(self, idx, animate=False):
        if 0 <= idx < len(self.labels) and idx != self.current_index:
            self.current_index = idx
            self._update_label_styles()
            self._position_indicator(animate=animate)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_indicator(animate=False)

    def _position_indicator(self, animate=True):
        x = self.MARGIN + self.current_index * self.TAB_WIDTH
        h = self.TAB_HEIGHT - 2 * self.MARGIN
        target = QRect(x, self.MARGIN, self.TAB_WIDTH, h)
        if animate:
            self.anim.stop()
            self.anim.setStartValue(self.indicator.geometry())
            self.anim.setEndValue(target)
            self.anim.start()
        else:
            self.indicator.setGeometry(target)
        self.indicator.lower()


class ModernTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(40)
        self.setStyleSheet(
            "background-color: #1a1a2e;"
            "border-top-left-radius: 12px; border-top-right-radius: 12px;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(6)
        self.title_label = QLabel("📁 Сканер папок")
        self.title_label.setStyleSheet(
            "color: #c0c0d0; font-size: 13px; font-weight: 600; background: transparent;")
        self.min_btn = self._create_btn("─")
        self.max_btn = self._create_btn("☐")
        self.close_btn = self._create_btn("✕")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #a0a0b0; border: none;
                font-size: 14px; padding: 4px 12px; border-radius: 6px;
            }
            QPushButton:hover { background: #e81123; color: #ffffff; }
        """)
        self.min_btn.clicked.connect(self.parent.showMinimized)
        self.max_btn.clicked.connect(self.toggle_maximize)
        self.close_btn.clicked.connect(self.parent.close)
        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)
        self.drag_pos = None
        self.setMouseTracking(True)

    def _create_btn(self, text):
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #a0a0b0; border: none;
                font-size: 14px; padding: 4px 12px; border-radius: 6px;
            }
            QPushButton:hover { background: #2d2d44; color: #ffffff; }
        """)
        return btn

    def toggle_maximize(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.max_btn.setText("☐")
        else:
            self.parent.showMaximized()
            self.max_btn.setText("❐")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_pos is not None:
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.parent.move(self.parent.pos() + delta)
            self.drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_pos = None


class ScannerApp(QMainWindow):
    update_progress_signal = pyqtSignal(int)
    append_output_signal = pyqtSignal(str)
    scan_finished_signal = pyqtSignal()
    set_top_files_signal = pyqtSignal(list)
    set_folder_chart_signal = pyqtSignal(list)
    set_file_chart_signal = pyqtSignal(list)
    dup_found_signal = pyqtSignal(list)
    dup_status_signal = pyqtSignal(str)
    set_cancel_btn_signal = pyqtSignal(str, bool)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(1300, 750)
        self.resize(1450, 800)

        self._scanning = False
        self._cancel_event = threading.Event()
        self._last_dup_candidates = []
        self._current_anim = None

        container = QWidget()
        container.setObjectName("container")
        container.setStyleSheet("""
            #container {
                background-color: #16162a;
                border-radius: 12px;
                border: 1px solid #2a2a44;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 150))
        container.setGraphicsEffect(shadow)
        self.setCentralWidget(container)
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.title_bar = ModernTitleBar(self)
        main_layout.addWidget(self.title_bar)

        inner = QWidget()
        inner.setStyleSheet(
            "background-color: #16162a;"
            "border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;"
        )
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(20, 14, 20, 16)
        inner_layout.setSpacing(12)

        self.tab_bar = SlidingTabBar(["📊   Обзор", "🔍   Дубликаты"])
        self.tab_bar.tab_changed.connect(self._switch_tab)
        inner_layout.addWidget(self.tab_bar, 0, Qt.AlignmentFlag.AlignLeft)

        self.content_frame = QFrame()
        self.content_frame.setObjectName("contentFrame")
        self.content_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.content_frame.setStyleSheet("""
            #contentFrame {
                background-color: #141426;
                border-radius: 14px;
                border: 1px solid #2a2a44;
            }
        """)
        cf_layout = QVBoxLayout(self.content_frame)
        cf_layout.setContentsMargins(0, 0, 0, 0)
        cf_layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: transparent;")
        cf_layout.addWidget(self.stack)

        inner_layout.addWidget(self.content_frame, 1)
        main_layout.addWidget(inner, 1)

        self._build_overview_tab()
        self._build_duplicates_tab()
        self.tab_bar.set_current(0, animate=False)

        self.update_progress_signal.connect(self.progress.setValue)
        self.append_output_signal.connect(self.output.append)
        self.scan_finished_signal.connect(self._on_scan_finished)
        self.set_top_files_signal.connect(self._populate_top_files)
        self.set_folder_chart_signal.connect(self.folder_chart.set_data)
        self.set_file_chart_signal.connect(self.file_chart.set_data)
        self.dup_found_signal.connect(self._show_duplicates)
        self.dup_status_signal.connect(self.dup_status.setText)
        self.set_cancel_btn_signal.connect(self._apply_cancel_state)

        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self.start_scan)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, activated=self.start_scan)

        QTimer.singleShot(0, self.path_input.setFocus)

    def _switch_tab(self, index):
        if index == self.stack.currentIndex():
            return
        widget = self.stack.widget(index)
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda w=widget: w.setGraphicsEffect(None))
        self.stack.setCurrentIndex(index)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._current_anim = anim

    def _build_overview_tab(self):
        page = QWidget()
        page.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        path_layout = QHBoxLayout()
        path_layout.setSpacing(10)
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Введите путь к папке... (Enter — запуск / отмена)")
        self.path_input.setStyleSheet("""
            QLineEdit {
                background-color: #1f1f3a;
                border: 1px solid #2a2a4a;
                border-radius: 10px;
                padding: 12px 16px;
                color: #c0c0d0;
                font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #8b6fcf; }
        """)
        self.path_input.returnPressed.connect(self.start_scan)
        self.select_btn = QPushButton("📂")
        self.select_btn.setFixedSize(44, 44)
        self.select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_btn.setStyleSheet("""
            QPushButton {
                background-color: #1f1f3a;
                border: 1px solid #2a2a4a;
                border-radius: 10px;
                color: #c0c0d0;
                font-size: 20px;
            }
            QPushButton:hover { background-color: #2a2a4a; border-color: #8b6fcf; }
            QPushButton:disabled { background-color: #15152a; color: #444458; border-color: #1f1f3a; }
        """)
        self.select_btn.clicked.connect(self.select_folder)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.select_btn)
        layout.addLayout(path_layout)

        self.scan_btn = QPushButton("🚀 Сканировать")
        self.scan_btn.setFixedHeight(48)
        self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_btn.setStyleSheet(self._scan_style_idle())
        self.scan_btn.clicked.connect(self.start_scan)
        layout.addWidget(self.scan_btn)

        self.progress = QProgressBar()
        self.progress.setStyleSheet("""
            QProgressBar { background-color: #1f1f3a; border: none; border-radius: 4px; height: 5px; }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6a4ca8, stop:1 #8b6fcf);
                border-radius: 4px;
            }
        """)
        self.progress.setFixedHeight(5)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        bottom = QHBoxLayout()
        bottom.setSpacing(20)

        left = QVBoxLayout()
        left.setSpacing(10)
        self.folder_chart = AnimatedPieChart("📁  Папки")
        left.addWidget(self.folder_chart)
        self.file_chart = AnimatedPieChart("📄  Расширения")
        left.addWidget(self.file_chart)
        bottom.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(8)
        out_title = QLabel("📋 Результаты")
        out_title.setStyleSheet("color: #8888aa; font-size: 13px; font-weight: 500;")
        right.addWidget(out_title)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.output.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.output.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.output.setStyleSheet(f"""
            QTextEdit {{
                background-color: #0e0e1a;
                border: 1px solid #1f1f3a;
                border-radius: 10px;
                color: #b0b0c8;
                font-family: {MONO_FONT_CSS};
                font-size: 13px;
                padding: 12px;
            }}
        """)
        right.addWidget(self.output, 3)

        top_label = QLabel("📌 Топ-5 файлов (двойной клик — открыть в проводнике)")
        top_label.setStyleSheet("color: #8888aa; font-size: 12px;")
        right.addWidget(top_label)

        self.top_files_list = QListWidget()
        self.top_files_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.top_files_list.setStyleSheet(f"""
            QListWidget {{
                background-color: #0e0e1a;
                border: 1px solid #1f1f3a;
                border-radius: 10px;
                color: #c0c0d0;
                font-family: {MONO_FONT_CSS};
                font-size: 12px;
                padding: 6px;
                outline: none;
            }}
            QListWidget::item {{ padding: 4px; }}
            QListWidget::item:selected {{ background: #2a2a4a; color: #ffffff; }}
            QListWidget::item:hover {{ background: #1f1f3a; }}
        """)
        self.top_files_list.itemDoubleClicked.connect(self._open_top_file)
        right.addWidget(self.top_files_list, 2)

        bottom.addLayout(right, 2)
        layout.addLayout(bottom)

        actions = QHBoxLayout()
        actions.addStretch()
        self.clear_btn = QPushButton("🗑️ Очистить")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #2a2a4a;
                border-radius: 8px;
                padding: 6px 20px;
                color: #8888aa;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2a1a2a;
                border-color: #a04060;
                color: #ffffff;
            }
        """)
        self.clear_btn.clicked.connect(self.clear_output)
        actions.addWidget(self.clear_btn)
        layout.addLayout(actions)

        self.stack.addWidget(page)

    def _build_duplicates_tab(self):
        page = QWidget()
        page.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        info = QLabel(
            "🔍 Дубликаты — файлы, у которых совпадают имя, размер и содержимое.\n"
            "Порог: файлы ≥ 1 МБ. Сначала отсканируй папку на вкладке «Обзор»."
        )
        info.setStyleSheet("color: #8888aa; font-size: 12px;")
        layout.addWidget(info)

        row = QHBoxLayout()
        self.dup_btn = QPushButton("🔍 Найти дубликаты")
        self.dup_btn.setFixedHeight(42)
        self.dup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dup_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6a4ca8, stop:1 #8b6fcf);
                border: none; border-radius: 10px; padding: 10px 24px;
                color: #ffffff; font-size: 14px; font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7a5cb8, stop:1 #9b7fdf);
            }
            QPushButton:disabled { background-color: #2a2a44; color: #666680; }
        """)
        self.dup_btn.clicked.connect(self.find_duplicates)
        row.addWidget(self.dup_btn)
        self.dup_status = QLabel("Ожидание сканирования...")
        self.dup_status.setStyleSheet("color: #8888aa; font-size: 13px;")
        row.addWidget(self.dup_status, 1)
        layout.addLayout(row)

        self.dup_list = QTreeWidget()
        self.dup_list.setHeaderLabels(["Файл", "Размер", "Путь"])
        self.dup_list.setColumnWidth(0, 280)
        self.dup_list.setColumnWidth(1, 100)
        self.dup_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.dup_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.dup_list.header().setStretchLastSection(True)
        self.dup_list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.dup_list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.dup_list.setStyleSheet(f"""
            QTreeWidget {{
                background-color: #0e0e1a;
                border: 1px solid #1f1f3a;
                border-radius: 10px;
                color: #c0c0d0;
                font-family: {MONO_FONT_CSS};
                font-size: 12px;
                outline: none;
            }}
            QTreeWidget::item {{ padding: 4px; }}
            QTreeWidget::item:selected {{ background: #2a2a4a; }}
            QTreeWidget QHeaderView {{
                background-color: transparent;
                border: none;
            }}
            QTreeWidget QHeaderView::section {{
                background-color: #1a1a2e;
                color: #8888aa;
                border: none;
                border-bottom: 1px solid #1f1f3a;
                padding: 6px 8px;
            }}
            QTreeWidget QHeaderView::section:first {{
                border-top-left-radius: 10px;
            }}
            QTreeWidget QHeaderView::section:last {{
                border-top-right-radius: 10px;
            }}
        """)
        self.dup_list.itemDoubleClicked.connect(self._open_dup_file)
        layout.addWidget(self.dup_list, 1)

        self.stack.addWidget(page)

    def _scan_style_idle(self):
        return """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6a4ca8, stop:1 #8b6fcf);
                border: none; border-radius: 10px; padding: 12px;
                color: #ffffff; font-size: 16px; font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7a5cb8, stop:1 #9b7fdf);
            }
            QPushButton:disabled { background-color: #2a2a44; color: #666680; }
        """

    def _scan_style_cancel(self):
        return """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #a04060, stop:1 #c05070);
                border: none; border-radius: 10px; padding: 12px;
                color: #ffffff; font-size: 16px; font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #b05070, stop:1 #d06080);
            }
        """

    def _scan_style_cancelling(self):
        return """
            QPushButton {
                background-color: #2a2a44;
                border: none; border-radius: 10px; padding: 12px;
                color: #9999b0; font-size: 16px; font-weight: 700;
            }
        """

    def _apply_cancel_state(self, text, enabled):
        self.scan_btn.setText(text)
        self.scan_btn.setEnabled(enabled)

    def _on_scan_finished(self):
        self._scanning = False
        self.scan_btn.setText("🚀 Сканировать")
        self.scan_btn.setStyleSheet(self._scan_style_idle())
        self.scan_btn.setEnabled(True)
        self.select_btn.setEnabled(True)
        self.progress.setValue(100)
        self.dup_btn.setEnabled(True)

    def _open_top_file(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            reveal_in_explorer(path)

    def _open_dup_file(self, item, _col):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            reveal_in_explorer(path)

    def _populate_top_files(self, items):
        self.top_files_list.clear()
        for size, path in items:
            text = f"{format_size(size)}  ·  {path}"
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, path)
            self.top_files_list.addItem(it)

    def _show_duplicates(self, groups):
        self.dup_list.clear()
        total_wasted = 0
        for group in groups:
            size = group[0][0]
            wasted = size * (len(group) - 1)
            total_wasted += wasted
            parent = QTreeWidgetItem(
                self.dup_list,
                [f"🗂 {len(group)} копий  ·  {os.path.basename(group[0][1])}",
                 format_size(size),
                 f"освободить {format_size(wasted)}"]
            )
            parent.setExpanded(True)
            parent.setForeground(1, QColor(255, 150, 150))
            parent.setForeground(2, QColor(255, 200, 100))
            for s, path in group:
                child = QTreeWidgetItem(parent, [
                    os.path.basename(path), format_size(s),
                    os.path.dirname(path)
                ])
                child.setData(0, Qt.ItemDataRole.UserRole, path)
        if groups:
            self.dup_status.setText(
                f"групп: {len(groups)}  ·  можно освободить: {format_size(total_wasted)}"
            )
        else:
            self.dup_status.setText("дубликатов не найдено")

    def clear_output(self):
        self.output.clear()
        self.folder_chart.set_data([])
        self.file_chart.set_data([])
        self.top_files_list.clear()
        self.progress.setValue(0)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if folder:
            self.path_input.setText(folder)

    def start_scan(self):
        if self._scanning:
            self._cancel_event.set()
            self.set_cancel_btn_signal.emit("⏳ Отмена...", False)
            self.scan_btn.setStyleSheet(self._scan_style_cancelling())
            self.append_output_signal.emit("🛑 Запрошена отмена...\n")
            return

        path = self.path_input.text().strip()
        if not path or not os.path.isdir(path):
            self.output.append("❌ Ошибка: укажите существующую папку!\n")
            return

        self._scanning = True
        self._cancel_event.clear()
        self.scan_btn.setText("🛑 Отменить")
        self.scan_btn.setStyleSheet(self._scan_style_cancel())
        self.scan_btn.setEnabled(True)
        self.select_btn.setEnabled(False)
        self.dup_btn.setEnabled(False)
        self.progress.setValue(0)
        self.output.clear()
        self.folder_chart.set_data([])
        self.file_chart.set_data([])
        self.top_files_list.clear()
        self._last_dup_candidates = []

        t = threading.Thread(target=self.scan_folder, args=(path,), daemon=True)
        t.start()

    def _merge_worker_result(self, agg, bucket, res):
        agg["total_size"] += res["total_size"]
        agg["total_files"] += res["total_files"]
        agg["total_folders"] += res["total_folders"]
        agg["system_skipped"] = agg["system_skipped"] or res["system_skipped"]
        agg["has_files"] = agg["has_files"] or res["has_files"]
        if res["total_size"] > 0:
            agg["folder_sizes"][bucket] = agg["folder_sizes"].get(bucket, 0) + res["total_size"]
        for ext, sz in res["extension_sizes"].items():
            agg["extension_sizes"][ext] = agg["extension_sizes"].get(ext, 0) + sz
        for size, p in res["top_files"]:
            item = (size, p)
            if len(agg["top_files"]) < 5:
                heapq.heappush(agg["top_files"], item)
            elif size > agg["top_files"][0][0]:
                heapq.heapreplace(agg["top_files"], item)
        if res["dup_candidates"]:
            agg["dup_candidates"].extend(res["dup_candidates"])

    def scan_folder(self, path):
        start_time = time.time()
        cancel = self._cancel_event

        try:
            self.append_output_signal.emit("⏳ Сканирование...\n")

            agg = {
                "total_size": 0, "total_files": 0, "total_folders": 0,
                "folder_sizes": {}, "extension_sizes": {},
                "top_files": [], "dup_candidates": [],
                "system_skipped": False, "has_files": False,
            }

            top_dirs = []
            root_own_size = 0
            splitext = os.path.splitext
            try:
                with os.scandir(path) as it:
                    for entry in it:
                        try:
                            if entry.is_symlink():
                                continue
                            if entry.is_dir():
                                if entry.name in SYSTEM_FOLDERS:
                                    agg["system_skipped"] = True
                                    continue
                                top_dirs.append(entry.path)
                            elif entry.is_file():
                                size = entry.stat().st_size
                                agg["total_size"] += size
                                agg["total_files"] += 1
                                agg["has_files"] = True
                                root_own_size += size
                                ext = splitext(entry.name)[1]
                                ext = ext.lower() if ext else "без расширения"
                                agg["extension_sizes"][ext] = agg["extension_sizes"].get(ext, 0) + size
                                if entry.name not in SYSTEM_FILES:
                                    item = (size, entry.path)
                                    if len(agg["top_files"]) < 5:
                                        heapq.heappush(agg["top_files"], item)
                                    elif size > agg["top_files"][0][0]:
                                        heapq.heapreplace(agg["top_files"], item)
                                    if size >= MIN_DUP_SIZE:
                                        agg["dup_candidates"].append((size, entry.path))
                        except OSError:
                            continue
            except (PermissionError, OSError) as e:
                self.append_output_signal.emit(f"❌ Не удалось открыть корень: {e}\n")
                return

            if root_own_size:
                agg["folder_sizes"]["(в корне)"] = root_own_size

            total_top = len(top_dirs)

            if total_top > 0 and not cancel.is_set():
                workers = min(MAX_WORKERS, max(1, total_top))
                self.append_output_signal.emit(
                    f"⚡ Потоков: {workers}, верхнеуровневых папок: {total_top}.\n"
                )
                processed = 0
                max_pct = 0

                with ThreadPoolExecutor(max_workers=workers) as ex:
                    task_queue = []
                    active = set()

                    for d in top_dirs:
                        task_queue.append((d, os.path.basename(d) or d))

                    while task_queue and len(active) < workers:
                        sd, sb = task_queue.pop(0)
                        active.add(ex.submit(
                            scan_worker, sd, sb, cancel, SPLIT_THRESHOLD
                        ))

                    while active:
                        if cancel.is_set():
                            break

                        done, active = wait(
                            active, timeout=0.05,
                            return_when=FIRST_COMPLETED
                        )

                        for fut in done:
                            if cancel.is_set():
                                break
                            try:
                                res = fut.result()
                            except Exception:
                                continue

                            bucket = res.get("bucket") or "(unknown)"
                            self._merge_worker_result(agg, bucket, res)
                            processed += 1

                            for subdir, sub_bucket in res.get("split_dirs", []):
                                if cancel.is_set():
                                    break
                                task_queue.append((subdir, sub_bucket))

                            while task_queue and len(active) < workers:
                                if cancel.is_set():
                                    break
                                sd, sb = task_queue.pop(0)
                                active.add(ex.submit(
                                    scan_worker, sd, sb, cancel, SPLIT_THRESHOLD
                                ))

                            total_estimate = processed + len(active) + len(task_queue)
                            if total_estimate > 0:
                                raw = int(processed * 99 / total_estimate)
                                if raw > max_pct:
                                    max_pct = raw
                                    self.update_progress_signal.emit(max_pct)

                if cancel.is_set():
                    self.append_output_signal.emit("🛑 Сканирование отменено.\n")
                    return
            else:
                if cancel.is_set():
                    self.append_output_signal.emit("🛑 Сканирование отменено.\n")
                    return

            if not agg["has_files"]:
                self.append_output_signal.emit("📭 Нет доступных файлов\n")
                return

            folder_data = [
                (n, s / (1024 * 1024))
                for n, s in sorted(agg["folder_sizes"].items(),
                                   key=lambda x: x[1], reverse=True)[:15]
            ]
            self.set_folder_chart_signal.emit(folder_data)

            file_data = [
                (ext, s / (1024 * 1024))
                for ext, s in sorted(agg["extension_sizes"].items(),
                                     key=lambda x: x[1], reverse=True)[:15]
            ]
            self.set_file_chart_signal.emit(file_data)

            top5 = sorted(agg["top_files"], reverse=True)
            self.set_top_files_signal.emit(top5)
            self._last_dup_candidates = agg["dup_candidates"]

            free_text = total_text = None
            is_drive = is_drive_root(path)
            if is_drive:
                try:
                    du = shutil.disk_usage(path)
                    free_text = format_size(du.free)
                    total_text = format_size(du.total)
                except OSError:
                    pass

            size_str = format_size(agg["total_size"])
            lines = ["──────────────────────────────────────────────────"]
            if is_drive and total_text and free_text:
                lines.append(f"💾 Общий размер диска: {total_text}")
                lines.append(f"📊 Свободно места: {free_text}")
            lines.append(f"📁 Папок: {agg['total_folders']}")
            lines.append(f"✅ Файлов: {agg['total_files']}")
            lines.append(f"✅ Размер просканированных файлов: {size_str}")
            if is_drive and agg["system_skipped"]:
                lines.append("⚠️ СИСТЕМНЫЕ ПАПКИ ПРОПУЩЕНЫ")
            self.append_output_signal.emit("\n".join(lines) + "\n")

            elapsed = time.time() - start_time
            if elapsed < 1:
                self.append_output_signal.emit(f"⏱️ Время: {elapsed * 1000:.0f} мс")
            else:
                self.append_output_signal.emit(f"⏱️ Время: {elapsed:.2f} сек")

        except Exception as e:
            self.append_output_signal.emit(f"❌ Ошибка: {e}\n")
        finally:
            self.scan_finished_signal.emit()

    def find_duplicates(self):
        if not self._last_dup_candidates:
            self.dup_status.setText("Сначала отсканируй папку на вкладке «Обзор».")
            return
        self.dup_btn.setEnabled(False)
        self.dup_status.setText("Поиск дубликатов...")
        self.dup_list.clear()
        t = threading.Thread(target=self._dup_worker, daemon=True)
        t.start()

    def _dup_worker(self):
        try:
            candidates = self._last_dup_candidates

            if not candidates:
                self.dup_found_signal.emit([])
                return

            by_key = {}
            for size, path in candidates:
                basename = os.path.basename(path)
                key = (basename, size)
                by_key.setdefault(key, []).append(path)

            groups_to_check = [(k, v) for k, v in by_key.items() if len(v) > 1]

            if not groups_to_check:
                self.dup_found_signal.emit([])
                return

            tasks = []
            for (bn, size), paths in groups_to_check:
                for p in paths:
                    tasks.append((p, size))

            total = len(tasks)
            self.dup_status_signal.emit(f"Проверка {total} файлов...")

            hashes = hash_many_sampled(tasks)

            final_groups = {}
            for (bn, size), paths in groups_to_check:
                for p in paths:
                    h = hashes.get(p)
                    if h is None:
                        continue
                    final_groups.setdefault((bn, size, h), []).append(p)

            groups = []
            for (bn, size, h), paths in final_groups.items():
                if len(paths) < 2:
                    continue
                entries = sorted(((size, p) for p in paths), key=lambda x: x[1])
                groups.append(entries)

            groups.sort(key=lambda g: g[0][0] * (len(g) - 1), reverse=True)
            self.dup_found_signal.emit(groups)
        except Exception as e:
            self.dup_status_signal.emit(f"Ошибка: {e}")
        finally:
            self.dup_btn.setEnabled(True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ScannerApp()
    window.show()
    sys.exit(app.exec())
