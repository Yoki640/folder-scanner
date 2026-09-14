# 📁 Сканер папок (оптимизированная версия)

Мощный сканер папок и дисков с анимированными круговыми диаграммами, топ‑5 файлов, поиском дубликатов и прогресс‑баром. Идеален для быстрой оценки занятого места, поиска «тяжелых» файлов и очистки диска от копий.

---

## 🚀 Возможности

- **Мгновенное сканирование** — оптимизирован под большие диски и сотни тысяч файлов.
- **Быстрый режим (Windows)** — с правами администратора читает NTFS MFT напрямую: обход каталогов в десятки раз быстрее.
- **Анимированные круговые диаграммы** — наглядное распределение по папкам и расширениям.
- **Топ‑5 самых больших файлов** — двойной клик открывает файл в проводнике.
- **Поиск дубликатов** — по имени, размеру и содержимому. Читает начало, середину и конец файла, поэтому работает быстро.
- **Отмена сканирования** — в любой момент по кнопке или клавише Enter.
- **Пропуск системных папок и файлов** — Windows, Program Files, pagefile.sys и другие.
- **Без прав администратора** — работает из любой папки.
- **Кроссплатформенность** — Windows, macOS и Linux.
- **Современный интерфейс** — нативный десктоп на Rust + Tauri, чистый дизайн, прогресс‑бар, понятные подсказки.
- **Безопасное удаление дубликатов** — файлы перемещаются в корзину на системном уровне, ничего не удаляется навсегда.
- **Защита от наложения операций** — нельзя запустить скан во время удаления и наоборот.
- **Кэш хешей** — повторный поиск дубликатов проходит мгновенно.

---

## ⚠️ Антивирус

Программа может вызвать ложное срабатывание антивируса из-за того, что у сборок нет цифровой подписи. Она ничего не удаляет, не изменяет и не отправляет в сеть — только читает имена, размеры и часть содержимого файлов. Если антивирус ругается, добавь её в исключения — это также ускорит сканирование в 2–5 раз.

---

## ⬇️ Скачать и запустить

Готовые сборки находятся в разделе [Releases](https://github.com/Yoki640/folder-scanner/releases).  
В релизе есть файлы под каждую ОС — выберите нужный:

| ОС | Файл | Как запустить | Важное примечание |
|----|------|---------------|-------------------|
| **Windows** | `FolderScanner_0.1.0_x64-setup.exe` | Двойной клик, установка через мастер. | Самый надёжный вариант — установщик NSIS. Есть и `.msi`. |
| **Linux** | `FolderScanner_0.1.0_x64.AppImage` | 1. `chmod +x FolderScanner_0.1.0_x64.AppImage`<br>2. `./FolderScanner_0.1.0_x64.AppImage` | Если не запускается, установи FUSE: `sudo apt install libfuse2`. |
| **macOS** | `FolderScanner-macos.zip` | 1. Распакуй<br>2. `xattr -d com.apple.quarantine FolderScanner.app`<br>3. Запусти двойным кликом | macOS покажет предупреждение «Приложение от неизвестного разработчика». `xattr` убирает карантинную метку. |

> ⚠️ Версия для macOS — это `.app` внутри zip-архива. Пользователям Linux — `.AppImage`, для быстрого старта используйте терминал.

---

## 🛠️ Для разработчиков

### Требования

Установи [Rust](https://rustup.rs/) и Node.js. Для Linux понадобятся системные библиотеки WebKit (webkit2gtk-4.1), для Windows — ничего дополнительно.

### Установка зависимостей

```bash
npm ci
```

### Запуск из исходного кода (режим разработки)

```bash
npm run tauri dev
```

### Сборка своей версии (как в CI)

```bash
npm run tauri build
```

Windows: `npm run tauri build -- --bundles nsis,msi`  
Linux: `npm run tauri build -- --bundles appimage,deb`  
macOS: `npm run tauri build -- --bundles app` (соберёт `.app`, для релиза CI сам пакует его в zip)

Готовые файлы появятся в `src-tauri/target/release/bundle/`.

---

## ❓ Частые вопросы

**Почему в релизе разные файлы для каждой ОС?**
Tauri компилирует нативные бинарники под каждую ОС. Файл для Windows не запустится на Linux/macOS и наоборот. Поэтому мы выкладываем отдельные сборки.

**Зачем делать chmod +x?**
На Unix‑системах (Linux, macOS) исполняемые файлы должны иметь флаг «исполняемый». Это стандартная процедура.

**Почему macOS ругается на приложение?**
Это защита Gatekeeper. Она блокирует запуск программ от «неизвестного разработчика». Поскольку у проекта нет сертификата Apple, такое предупреждение неизбежно. Убрать его можно командой `xattr -d com.apple.quarantine FolderScanner.app` или через правый клик → «Открыть» → «Открыть всё равно».

**Почему поиск дубликатов быстрый?**
Программа не читает файл целиком. Она сравнивает имя, размер и хеш (blake3) только начала, середины и конца файла. Для реальных дубликатов этого достаточно, а нагрузка на диск минимальна.

**Зачем нужны права администратора?**
Без них программа обходит каталоги обычным способом. С правами администратора на Windows она открывает `\\.\C:` и читает таблицу NTFS MFT напрямую — сканирование списков файлов занимает секунды даже на больших дисках.

**Программа что-то удаляет?**
Нет. Только читает. Удаление дубликатов — только по вашей команде, и файлы попадают в корзину, а не стираются навсегда.

**Что внутри?**
Backend на Rust (Tauri 2, Windows/Linux/macOS), интерфейс на TypeScript. Всё упаковывается в один исполняемый файл, ставить ничего дополнительно не нужно.

---

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