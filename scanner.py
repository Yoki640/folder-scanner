import os
from datetime import datetime
import sys
import time

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def exit_program(message=""):
    if message:
        print(message)
    print("\nНажмите Enter для выхода...")
    try:
        input()
    except:
        pass
    sys.exit(0)

print("=== Сканирование папки ===")

try:
    while True:
        path = input("Введите путь к папке: ").strip()

        if not path:
            print("Путь не может быть пустым!")
            continue

        if not os.path.isdir(path):
            print("Введите корректный путь к папке!")
            continue

        print("\n⏳ Подсчёт папок...")

        # --- 1. Собираем все папки ---
        all_folders = []
        try:
            total_folders = 0
            for _, _, _ in os.walk(path):
                total_folders += 1

            processed = 0
            for root, dirs, files in os.walk(path):
                all_folders.append(root)
                processed += 1

                percent = (processed / total_folders) * 100
                bar_len = 30
                filled = int(bar_len * processed // total_folders)
                bar = '█' * filled + '░' * (bar_len - filled)
                print(f"\r[{bar}] {percent:.1f}%   ", end='', flush=True)

            print(f"\n📁 Найдено папок: {total_folders}")

        except PermissionError:
            print("❌ Ошибка: нет доступа к некоторым папкам.")
            exit_program()
        except Exception as e:
            print(f"❌ Ошибка при подсчёте папок: {e}")
            exit_program()

        print("🔍 Сканирование файлов...")

        # --- 2. Определяем мощность ПК ---
        cpu_cores = os.cpu_count() or 1
        if cpu_cores <= 2:
            use_multithreading = False
            print(f"💻 Слабый ПК ({cpu_cores} ядра) — однопоточный режим")
        else:
            use_multithreading = True
            max_workers = min(cpu_cores, 4)
            print(f"⚡ Мощный ПК ({cpu_cores} ядер) — многопоточный режим ({max_workers} потоков)")

        has_files = False
        total_size = 0
        total_files = 0
        sf = []
        processed_folders = 0
        print_text = ""

        def process_folder(root):
            local_size = 0
            local_files = 0
            local_has_files = False
            local_sf = []

            try:
                files = os.listdir(root)
            except PermissionError:
                return local_size, local_files, local_has_files, local_sf

            local_files += len(files)
            for item in files:
                full_path = os.path.join(root, item)
                try:
                    getsize = os.path.getsize(full_path)
                except OSError:
                    continue

                if os.path.isfile(full_path):
                    local_size += getsize
                    local_has_files = True

                    if getsize >= (1024 * 1024 * 1024):
                        sf_text = f"{getsize / (1024 * 1024 * 1024):.2f} ГБ"
                    elif getsize >= (1024 * 1024):
                        sf_text = f"{getsize / (1024 * 1024):.2f} МБ"
                    elif getsize >= 1024:
                        sf_text = f"{getsize / 1024:.2f} КБ"
                    else:
                        sf_text = f"{getsize} Б"

                    local_sf.append((getsize, f"{full_path} - {sf_text}"))

            return local_size, local_files, local_has_files, local_sf

        try:
            if use_multithreading:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(process_folder, root) for root in all_folders]

                    for future in futures:
                        processed_folders += 1
                        percent = (processed_folders / total_folders) * 100
                        bar_len = 30
                        filled = int(bar_len * processed_folders // total_folders)
                        bar = '█' * filled + '░' * (bar_len - filled)
                        print(f"\r[{bar}] {percent:.1f}%   ", end='', flush=True)

                        local_size, local_files, local_has_files, local_sf = future.result()
                        total_size += local_size
                        total_files += local_files
                        has_files = has_files or local_has_files
                        sf.extend(local_sf)
            else:
                for root in all_folders:
                    processed_folders += 1
                    percent = (processed_folders / total_folders) * 100
                    bar_len = 30
                    filled = int(bar_len * processed_folders // total_folders)
                    bar = '█' * filled + '░' * (bar_len - filled)
                    print(f"\r[{bar}] {percent:.1f}%   ", end='', flush=True)

                    local_size, local_files, local_has_files, local_sf = process_folder(root)
                    total_size += local_size
                    total_files += local_files
                    has_files = has_files or local_has_files
                    sf.extend(local_sf)

            print()

            # --- Форматируем общий размер ---
            if total_size >= (1024 * 1024 * 1024):
                print_text = f"{total_size / (1024 * 1024 * 1024):.2f} ГБ"
            elif total_size >= (1024 * 1024):
                print_text = f"{total_size / (1024 * 1024):.2f} МБ"
            elif total_size >= 1024:
                print_text = f"{total_size / 1024:.2f} КБ"
            else:
                print_text = f"{total_size} Б"

            # --- Сортируем и берём топ-5 ---
            sf.sort(key=lambda x: x[0], reverse=True)
            t5 = [item[1] for item in sf[:5]]

            # --- Вывод результатов ---
            if not has_files:
                print("В папке нет файлов (только папки или пусто).")
            else:
                print(f"✅ Общее количество файлов: {total_files}")
                print(f"✅ Общий размер: {print_text}")
                print("\n📌 Топ-5 самых больших файлов:")
                for i, file_info in enumerate(t5, start=1):
                    print(f"  {i}. {file_info}")

                # --- Сохраняем в файл ---
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
                    exit_program()

                except PermissionError:
                    exit_program("❌ Ошибка: нет прав на запись в report.txt")
                except Exception as e:
                    exit_program(f"❌ Ошибка при сохранении: {e}")

        except KeyboardInterrupt:
            exit_program("\n❌ Сканирование прервано пользователем.")
        except Exception as e:
            exit_program(f"❌ Произошла ошибка: {e}")

        break

except KeyboardInterrupt:
    exit_program("\n❌ Программа остановлена пользователем.")
except Exception as e:
    exit_program(f"❌ Критическая ошибка: {e}")
