import os
from datetime import datetime

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

print("=== Сканирование папки ===")

while True:
    path = input("Введите путь к папке: ").strip()

    if not path:
        print("Путь не может быть пустым!")
        continue

    if not os.path.isdir(path):
        print("Введите корректный путь к папке!")
        continue

    print("\n⏳ Подсчёт папок для прогресса...")

    total_folders = 0
    try:
        for _, _, _ in os.walk(path):
            total_folders += 1
    except PermissionError:
        print("❌ Ошибка: нет доступа к некоторым папкам.")
        continue

    print(f"📁 Найдено папок: {total_folders}")
    print("🔍 Начинаю сканирование...")

    has_files = False
    total_size = 0
    total_files = 0
    sf = []
    processed_folders = 0
    print_text = ""

    try:
        for root, dirs, files in os.walk(path):
            processed_folders += 1

            # Показываем прогресс только если есть что обрабатывать
            percent = (processed_folders / total_folders) * 100
            bar_len = 30
            filled = int(bar_len * processed_folders // total_folders)
            bar = '█' * filled + '░' * (bar_len - filled)
            print(f"\r[{bar}] {percent:.1f}%   ", end='', flush=True)

            total_files += len(files)
            for item in files:
                full_path = os.path.join(root, item)

                try:
                    getsize = os.path.getsize(full_path)
                except OSError:
                    continue

                if os.path.isfile(full_path):
                    total_size += getsize
                    has_files = True

                if getsize >= (1024 * 1024):
                    sf_text = f"{getsize / (1024 * 1024):.2f} МБ"
                elif getsize >= 1024:
                    sf_text = f"{getsize / 1024:.2f} КБ"
                else:
                    sf_text = f"{getsize} Б"

                sf.append((getsize, f"{full_path} - {sf_text}"))

        print()

        if total_size >= (1024 * 1024):
            print_text = f"{total_size / (1024 * 1024):.2f} МБ"
        elif total_size >= 1024:
            print_text = f"{total_size / 1024:.2f} КБ"
        else:
            print_text = f"{total_size} Б"

        sf.sort(key=lambda x: x[0], reverse=True)
        t5 = [item[1] for item in sf[:5]]

        if not has_files:
            print("В папке нет файлов (только папки или пусто).")
        else:
            print(f"✅ Общее количество файлов: {total_files}")
            print(f"✅ Общий размер: {print_text}")
            print("\n📌 Топ-5 самых больших файлов:")
            for i, file_info in enumerate(t5, start=1):
                print(f"  {i}. {file_info}")

            try:
                with open("report.txt", "a", encoding="cp1251") as f:
                    f.write("=== Сканирование папки ===\n")
                    f.write(f"Путь: {path}\n")
                    f.write(f"Дата сканирования: {now}\n\n")
                    f.write(f"Общее количество файлов: {total_files}\n")
                    f.write(f"Общий размер: {print_text}\n\n")
                    f.write("Топ-5 самых больших файлов:\n")
                    for i, file_info in enumerate(t5, start=1):
                        f.write(f"{i}. {file_info}\n")
                    f.write("\n" + "-" * 40 + "\n\n")
                print("\n✅ Сохранено в report.txt")
            except PermissionError:
                print("\n❌ Ошибка: нет прав на запись в report.txt")
            except Exception as e:
                print(f"\n❌ Ошибка при сохранении: {e}")

    except PermissionError:
        print("\n❌ Ошибка: нет доступа к некоторым папкам.")
    except KeyboardInterrupt:
        print("\n❌ Сканирование прервано пользователем.")
    except Exception as e:
        print(f"\n❌ Произошла ошибка: {e}")

    break