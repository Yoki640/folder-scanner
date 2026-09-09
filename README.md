# 📁 Сканер папок (оптимизированная версия)


Мощный сканер папок и дисков с анимированными круговыми диаграммами, топ‑5 файлов и прогресс‑баром.

## Возможности

🚀 Мгновенное сканирование (оптимизирован под большие диски)  
📊 Анимированные круговые диаграммы (папки и расширения)  
📋 Топ‑5 самых больших файлов  
💾 Отчёт сохраняется в `report.txt`  
🔔 Предупреждение, если `report.txt` превышает 100 КБ (с возможностью очистки)  
⚙️ Работает без прав администратора  
🖥️ Красивый современный интерфейс на PyQt6  

---

## Скачать и запустить

Готовые сборки находятся в разделе [Releases](https://github.com/Yoki640/folder-scanner/releases).  
В релизе ровно 3 файла — выберите нужный под свою ОС:

| ОС | Файл для скачивания | Как запустить |
|----|---------------------|---------------|
| **Windows** | `FolderScanner-windows.exe` | Скачайте и запустите двойным кликом. При первом запуске Windows может запросить подтверждение («Неизвестный издатель») — это нормально. |
| **Linux** | `FolderScanner-linux` | 1. Сделайте исполняемым: `chmod +x FolderScanner-linux`<br>2. Запустите: `./FolderScanner-linux`<br>Если интерфейс не появляется, попробуйте установить базовые библиотеки: `sudo apt install libgtk-3-0` (или аналог для вашего дистрибутива). |
| **macOS** | `FolderScanner-macos` | 1. Сделайте исполняемым: `chmod +x FolderScanner-macos`<br>2. Запустите из терминала: `./FolderScanner-macos`<br>**Важно:** macOS покажет предупреждение «Приложение от неизвестного разработчика». В «Системных настройках → Защита и безопасность» нажмите «Открыть всё равно». Это ожидаемо для утилит, собранных через PyInstaller. |

> ⚠️ Примечание: версия для macOS и Linux — это исполняемые файлы (не `.app` и не `.deb`). Для быстрого старта используйте терминал.

---

## Для разработчиков

Если вы хотите собрать проект самостоятельно или внести изменения:

### Установка зависимостей

```bash
pip install PyQt6
```
Запуск из исходного кода

```bash
python scanner.py
```
Сборка своей версии (как в CI)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name="FolderScanner" scanner.py
```
После сборки готовый файл появится в папке dist/.

Скриншоты

<img width="1393" height="742" alt="image" src="https://github.com/user-attachments/assets/5067acf6-1f0d-4bec-acf8-679d71425543" />



Зависимости
Все зависимости уже встроены в бинарные файлы (благодаря PyInstaller --onefile). Отдельный Python не требуется для запуска готовых сборок.

## 🤝 Контакты и вклад
Автор: Yoki640
Хочешь помочь с проектом? Создавай Issues или Pull Request — буду рад любой помощи.

## Лицензия
Проект распространяется под лицензией MIT.

## MIT License

Copyright (c) 2024 Yoki640

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
