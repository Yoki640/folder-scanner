# 📁 Сканер папок (оптимизированная версия)

Мощный сканер папок и дисков с анимированными круговыми диаграммами, топ‑5 файлов, поиском дубликатов и прогресс‑баром. Идеален для быстрой оценки занятого места, поиска «тяжелых» файлов и очистки диска от копий.

---

## 🚀 Возможности

- **Мгновенное сканирование** — оптимизирован под большие диски и тысячи файлов.
- **Анимированные круговые диаграммы** — наглядное распределение по папкам и расширениям.
- **Топ‑5 самых больших файлов** — двойной клик открывает файл в проводнике.
- - **Поиск дубликатов** — по имени, размеру и содержимому. Читает только начало, середину и конец файла, поэтому работает быстро.
- **Отмена сканирования** — в любой момент по кнопке или клавишей Enter.
- **Пропуск системных папок и файлов** — Windows, Program Files, pagefile.sys и другие.
- **Умное предупреждение** — если `report.txt` превышает 100 КБ, программа предупредит и предложит очистить.
- **Оптимизация под слабые ПК** — анимация отключается в покое (0% CPU).
- **Без прав администратора** — работает из любой папки, не требует установки.
- **Кроссплатформенность** — Windows, macOS и Linux.
- **Современный интерфейс** на PyQt6 — чистый дизайн, прогресс‑бар, понятные подсказки.
- **Безопасное удаление дубликатов** — файлы перемещаются в корзину через 5-секундный таймер с возможностью отмены.
- **Защита от наложения операций** — нельзя запустить скан во время удаления и наоборот.
- **Кэш хешей** — повторный поиск дубликатов проходит мгновенно.

---

## ⚠️ Антивирус

Программа может вызвать ложное срабатывание антивируса из-за того, что программа не собрана на вашем ПК и у нее нет цифровой подписи. Она ничего не удаляет, не изменяет и не отправляет в сеть — только читает имена, размеры и первые/последние байты файлов. Если антивирус ругается, добавь её в исключения — это также ускорит сканирование в 2–5 раз.

---

## ⬇️ Скачать и запустить

Готовые сборки находятся в разделе [Releases](https://github.com/Yoki640/folder-scanner/releases).  
В релизе ровно 3 файла — выберите нужный под свою ОС:

| ОС | Файл | Как запустить | Важное примечание |
|----|------|---------------|-------------------|
| **Windows** | `FolderScanner-windows.exe` | Двойной клик. При первом запуске Windows может запросить подтверждение («Неизвестный издатель») — это нормально. | Работает сразу, ничего дополнительно ставить не нужно. |
| **Linux** | `FolderScanner-linux.AppImage` | 1. `chmod +x FolderScanner-linux.AppImage`<br>2. `./FolderScanner-linux.AppImage` | Если не запускается, установи FUSE: `sudo apt install libfuse2`. |
| **macOS** | `FolderScanner-macos.zip` | 1. Распакуй<br>2. `xattr -d com.apple.quarantine FolderScanner.app`<br>3. Запусти двойным кликом | macOS покажет предупреждение «Приложение от неизвестного разработчика». `xattr` убирает карантинную метку. |

> ⚠️ Версия для macOS — это `.app` внутри zip-архива. Пользователям Linux — `.AppImage`, для быстрого старта используйте терминал.

---

## 🛠️ Для разработчиков

### Установка зависимостей

```bash
pip install PyQt6 send2trash
```
Опционально — ускорение поиска дубликатов в 10–20 раз:

```bash
pip install xxhash
```
## Запуск из исходного кода
```bash
python scanner.py
```
## Сборка своей версии (как в CI)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --hidden-import=xxhash --name="FolderScanner" scanner.py
```
Готовый файл появится в папке dist/.

## ❓ Частые вопросы
Почему в релизе 3 разных файла?
PyInstaller собирает нативные бинарники под каждую ОС. Файл для Windows не запустится на Linux/macOS и наоборот. Поэтому мы выкладываем отдельные сборки.

Зачем делать chmod +x?
На Unix‑системах (Linux, macOS) исполняемые файлы должны иметь флаг «исполняемый». Это стандартная процедура.

Почему macOS ругается на приложение?
Это защита Gatekeeper. Она блокирует запуск программ от «неизвестного разработчика». Поскольку ты собираешь утилиту самостоятельно и не имеешь сертификата Apple, такое предупреждение неизбежно. Убрать его можно командой xattr -d com.apple.quarantine FolderScanner.app или через правый клик → «Открыть» → «Открыть всё равно».

Почему поиск дубликатов быстрый?
Программа не читает файл целиком. Она сравнивает имя, размер и хеш только первых, средних и последних 4 МБ. Для реальных дубликатов этого достаточно, а нагрузка на диск минимальна.

Зачем нужен xxhash?
Опциональная библиотека для ускорения поиска дубликатов в 10–20 раз. Если не установлена — работает встроенный blake2b, чуть медленнее.

Зачем нужен send2trash?
Библиотека для безопасного удаления — файлы перемещаются в корзину, а не удаляются навсегда. Без неё восстановить удалённое будет невозможно.

Программа что-то удаляет?
Нет. Только читает. Ничего не удаляет, не изменяет и не отправляет в сеть.

## 📜 Лицензия
Проект распространяется под лицензией MIT.


MIT License

Copyright (c) 2026 Yoki640

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

## 🤝 Контакты и вклад
Автор: Yoki640

Хочешь помочь с проектом? Создавай Issues или Pull Request — буду рад любой помощи.