import sys
import os
import threading
import shutil
import time
from datetime import datetime
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

# === АНИМИРОВАННАЯ КРУГОВАЯ ДИАГРАММА ===
class AnimatedPieChart(QWidget):
    def __init__(self, title=""):
        super().__init__()
        self.data = []
        self.title = title
        self.animation_value = 0
        self.target_data = []
        self.animation = QPropertyAnimation(self, b"animationValue")
        self.animation.setDuration(800)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.colors = [
            QColor(255, 99, 132), QColor(54, 162, 235), QColor(255, 206, 86),
            QColor(75, 192, 192), QColor(153, 102, 255), QColor(255, 159, 64),
            QColor(128, 128, 128), QColor(201, 203, 207), QColor(255, 99, 132),
            QColor(54, 162, 235), QColor(255, 206, 86), QColor(75, 192, 192),
            QColor(153, 102, 255), QColor(255, 159, 64), QColor(128, 128, 128),
        ]
        self.setMinimumHeight(150)

    @pyqtProperty(float)
    def animationValue(self):
        return self.animation_value

    @animationValue.setter
    def animationValue(self, val):
        self.animation_value = val
        self.update()

    def set_data(self, data):
        self.target_data = data[:15]
        self.animation.stop()
        self.animation.setStartValue(0)
        self.animation.setEndValue(1)
        self.animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        if not self.target_data:
            painter.setPen(QColor(80, 80, 100))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Нет данных")
            return
        total = sum(v for _, v in self.target_data)
        if total == 0:
            return
        progress = self.animation_value
        painter.setPen(QColor(150, 150, 180))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(rect.left(), rect.top(), rect.width(), 18,
                         Qt.AlignmentFlag.AlignHCenter, self.title)
        offset_y = 20
        size = min(rect.width() - 160, rect.height() - 30)
        x = 5
        y = offset_y
        start_angle = 0
        for i, (name, val) in enumerate(self.target_data):
            angle = (val / total) * 360 * progress
            painter.setBrush(self.colors[i % len(self.colors)])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(x, y, size, size, int(start_angle * 16), int(angle * 16))
            start_angle += angle
        legend_x = x + size + 5
        legend_y = y
        for i, (name, val) in enumerate(self.target_data):
            painter.setBrush(self.colors[i % len(self.colors)])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(legend_x, legend_y + i * 18, 10, 10)
            painter.setPen(QColor(200, 200, 210))
            painter.setFont(QFont("Arial", 7))
            painter.drawText(legend_x + 14, legend_y + i * 18 + 9, name)
        painter.end()

# === СИСТЕМНЫЕ ПАПКИ ===
SYSTEM_FOLDERS = {
    "$Recycle.Bin", "System Volume Information", "Windows", "Program Files",
    "Program Files (x86)", "boot", "Documents and Settings", "Recovery",
    "Config.Msi", "PerfLogs", "swapfile.sys", "pagefile.sys",
    "MSOCache", "AMD", "Intel", "NVIDIA", "Drivers", "Temp", "tmp",
    "Cache", "Logs", "AppData", "Local Settings", "Application Data",
    "Microsoft", "Microsoft.NET", "Microsoft.SharePoint", "Windows.old",
    "$Windows.~BT", "$Windows.~WS", "OneDrive", "MicrosoftEdge",
    "WindowsApps", "WinSxS", "assembly", "System32", "SysWOW64",
    "Resources", "Installer", "Fonts", "Help", "Prefetch", "Recent",
    "ServiceProfiles", "Tasks", "WER", "winnt", "system", "drivers",
    "config", "security", "software", "default", "sam", "systemprofile"
}

def format_size(size):
    if size >= (1024 * 1024 * 1024):
        return f"{size / (1024 * 1024 * 1024):.2f} ГБ"
    elif size >= (1024 * 1024):
        return f"{size / (1024 * 1024):.2f} МБ"
    elif size >= 1024:
        return f"{size / 1024:.2f} КБ"
    return f"{size} Б"

def is_drive_root(path):
    return len(path) >= 3 and path[1] == ':' and (path[2] == '\\' or path[2] == '/') and len(path) <= 3

class ModernTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(40)
        self.setStyleSheet("background-color: #1a1a2e; border-top-left-radius: 12px; border-top-right-radius: 12px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(6)
        self.title_label = QLabel("📁 Сканер папок")
        self.title_label.setStyleSheet("color: #c0c0d0; font-size: 13px; font-weight: 600; background: transparent;")
        self.min_btn = self.create_btn("─")
        self.max_btn = self.create_btn("☐")
        self.close_btn = self.create_btn("✕")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #a0a0b0;
                border: none;
                font-size: 14px;
                padding: 4px 12px;
                border-radius: 6px;
            }
            QPushButton:hover { background: #e81123; color: #ffffff; border-radius: 6px; }
        """)
        self.min_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #a0a0b0;
                border: none;
                font-size: 14px;
                padding: 4px 12px;
                border-radius: 6px;
            }
            QPushButton:hover { background: #2d2d44; color: #ffffff; border-radius: 6px; }
        """)
        self.max_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #a0a0b0;
                border: none;
                font-size: 14px;
                padding: 4px 12px;
                border-radius: 6px;
            }
            QPushButton:hover { background: #2d2d44; color: #ffffff; border-radius: 6px; }
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

    def create_btn(self, text):
        btn = QPushButton(text)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #a0a0b0;
                border: none;
                font-size: 14px;
                padding: 4px 12px;
                border-radius: 6px;
            }
            QPushButton:hover { background: #2d2d44; color: #ffffff; border-radius: 6px; }
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
    enable_scan_button_signal = pyqtSignal(bool)
    update_folder_chart_signal = pyqtSignal(list)
    update_file_chart_signal = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(1300, 700)
        self.resize(1400, 750)

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

        content = QWidget()
        content.setStyleSheet(
            "background-color: #16162a; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(25, 10, 25, 15)
        content_layout.setSpacing(10)

        # --- ВЫБОР ПАПКИ ---
        path_layout = QHBoxLayout()
        path_layout.setSpacing(10)
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Введите путь к папке...")
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
        self.select_btn = QLabel("📂")
        self.select_btn.setFixedSize(44, 44)
        self.select_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.select_btn.setStyleSheet("""
            QLabel {
                background-color: #1f1f3a;
                border: 1px solid #2a2a4a;
                border-radius: 10px;
                color: #c0c0d0;
                font-size: 22px;
            }
            QLabel:hover { background-color: #2a2a4a; border-color: #8b6fcf; }
        """)
        self.select_btn.mousePressEvent = lambda e: self.select_folder()
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.select_btn)
        content_layout.addLayout(path_layout)

        self.scan_btn = QPushButton("🚀 Сканировать")
        self.scan_btn.setFixedHeight(48)
        self.scan_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6a4ca8, stop:1 #8b6fcf);
                border: none;
                border-radius: 10px;
                padding: 12px;
                color: #ffffff;
                font-size: 16px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7a5cb8, stop:1 #9b7fdf);
            }
            QPushButton:disabled { background-color: #2a2a44; color: #666680; }
        """)
        self.scan_btn.clicked.connect(self.start_scan)
        content_layout.addWidget(self.scan_btn)

        self.progress = QProgressBar()
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #1f1f3a;
                border: none;
                border-radius: 4px;
                height: 5px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6a4ca8, stop:1 #8b6fcf);
                border-radius: 4px;
            }
        """)
        self.progress.setFixedHeight(5)
        self.progress.setTextVisible(False)
        content_layout.addWidget(self.progress)

        # === ОСНОВНАЯ ЧАСТЬ ===
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(20)

        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)
        self.folder_chart = AnimatedPieChart("📁 Папки")
        left_panel.addWidget(self.folder_chart)
        self.file_chart = AnimatedPieChart("📄 Расширения")
        left_panel.addWidget(self.file_chart)
        bottom_layout.addLayout(left_panel, 1)

        right_panel = QVBoxLayout()
        output_title = QLabel("📋 Результаты")
        output_title.setStyleSheet("color: #8888aa; font-size: 13px; font-weight: 500;")
        right_panel.addWidget(output_title)

        text_container = QWidget()
        text_container.setStyleSheet("background-color: transparent;")
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.output.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.output.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.output.setStyleSheet("""
            QTextEdit {
                background-color: #0e0e1a;
                border: 1px solid #1f1f3a;
                border-radius: 10px;
                color: #b0b0c8;
                font-family: 'Consolas', 'Courier New';
                font-size: 13px;
                padding: 12px;
            }
        """)
        text_layout.addWidget(self.output)

        right_panel.addWidget(text_container)
        bottom_layout.addLayout(right_panel, 2)
        content_layout.addLayout(bottom_layout)

        clear_layout = QHBoxLayout()
        clear_layout.addStretch()
        self.clear_btn = QPushButton("🗑️ Очистить")
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
        clear_layout.addWidget(self.clear_btn)
        content_layout.addLayout(clear_layout)

        main_layout.addWidget(content)

        self.update_progress_signal.connect(self.progress.setValue)
        self.append_output_signal.connect(self.output.append)
        self.enable_scan_button_signal.connect(self.scan_btn.setEnabled)
        self.update_folder_chart_signal.connect(self.folder_chart.set_data)
        self.update_file_chart_signal.connect(self.file_chart.set_data)

        # === Проверка размера report.txt ===
        self.check_report_size()

    def check_report_size(self):
        report_path = "report.txt"
        if not os.path.exists(report_path):
            return
        try:
            size = os.path.getsize(report_path)
            if size > 100 * 1024:
                size_str = format_size(size)
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Предупреждение")
                msg_box.setIcon(QMessageBox.Icon.Warning)
                msg_box.setText(f"Файл report.txt достиг размера {size_str}.")
                msg_box.setInformativeText("Рекомендуется очистить его для экономии места и удобства.")
                clear_btn = msg_box.addButton("Очистить", QMessageBox.ButtonRole.ActionRole)
                cancel_btn = msg_box.addButton("Позже", QMessageBox.ButtonRole.RejectRole)
                msg_box.setDefaultButton(cancel_btn)
                msg_box.exec()
                if msg_box.clickedButton() == clear_btn:
                    with open(report_path, "w", encoding="utf-8") as f:
                        f.write("")
                    self.output.append("🧹 Файл report.txt был очищен.\n")
        except Exception:
            pass

    def clear_output(self):
        self.output.clear()
        self.folder_chart.set_data([])
        self.file_chart.set_data([])
        self.progress.setValue(0)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if folder:
            self.path_input.setText(folder)

    def start_scan(self):
        path = self.path_input.text().strip()
        if not path or not os.path.isdir(path):
            self.output.append("❌ Ошибка: укажите существующую папку!\n")
            return
        self.scan_btn.setEnabled(False)
        self.select_btn.setEnabled(False)
        self.progress.setValue(0)
        self.output.clear()
        self.folder_chart.set_data([])
        self.file_chart.set_data([])
        thread = threading.Thread(target=self.scan_folder, args=(path,))
        thread.daemon = True
        thread.start()

    def scan_folder(self, path):
        start_time = time.time()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            self.append_output_signal.emit("⏳ Сканирование...\n")

            total_size = 0
            total_files = 0
            total_folders = 0
            has_files = False
            sf = []  # (size, path)
            folder_sizes = {}
            extension_sizes = {}
            processed = 0
            system_folders_skipped = False
            is_drive = is_drive_root(path)

            def scan_recursive(root_path):
                nonlocal total_size, total_files, total_folders, has_files, processed, system_folders_skipped
                folder_name = os.path.basename(root_path)
                if folder_name in SYSTEM_FOLDERS:
                    system_folders_skipped = True
                    return
                total_folders += 1
                processed += 1
                if processed % 50 == 0:
                    self.update_progress_signal.emit(min(processed, 99))

                folder_size = 0
                try:
                    with os.scandir(root_path) as entries:
                        for entry in entries:
                            try:
                                if entry.is_file():
                                    size = entry.stat().st_size
                                    total_size += size
                                    folder_size += size
                                    total_files += 1
                                    has_files = True

                                    # Расширение
                                    ext = os.path.splitext(entry.name)[1].lower() or "без расширения"
                                    extension_sizes[ext] = extension_sizes.get(ext, 0) + size

                                    # Сохраняем для топ-5 (без форматирования)
                                    sf.append((size, entry.path))
                                elif entry.is_dir():
                                    sub_name = os.path.basename(entry.path)
                                    if sub_name not in SYSTEM_FOLDERS:
                                        scan_recursive(entry.path)
                                    else:
                                        system_folders_skipped = True
                            except OSError:
                                continue
                except (PermissionError, OSError):
                    return

                if folder_size > 0:
                    folder_name = os.path.basename(root_path) or root_path
                    folder_sizes[folder_name] = folder_sizes.get(folder_name, 0) + folder_size

            free_space_text = None
            total_space_text = None
            if is_drive:
                try:
                    disk_usage = shutil.disk_usage(path)
                    free_space_text = format_size(disk_usage.free)
                    total_space_text = format_size(disk_usage.total)
                except:
                    pass

            scan_recursive(path)

            if not has_files:
                self.append_output_signal.emit("📭 Нет доступных файлов\n")
                self.update_progress_signal.emit(100)
                return

            self.update_progress_signal.emit(100)

            # Форматируем общий размер
            print_text = format_size(total_size)

            # Сортируем и берём топ-5
            sf.sort(key=lambda x: x[0], reverse=True)
            t5 = [f"{os.path.basename(path)} - {format_size(size)}" for size, path in sf[:5]]

            # Подготовка данных для диаграмм
            folder_chart_data = []
            for name, size in sorted(folder_sizes.items(), key=lambda x: x[1], reverse=True)[:15]:
                folder_chart_data.append((name, size / (1024 * 1024)))
            self.update_folder_chart_signal.emit(folder_chart_data)

            file_chart_data = []
            for ext, size in sorted(extension_sizes.items(), key=lambda x: x[1], reverse=True)[:15]:
                file_chart_data.append((ext, size / (1024 * 1024)))
            self.update_file_chart_signal.emit(file_chart_data)

            # Вывод
            self.append_output_signal.emit("──────────────────────────────────────────────────\n")
            if is_drive and total_space_text and free_space_text:
                self.append_output_signal.emit(f"💾 Общий размер диска: {total_space_text}")
                self.append_output_signal.emit(f"📊 Свободно места: {free_space_text}")
            self.append_output_signal.emit(f"📁 Папок: {total_folders}")
            self.append_output_signal.emit(f"✅ Файлов: {total_files}")
            self.append_output_signal.emit(f"✅ Размер просканированных файлов: {print_text}")
            if is_drive and system_folders_skipped:
                self.append_output_signal.emit("⚠️ СИСТЕМНЫЕ ПАПКИ ПРОПУЩЕНЫ")
                self.append_output_signal.emit("   Windows, Program Files, $Recycle.Bin и др.")
                self.append_output_signal.emit("   Их размер не учтён.")
            self.append_output_signal.emit("\n📌 Топ-5 файлов:\n")
            for i, line in enumerate(t5, 1):
                self.append_output_signal.emit(f"  {i}. {line}")

            # Сохранение в report.txt
            try:
                with open("report.txt", "a", encoding="cp1251", errors="ignore") as f:
                    f.write("=== Сканирование папки ===\n")
                    f.write(f"Путь: {path}\n")
                    f.write(f"Дата: {now}\n")
                    if is_drive and total_space_text and free_space_text:
                        f.write(f"Общий размер диска: {total_space_text}\n")
                        f.write(f"Свободно места: {free_space_text}\n")
                    f.write(f"Папок: {total_folders}\n")
                    f.write(f"Файлов: {total_files}\n")
                    f.write(f"Размер: {print_text}\n")
                    if is_drive and system_folders_skipped:
                        f.write("⚠️ СИСТЕМНЫЕ ПАПКИ ПРОПУЩЕНЫ\n")
                    f.write("Топ-5:\n")
                    for i, line in enumerate(t5, 1):
                        f.write(f"{i}. {line}\n")
                    f.write("-" * 40 + "\n")
                self.append_output_signal.emit("\n💾 Сохранено в report.txt\n")
            except Exception as e:
                self.append_output_signal.emit(f"❌ Ошибка сохранения: {e}\n")

            elapsed = time.time() - start_time
            if elapsed < 1:
                self.append_output_signal.emit(f"⏱️ Время сканирования: {elapsed * 1000:.0f} мс")
            else:
                self.append_output_signal.emit(f"⏱️ Время сканирования: {elapsed:.2f} сек")

        except Exception as e:
            self.append_output_signal.emit(f"❌ Ошибка: {e}\n")
        finally:
            self.update_progress_signal.emit(100)
            self.enable_scan_button_signal.emit(True)
            self.select_btn.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ScannerApp()
    window.show()
    sys.exit(app.exec())
