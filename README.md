# 📁 Сканер папок

Кроссплатформенный анализатор дискового пространства с поиском дубликатов на PyQt6.

## Возможности

- Быстрое многопоточное сканирование папок и целых дисков
- Круговые диаграммы распределения по папкам и расширениям
- Топ-5 самых больших файлов — двойной клик открывает в проводнике
- Поиск дубликатов по имени, размеру и содержимому
- Отмена сканирования в любой момент (Enter или кнопка)
- Пропуск системных папок и служебных файлов
- Тёмная тема с плавными анимациями

## Требования

- Python 3.9+
- PyQt6

## Установка

```bash
pip install PyQt6
```
Опционально — ускорение поиска дубликатов в 10–20 раз:

```bash
pip install xxhash
```
Запуск
```bash
python scanner.py
```
# Использование
Введи путь к папке или выбери через кнопку 📂

Нажми Enter или «🚀 Сканировать»

Во время сканирования кнопка превращается в «🛑 Отменить»

Двойной клик по файлу в топ-5 открывает его в проводнике

Переключись на вкладку «🔍 Дубликаты» и нажми «Найти дубликаты»

Как работает поиск дубликатов
Файл считается дубликатом, если у него совпадают имя, размер и содержимое. Проверка идёт в несколько стадий:

Группировка по имени и размеру

Хеширование первых 4 МБ и последних 4 МБ (для больших файлов)

Финальная сверка по хешу

Благодаря чтению только начала и конца файла, поиск работает быстро даже на больших дисках и не нагружает систему.

# Поддерживаемые платформы
Windows 10/11

macOS

Linux

Для каждой ОС свой список пропускаемых системных папок и свой способ открытия файлового менеджера.

# Лицензия
Проект распространяется под лицензией MIT.

## MIT License

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
