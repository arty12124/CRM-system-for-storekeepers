import sqlite3
import requests
import json
import os
import threading
import customtkinter as ctk
from tkinter import messagebox, ttk, simpledialog  
import pygame
import webbrowser
import time
import platform
import subprocess
from datetime import datetime, timedelta
import queue
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import sys

# Функция для получения путей к ресурсам
def resource_path(relative_path):
    """Получение абсолютного пути к ресурсу, работает как в разработке, так и в .exe."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# Путь к файлу конфигурации
CONFIG_FILE = resource_path("database/config.json")

# Функция для загрузки конфигурации из JSON
def load_config():
    """Загружает конфигурацию из JSON-файла или возвращает значения по умолчанию."""
    default_config = {
        "api_keys": {
            "wildberries": "eyJhbGciOiJFUzI1NiIsImtpZCI6IjIwMjUwNDE3djEiLCJ0eXAiOiJKV1QifQ.eyJlbnQiOjEsImV4cCI6MTc2MTI3MTA4MywiaWQiOiIwMTk2NjgxNy01YjUxLTc5YTItOTk4ZS1mNjcyNTA4ZjcyMmUiLCJpaWQiOjEwNDI1MjM5MCwib2lkIjoyOTgzMCwicyI6NzkzNCwic2lkIjoiZjc0Y2ExYmUtYzVjMi01OTNjLWEzZGItM2M2ZGI3YjE0MGJiIiwidCI6ZmFsc2UsInVuZCI6MTA0MjUyMzkwfQ.x-N67msygbk6lD9cvN4ugFanH1kL_McIOe8iREzIz6cXofNVh6bJsskdqshjzoMGMHCTycuh06m1SfCMO5bkXw",
            "ozon": "e5d79470-d4db-4d99-bc5d-9701d083ff19",
        },
        "ozon_client_id": "35457",
        "config": {
            "enable_notification_sound": True,
            "max_retries": 3,
            "retry_backoff_factor": 2,
            "default_image": resource_path("assets/default_image.png")
        },
        "avito": {
            "debug_port": 9222,
            "avito_orders_url": "https://www.avito.ru/orders?source=sidebar",
            "chrome_start_timeout": 10,
            "cookies_file": resource_path("database/avito_cookies.json")
        }
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                # Обновляем пути, которые зависят от resource_path
                config["config"]["default_image"] = resource_path("assets/default_image.png")
                config["avito"]["cookies_file"] = resource_path("database/avito_cookies.json")
                return config
    except Exception as e:
        print(f"Ошибка загрузки конфигурации: {e}")
    return default_config

# Функция для сохранения конфигурации в JSON
def save_config(config):
    """Сохраняет конфигурацию в JSON-файл."""
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Ошибка сохранения конфигурации: {e}")

# Загружаем конфигурацию при старте
CONFIG_DATA = load_config()

# Константы из конфигурации
API_KEYS = CONFIG_DATA["api_keys"]
OZON_CLIENT_ID = CONFIG_DATA["ozon_client_id"]
CONFIG = CONFIG_DATA["config"]
STATUSES = ["Новый", "Готов"]
SOURCES = ["Wildberries", "Ozon", "Avito"]
TABLE_COLUMNS = ("Check", "ID", "Name", "Quantity", "Price", "Source", "Status", "Comment", "Date", "Link")
TABLE_HEADINGS = ("", "ID", "Название", "Количество", "Цена", "Источник", "Статус", "Комментарий", "Дата", "Ссылка")
MAX_LOG_LINES = 100
DEBUG_PORT = CONFIG_DATA["avito"]["debug_port"]
AVITO_ORDERS_URL = CONFIG_DATA["avito"]["avito_orders_url"]
CHROME_START_TIMEOUT = CONFIG_DATA["avito"]["chrome_start_timeout"]
COOKIES_FILE = CONFIG_DATA["avito"]["cookies_file"]

class MarketplaceCRM(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CRM для кладовщиков")
        self.geometry("1200x700")
        self.minsize(1000, 600)
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # Очередь для передачи сообщений лога из фонового потока
        self.log_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        self.log_lines = []  # Список для хранения строк лога
        self.auto_fetch_enabled = False  # Флаг для автообновления, изначально выключено

        os.makedirs(resource_path("database"), exist_ok=True)
        self.init_database()
        self.init_notification_sound()
        self.setup_ui()
        self.load_orders()
        self.start_auto_fetch()  # Запускаем автоматическое обновление (не сработает, так как auto_fetch_enabled = False)
        self.check_queues()  # Запускаем проверку очередей

    def check_queues(self):
        """Проверка очередей для обновления UI в главном потоке."""
        try:
            while True:
                log_msg = self.log_queue.get_nowait()
                self._log_message_ui(log_msg)
        except queue.Empty:
            pass

        try:
            while True:
                ui_action = self.ui_queue.get_nowait()
                ui_action()
        except queue.Empty:
            pass

        self.after(100, self.check_queues)  # Проверяем очереди каждые 100 мс

    def init_notification_sound(self):
        """Инициализация звука уведомления."""
        self.notification_sound = None
        if CONFIG["enable_notification_sound"]:
            if platform.system() == "Emscripten":
                self.log_message("Звук уведомлений отключён: pygame.mixer не поддерживается в браузере.")
                return
            try:
                pygame.mixer.init()
                sound_file = resource_path("assets/notification.wav")
                if os.path.exists(sound_file):
                    self.notification_sound = pygame.mixer.Sound(sound_file)
                else:
                    messagebox.showwarning("Предупреждение", f"Файл {sound_file} не найден.")
            except Exception as e:
                messagebox.showwarning("Предупреждение", f"Не удалось инициализировать звук: {e}")

    def init_database(self):
        """Инициализация базы данных SQLite."""
        with sqlite3.connect(resource_path("database/orders.db")) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    external_id TEXT PRIMARY KEY,
                    product_image TEXT,
                    product_name TEXT,
                    product_link TEXT,
                    quantity INTEGER,
                    price REAL,
                    source TEXT,
                    status TEXT,
                    comment TEXT,
                    created_at TEXT
                )
            ''')
            conn.commit()

    def migrate_database(self):
        """Миграция структуры базы данных при необходимости."""
        with sqlite3.connect(resource_path("database/orders.db")) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
                if cursor.fetchone():
                    cursor.execute("ALTER TABLE orders RENAME TO orders_old")
                    self.init_database()
                    cursor.execute('''
                        INSERT INTO orders (external_id, product_image, product_name, product_link, quantity, price, source, status, comment, created_at)
                        SELECT external_id, product_image, product_name, product_link, quantity, price, source, status, comment, created_at
                        FROM orders_old
                    ''')
                    cursor.execute("DROP TABLE orders_old")
                    conn.commit()
            except Exception as e:
                self.log_message(f"Ошибка миграции базы данных: {e}")

    def setup_ui(self):
        """Настройка пользовательского интерфейса с вкладками."""
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Создаём вкладки
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        self.tabview.add("Заказы")
        self.tabview.add("Настройки")

        # Вкладка "Заказы"
        orders_tab = self.tabview.tab("Заказы")
        orders_tab.grid_rowconfigure(4, weight=1)
        orders_tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(orders_tab, text="Заказы с маркетплейсов", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, pady=(0, 20), sticky="w")

        filter_frame = ctk.CTkFrame(orders_tab)
        filter_frame.grid(row=1, column=0, pady=(0, 20), sticky="ew")
        self.status_filter = ctk.CTkComboBox(filter_frame, values=["Все статусы"] + STATUSES)
        self.status_filter.set("Новый")
        self.source_filter = ctk.CTkComboBox(filter_frame, values=["Все источники"] + SOURCES)
        self.source_filter.set("Все источники")
        filter_button = ctk.CTkButton(filter_frame, text="Фильтровать", command=self.load_orders)

        filter_frame.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkLabel(filter_frame, text="Статус:").grid(row=0, column=0, padx=5, sticky="w")
        self.status_filter.grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkLabel(filter_frame, text="Источник:").grid(row=0, column=2, padx=5, sticky="w")
        self.source_filter.grid(row=0, column=3, padx=5, sticky="ew")
        filter_button.grid(row=0, column=4, padx=5)

        button_frame = ctk.CTkFrame(orders_tab)
        button_frame.grid(row=2, column=0, pady=(0, 20), sticky="ew")
        self.fetch_button = ctk.CTkButton(button_frame, text="Получить заказы", command=self.fetch_orders, fg_color="#2E7D32", hover_color="#1B5E20")
        clear_db_button = ctk.CTkButton(button_frame, text="Очистить базу", command=self.clear_database)
        complete_button = ctk.CTkButton(button_frame, text="Выполнено", command=self.complete_selected_orders)
        self.auto_fetch_switch = ctk.CTkSwitch(
            button_frame,
            text="Автообновление",
            command=self.toggle_auto_fetch,
            onvalue=1,
            offvalue=0,
            fg_color="gray",
            progress_color="green",
            switch_width=40,
            switch_height=20
        )

        button_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.fetch_button.grid(row=0, column=0, padx=5)
        clear_db_button.grid(row=0, column=1, padx=5)
        complete_button.grid(row=0, column=2, padx=5)
        self.auto_fetch_switch.grid(row=0, column=3, padx=5)

        table_frame = ctk.CTkFrame(orders_tab)
        table_frame.grid(row=4, column=0, sticky="nsew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        style.configure("Treeview", foreground="black")
        style.configure("Black.Treeview", foreground="black")

        self.table = ttk.Treeview(table_frame, columns=TABLE_COLUMNS, show="headings", style="Treeview")
        for col, head in zip(TABLE_COLUMNS, TABLE_HEADINGS):
            self.table.heading(col, text=head)
        self.table.column("Check", width=30)
        self.table.column("ID", width=50)
        self.table.column("Name", width=200)
        self.table.column("Quantity", width=80)
        self.table.column("Price", width=80)
        self.table.column("Source", width=100)
        self.table.column("Status", width=100)
        self.table.column("Comment", width=150)
        self.table.column("Date", width=120)
        self.table.column("Link", width=100)
        self.table.grid(row=0, column=0, sticky="nsew")

        table_scroll = ctk.CTkScrollbar(table_frame, command=self.table.yview)
        table_scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=table_scroll.set)

        self.table.bind("<ButtonRelease-1>", self.on_table_click)
        self.table.bind("<Double-1>", self.on_table_double_click)
        self.table.bind("<Control-c>", self.copy_table_selection)

        log_frame = ctk.CTkFrame(orders_tab)
        log_frame.grid(row=5, column=0, pady=(20, 0), sticky="ew")
        log_frame.grid_columnconfigure(0, weight=1)
        self.log_text = ctk.CTkTextbox(log_frame, height=100, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")
        ctk.CTkButton(log_frame, text="Копировать лог", command=self.copy_log).grid(row=0, column=1, padx=(5, 10), pady=10, sticky="e")

        # Вкладка "Настройки"
        settings_tab = self.tabview.tab("Настройки")
        settings_tab.grid_rowconfigure(0, weight=1)
        settings_tab.grid_columnconfigure(0, weight=1)

        settings_frame = ctk.CTkFrame(settings_tab)
        settings_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        settings_frame.grid_columnconfigure(1, weight=1)

        # Поля ввода для констант
        ctk.CTkLabel(settings_frame, text="API-ключ Wildberries:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.wb_api_entry = ctk.CTkEntry(settings_frame, width=400)
        self.wb_api_entry.insert(0, API_KEYS["wildberries"])
        self.wb_api_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(settings_frame, text="API-ключ Ozon:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.ozon_api_entry = ctk.CTkEntry(settings_frame, width=400)
        self.ozon_api_entry.insert(0, API_KEYS["ozon"])
        self.ozon_api_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(settings_frame, text="Ozon Client ID:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.ozon_client_id_entry = ctk.CTkEntry(settings_frame, width=400)
        self.ozon_client_id_entry.insert(0, OZON_CLIENT_ID)
        self.ozon_client_id_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(settings_frame, text="Debug Port (Avito):").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.debug_port_entry = ctk.CTkEntry(settings_frame, width=400)
        self.debug_port_entry.insert(0, str(DEBUG_PORT))
        self.debug_port_entry.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(settings_frame, text="Avito Orders URL:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.avito_orders_url_entry = ctk.CTkEntry(settings_frame, width=400)
        self.avito_orders_url_entry.insert(0, AVITO_ORDERS_URL)
        self.avito_orders_url_entry.grid(row=4, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(settings_frame, text="Chrome Start Timeout (сек):").grid(row=5, column=0, padx=5, pady=5, sticky="w")
        self.chrome_timeout_entry = ctk.CTkEntry(settings_frame, width=400)
        self.chrome_timeout_entry.insert(0, str(CHROME_START_TIMEOUT))
        self.chrome_timeout_entry.grid(row=5, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(settings_frame, text="Путь к файлу cookies (Avito):").grid(row=6, column=0, padx=5, pady=5, sticky="w")
        self.cookies_file_entry = ctk.CTkEntry(settings_frame, width=400)
        self.cookies_file_entry.insert(0, COOKIES_FILE)
        self.cookies_file_entry.grid(row=6, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(settings_frame, text="Максимум попыток запроса:").grid(row=7, column=0, padx=5, pady=5, sticky="w")
        self.max_retries_entry = ctk.CTkEntry(settings_frame, width=400)
        self.max_retries_entry.insert(0, str(CONFIG["max_retries"]))
        self.max_retries_entry.grid(row=7, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(settings_frame, text="Коэффициент задержки повтора:").grid(row=8, column=0, padx=5, pady=5, sticky="w")
        self.retry_backoff_entry = ctk.CTkEntry(settings_frame, width=400)
        self.retry_backoff_entry.insert(0, str(CONFIG["retry_backoff_factor"]))
        self.retry_backoff_entry.grid(row=8, column=1, padx=5, pady=5, sticky="ew")

        self.enable_sound_var = ctk.BooleanVar(value=CONFIG["enable_notification_sound"])
        ctk.CTkCheckBox(
            settings_frame,
            text="Включить звук уведомлений",
            variable=self.enable_sound_var
        ).grid(row=9, column=0, columnspan=2, padx=5, pady=5, sticky="w")

        # Кнопка сохранения
        ctk.CTkButton(settings_frame, text="Сохранить настройки", command=self.save_settings).grid(row=10, column=0, columnspan=2, pady=20)

    def save_settings(self):
        """Сохранение настроек из полей ввода."""
        global API_KEYS, OZON_CLIENT_ID, CONFIG, DEBUG_PORT, AVITO_ORDERS_URL, CHROME_START_TIMEOUT, COOKIES_FILE
        try:
            # Обновляем конфигурацию
            CONFIG_DATA["api_keys"]["wildberries"] = self.wb_api_entry.get()
            CONFIG_DATA["api_keys"]["ozon"] = self.ozon_api_entry.get()
            CONFIG_DATA["ozon_client_id"] = self.ozon_client_id_entry.get()
            CONFIG_DATA["avito"]["debug_port"] = int(self.debug_port_entry.get())
            CONFIG_DATA["avito"]["avito_orders_url"] = self.avito_orders_url_entry.get()
            CONFIG_DATA["avito"]["chrome_start_timeout"] = int(self.chrome_timeout_entry.get())
            CONFIG_DATA["avito"]["cookies_file"] = self.cookies_file_entry.get()
            CONFIG_DATA["config"]["max_retries"] = int(self.max_retries_entry.get())
            CONFIG_DATA["config"]["retry_backoff_factor"] = float(self.retry_backoff_entry.get())
            CONFIG_DATA["config"]["enable_notification_sound"] = self.enable_sound_var.get()

            # Обновляем глобальные константы
            API_KEYS = CONFIG_DATA["api_keys"]
            OZON_CLIENT_ID = CONFIG_DATA["ozon_client_id"]
            CONFIG = CONFIG_DATA["config"]
            DEBUG_PORT = CONFIG_DATA["avito"]["debug_port"]
            AVITO_ORDERS_URL = CONFIG_DATA["avito"]["avito_orders_url"]
            CHROME_START_TIMEOUT = CONFIG_DATA["avito"]["chrome_start_timeout"]
            COOKIES_FILE = CONFIG_DATA["avito"]["cookies_file"]

            # Сохраняем в JSON
            save_config(CONFIG_DATA)
            self.log_message("Настройки сохранены")
            messagebox.showinfo("Успех", "Настройки успешно сохранены!")
        except ValueError as e:
            self.log_message(f"Ошибка сохранения настроек: Неверный формат данных ({e})")
            messagebox.showerror("Ошибка", "Проверьте правильность введённых данных (например, числа для порта и таймаута).")
        except Exception as e:
            self.log_message(f"Ошибка сохранения настроек: {e}")
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки: {e}")

    def toggle_auto_fetch(self):
        """Переключение автообновления заказов."""
        self.auto_fetch_enabled = bool(self.auto_fetch_switch.get())
        self.log_message(f"Автообновление {'включено' if self.auto_fetch_enabled else 'выключено'}")
        if self.auto_fetch_enabled:
            self.start_auto_fetch()  # Запускаем автообновление, если оно включено

    def log_message(self, message):
        """Добавление сообщения в очередь лога для обработки в главном потоке."""
        log_line = f"{datetime.now().strftime('%H:%M:%S')} - {message}\n"
        self.log_lines.append(log_line)
        # Обрезаем список логов, если превышен лимит
        if len(self.log_lines) > MAX_LOG_LINES:
            self.log_lines = self.log_lines[-MAX_LOG_LINES:]
        self.log_queue.put(log_line)

    def _log_message_ui(self, message):
        """Обновление текстового поля лога в главном потоке."""
        self.log_text.configure(state="normal")
        # Переписываем всё содержимое лога
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", "".join(self.log_lines))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.update()

    def clear_database(self):
        """Очистка базы данных заказов."""
        if not messagebox.askyesno("Подтверждение", "Очистить базу данных? Все заказы будут удалены."):
            return
        try:
            with sqlite3.connect(resource_path("database/orders.db")) as conn:
                conn.execute("DELETE FROM orders")
                conn.commit()
            self.log_message("База данных очищена")
            self.load_orders()
        except Exception as e:
            self.log_message(f"Ошибка очистки базы данных: {e}")
            messagebox.showerror("Ошибка", "Не удалось очистить базу данных.")

    def load_orders(self):
        """Загрузка заказов из базы данных в таблицу."""
        for item in self.table.get_children():
            self.table.delete(item)

        query = "SELECT external_id, product_image, product_name, product_link, quantity, price, source, status, comment, created_at FROM orders WHERE 1=1"
        params = []
        status = self.status_filter.get()
        source = self.source_filter.get()
        if status != "Все статусы":
            query += " AND status = ?"
            params.append(status)
        if source != "Все источники":
            query += " AND source = ?"
            params.append(source)
        query += " ORDER BY created_at DESC"

        try:
            with sqlite3.connect(resource_path("database/orders.db")) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()

            for idx, row in enumerate(rows, start=1):
                external_id, image_url, name, link, qty, price, source, status, comment, date = row
                values = ("☐", idx, name, qty, price, source, status, comment or "", date, "Открыть" if link else "")
                tags = (external_id,)
                if status == "Новый":
                    tags = (external_id, "black")
                self.table.insert("", "end", values=values, tags=tags)

            self.table.tag_configure("black", foreground="black")
            self.log_message(f"Загружено {len(rows)} заказов")
        except Exception as e:
            self.log_message(f"Ошибка загрузки заказов: {e}")

    def on_table_click(self, event):
        """Обработка клика по таблице."""
        item = self.table.identify_row(event.y)
        if not item:
            return

        column = self.table.identify_column(event.x)
        if column == "#1":  # Столбец чекбокса
            values = self.table.item(item, "values")
            new_value = "☑" if values[0] == "☐" else "☐"
            self.table.item(item, values=(new_value, *values[1:]))
        elif column == "#10":  # Столбец ссылки
            external_id = self.table.item(item, "tags")[0]
            try:
                with sqlite3.connect(resource_path("database/orders.db")) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT product_link FROM orders WHERE external_id = ?", (external_id,))
                    link = cursor.fetchone()[0]
                if link:
                    webbrowser.open(link)
            except Exception as e:
                self.log_message(f"Ошибка открытия ссылки для заказа external_id {external_id}: {e}")

    def on_table_double_click(self, event):
        """Обработка двойного клика по таблице: смена статуса или редактирование комментария."""
        item = self.table.identify_row(event.y)
        if not item:
            return

        column = self.table.identify_column(event.x)
        external_id = self.table.item(item, "tags")[0]

        if column == "#7":  # Столбец "Статус"
            self.change_status(event)
        elif column == "#8":  # Столбец "Комментарий"
            self.edit_comment(item, external_id)

    def change_status(self, event):
        """Смена статуса заказа при двойном клике."""
        item = self.table.identify_row(event.y)
        if not item:
            return
        external_id = self.table.item(item, "tags")[0]
        current_status = self.table.item(item, "values")[6]
        next_status = "Готов" if current_status == "Новый" else "Новый"
        try:
            with sqlite3.connect(resource_path("database/orders.db")) as conn:
                conn.execute("UPDATE orders SET status = ? WHERE external_id = ?", (next_status, external_id))
                conn.commit()
            self.load_orders()
            self.log_message(f"Статус заказа {external_id} изменён на {next_status}")
        except Exception as e:
            self.log_message(f"Ошибка смены статуса для заказа external_id {external_id}: {e}")

    def edit_comment(self, item, external_id):
        """Редактирование комментария для заказа."""
        current_comment = self.table.item(item, "values")[7] or ""  # Текущий комментарий (индекс 7)
        new_comment = simpledialog.askstring("Редактировать комментарий", "Введите новый комментарий:", initialvalue=current_comment, parent=self)
        
        if new_comment is not None:  # Если пользователь нажал "OK" (а не "Cancel")
            try:
                with sqlite3.connect(resource_path("database/orders.db")) as conn:
                    conn.execute("UPDATE orders SET comment = ? WHERE external_id = ?", (new_comment, external_id))
                    conn.commit()
                self.log_message(f"Комментарий для заказа {external_id} изменён на: {new_comment}")
                self.load_orders()  # Обновляем таблицу
            except Exception as e:
                self.log_message(f"Ошибка сохранения комментария для заказа {external_id}: {e}")
                messagebox.showerror("Ошибка", "Не удалось сохранить комментарий.")

    def complete_selected_orders(self):
        """Обработка отмеченных заказов: смена статуса на 'Готов'."""
        changed = 0
        for item in self.table.get_children():
            values = self.table.item(item, "values")
            if values[0] == "☑":  # Если чекбокс отмечен
                external_id = self.table.item(item, "tags")[0]
                current_status = values[6]  # Столбец статуса
                if current_status == "Новый":
                    try:
                        with sqlite3.connect(resource_path("database/orders.db")) as conn:
                            conn.execute("UPDATE orders SET status = 'Готов' WHERE external_id = ?", (external_id,))
                            conn.commit()
                        changed += 1
                    except Exception as e:
                        self.log_message(f"Ошибка смены статуса для заказа external_id {external_id}: {e}")

        if changed > 0:
            self.log_message(f"Статус изменен на 'Готов' для {changed} заказов")
            self.load_orders()
        else:
            self.log_message("Не выбрано заказов для изменения статуса или статус не 'Новый'")

    def copy_table_selection(self, event):
        """Копирование выделенных строк таблицы в буфер обмена."""
        try:
            selected_items = self.table.selection()
            if not selected_items:
                self.log_message("Нет выделенных строк для копирования")
                return
            clipboard_text = ["\t".join(TABLE_HEADINGS)]
            for item in selected_items:
                values = self.table.item(item, "values")
                row = [str(value) if value is not None else "" for value in values]
                clipboard_text.append("\t".join(row))
            self.clipboard_clear()
            self.clipboard_append("\n".join(clipboard_text))
            self.log_message(f"Скопировано {len(selected_items)} строк")
        except Exception as e:
            self.log_message(f"Ошибка копирования таблицы: {e}")
            messagebox.showerror("Ошибка", "Не удалось скопировать данные.")

    def start_auto_fetch(self):
        """Запуск автоматического обновления заказов каждую минуту, если включено."""
        if not self.auto_fetch_enabled:
            return  # Не запускаем автообновление, если оно выключено
        self.fetch_orders()
        threading.Timer(60, self.start_auto_fetch).start()  # 60 секунд = 1 минута

    def fetch_orders(self):
        """Запуск фоновой загрузки заказов."""
        self.ui_queue.put(lambda: self.fetch_button.configure(state="disabled"))
        threading.Thread(target=self._fetch_orders_with_notification, daemon=True).start()

    def _fetch_orders_with_notification(self):
        """Фоновая загрузка заказов с уведомлением о новых."""
        previous_count = len(self.table.get_children())
        self._fetch_orders()
        new_count = len(self.table.get_children())
        if new_count > previous_count:
            new_orders = new_count - previous_count
            self.ui_queue.put(lambda: messagebox.showinfo("Новые заказы", f"Появилось {new_orders} новых заказов!"))
            if self.notification_sound and CONFIG["enable_notification_sound"]:
                try:
                    self.notification_sound.play()
                except Exception as e:
                    self.log_message(f"Ошибка воспроизведения звука: {e}")
        self.ui_queue.put(lambda: self.fetch_button.configure(state="normal"))

    def _fetch_orders(self):
        """Фоновая загрузка заказов с маркетплейсов."""
        self.log_message("\n=== Загрузка заказов ===")
        try:
            with sqlite3.connect(resource_path("database/orders.db")) as conn:
                cursor = conn.cursor()
                
                selected_source = self.source_filter.get()
                sources_to_fetch = SOURCES if selected_source == "Все источники" else [selected_source]

                for source in sources_to_fetch:
                    self.log_message(f"Получение заказов с {source}...")
                    try:
                        orders = []
                        if source == "Wildberries" and API_KEYS["wildberries"]:
                            orders = self.get_wildberries_orders(API_KEYS["wildberries"]).get("orders", [])
                        elif source == "Ozon":
                            orders = self.get_ozon_orders(API_KEYS["ozon"])
                        elif source == "Avito":
                            orders = self.get_avito_orders()
                        self.log_message(f"Получено заказов с {source}: {len(orders)} шт.")
                        processor = {
                            "Wildberries": self.process_wildberries_order,
                            "Ozon": self.process_ozon_order,
                            "Avito": self.process_avito_order
                        }[source]
                        for order in orders:
                            processor(order, None, conn, cursor)
                    except Exception as e:
                        self.log_message(f"Ошибка обработки {source}: {e}")
                conn.commit()
            self.log_message("=== Загрузка завершена ===")
            if self.notification_sound and CONFIG["enable_notification_sound"]:
                try:
                    self.notification_sound.play()
                except Exception as e:
                    self.log_message(f"Ошибка воспроизведения звука: {e}")
            self.ui_queue.put(self.load_orders)  # Обновляем таблицу в главном потоке
        except Exception as e:
            self.log_message(f"Ошибка загрузки заказов: {e}")
            self.ui_queue.put(lambda: messagebox.showerror("Ошибка", str(e)))

    def retry_request(self, method, url, **kwargs):
        """Повторные попытки HTTP-запроса при ошибке."""
        for attempt in range(CONFIG["max_retries"]):
            try:
                response = method(url, **kwargs)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                if attempt == CONFIG["max_retries"] - 1:
                    try:
                        error_detail = e.response.text if e.response else "Нет ответа"
                        self.log_message(f"Детали ошибки запроса: {error_detail}")
                    except:
                        self.log_message("Не удалось получить детали ошибки")
                    raise
                delay = CONFIG["retry_backoff_factor"] ** attempt
                self.log_message(f"Ошибка запроса ({e}), повтор через {delay} сек...")
                time.sleep(delay)
        raise Exception("Превышено количество попыток запроса")

    def get_chrome_executable(self):
        """Поиск пути к исполняемому файлу Chrome."""
        system = platform.system()
        if system == "Windows":
            paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            ]
            for path in paths:
                if os.path.exists(path):
                    return path
        elif system == "Darwin":
            return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        elif system == "Linux":
            paths = ["/usr/bin/google-chrome", "/usr/local/bin/google-chrome"]
            for path in paths:
                if os.path.exists(path):
                    return path
        raise FileNotFoundError("Google Chrome не найден. Укажите путь вручную.")

    def start_chrome(self):
        """Запуск Chrome с удалённой отладкой."""
        try:
            chrome_path = self.get_chrome_executable()
            command = [
                chrome_path,
                f"--remote-debugging-port={DEBUG_PORT}",
                "--no-first-run",
                "--no-default-browser-check",
                "--user-data-dir=chrome-profile",  # Сохраняем профиль чтобы не вводить заново авторизацию
                AVITO_ORDERS_URL
            ]
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=(platform.system() == "Windows"))
            self.log_message(f"Запущен Chrome с портом {DEBUG_PORT}")
            time.sleep(CHROME_START_TIMEOUT)
        except Exception as e:
            self.log_message(f"Ошибка запуска Chrome: {e}")
            raise

    def scrape_avito_orders(self, page):
        """Парсинг заказов с Avito."""
        orders = []
        try:
            self.log_message("Начало парсинга заказов Avito")
            page.wait_for_load_state("networkidle", timeout=60000)
            page.wait_for_selector("div[data-marker='order-row']", timeout=60000)
            order_elements = page.query_selector_all("div[data-marker='order-row']")
            self.log_message(f"Найдено {len(order_elements)} элементов заказов")

            for order_elem in order_elements:
                try:
                    order = {}

                    # Логируем HTML-код элемента заказа для отладки
                    order_html = order_elem.inner_html()
                    self.log_message(f"HTML элемента заказа: {order_html[:500]}...")

                    # ID заказа
                    link_elem = order_elem.query_selector("a.index-link-CLcPY")
                    order_id = "avito_" + datetime.now().strftime("%Y%m%d%H%M%S%f")
                    if link_elem:
                        href = link_elem.get_attribute("href")
                        if href:
                            order_id = href.split("/")[-1].split("?")[0]
                    order["id"] = order_id

                    # Название товара
                    img_elem = order_elem.query_selector("img[data-testid='image']")
                    title = img_elem.get_attribute("alt").strip() if img_elem else "Товар Avito"

                    # Попытка извлечь статус
                    status_elem = order_elem.query_selector("h5[data-marker='order-status']")
                    status = status_elem.text_content().strip() if status_elem else "Неизвестный статус"
                    self.log_message(f"Сырой статус заказа {order_id}: {status}")  # Логируем сырой статус

                    # Цена товара и количество
                    price_elem = order_elem.query_selector("div.styles-module-root-h__aI.styles-module-root_width_fixed-UyJd_ p")
                    price = 0.0
                    quantity = 1
                    if price_elem:
                        price_text = price_elem.text_content().strip()

                        price_match = re.search(r"([\d\s]+)₽", price_text)
                        if price_match:
                            price_raw = price_match.group(1).replace(" ", "").replace("\u00a0", "")
                            price = float(price_raw)

                        quantity_match = re.search(r"·\s*(\d+)\s*товар", price_text)
                        if quantity_match:
                            quantity = int(quantity_match.group(1))

                    order["items"] = [{
                        "title": title,
                        "avitoId": order_id,
                        "count": quantity,
                        "prices": {"price": price}
                    }]
                    order["status"] = status

                    orders.append(order)
                    self.log_message(f"Обработан заказ ID: {order_id}, Название: {title}, Цена: {price}, Количество: {quantity}, Статус: {status}")

                except Exception as e:
                    self.log_message(f"Ошибка обработки элемента заказа: {e}")

            return orders

        except PlaywrightTimeoutError:
            self.log_message("Тайм-аут при загрузке заказов. Проверьте содержимое страницы Avito.")
            page.screenshot(path=resource_path("avito_page.png"))
            self.log_message("Скриншот страницы сохранён в avito_page.png")
            with open(resource_path("avito_page.html"), "w", encoding="utf-8") as f:
                f.write(page.content())
            self.log_message("HTML страницы сохранён в avito_page.html")
            return []
        except Exception as e:
            self.log_message(f"Ошибка парсинга заказов: {e}")
            return []

    def get_avito_orders(self):
        """Получение заказов с Avito через парсинг страницы."""
        all_orders = []
        try:
            self.start_chrome()
        except Exception as e:
            self.log_message(f"Не удалось запустить Chrome: {e}")
            return []

        with sync_playwright() as p:
            for attempt in range(3):
                try:
                    browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
                    self.log_message("Подключено к Chrome")
                    break
                except Exception as e:
                    self.log_message(f"Попытка {attempt + 1} не удалась: {e}")
                    time.sleep(2)
                    if attempt == 2:
                        self.log_message("Не удалось подключиться к Chrome. Убедитесь, что Chrome запущен с портом 9222.")
                        return []

            pages = browser.contexts[0].pages
            avito_page = None

            for page in pages:
                try:
                    if AVITO_ORDERS_URL.split("?")[0] in page.url:
                        avito_page = page
                        self.log_message(f"Найдена вкладка с Avito: {page.url}")
                        break
                except Exception as e:
                    self.log_message(f"Ошибка проверки вкладки: {e}")

            if not avito_page:
                self.log_message(f"Вкладка с {AVITO_ORDERS_URL} не найдена")
                browser.close()
                return []

            try:
                avito_page.goto(AVITO_ORDERS_URL, timeout=60000)
                if "Войти" in avito_page.content():
                    self.log_message("Требуется авторизация. Войдите в аккаунт Avito в открытой вкладке.")
                    time.sleep(30)
                    avito_page.reload()
                    if "Войти" in avito_page.content():
                        self.log_message("Авторизация не выполнена. Пропуск парсинга.")
                        browser.close()
                        return []

                os.makedirs(os.path.dirname(resource_path(COOKIES_FILE)), exist_ok=True)
                try:
                    cookies = browser.contexts[0].cookies()
                    with open(resource_path(COOKIES_FILE), "w") as f:
                        json.dump(cookies, f)
                    self.log_message("Cookies сохранены")
                except Exception as e:
                    self.log_message(f"Ошибка сохранения cookies: {e}. Продолжаем парсинг.")

                orders = self.scrape_avito_orders(avito_page)
                all_orders.extend(orders)
                self.log_message(f"Получено {len(orders)} заказов")

            except Exception as e:
                self.log_message(f"Ошибка обработки страницы Avito: {e}")
                import traceback
                self.log_message(f"Трассировка: {traceback.format_exc()}")

            browser.close()

        return all_orders

    def get_wildberries_orders(self, api_key):
        """Получение заказов с Wildberries."""
        self.log_message("Подключение к API Wildberries...")
        url = "https://marketplace-api.wildberries.ru/api/v3/orders"
        headers = {"Authorization": api_key, "Content-Type": "application/json"}
        self.log_message(f"Используемый API-ключ: {api_key[:20]}...")
        date_start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        date_end = datetime.now().strftime("%Y-%m-%d")
        all_orders = []
        skip = 0
        limit = 100

        while True:
            params = {
                "date_start": date_start,
                "date_end": date_end,
                "limit": limit,
                "skip": skip
            }
            try:
                response = self.retry_request(requests.get, url, headers=headers, params=params, timeout=10)
                data = response.json()
                self.log_message(f"Ответ API Wildberries: {data}")
                orders = data.get("orders", [])
                all_orders.extend(orders)
                self.log_message(f"Получено {len(orders)} заказов с Wildberries, всего: {len(all_orders)}")
                if len(orders) < limit:
                    break
                skip += limit
            except requests.RequestException as e:
                self.log_message(f"Ошибка запроса к API Wildberries: {e}")
                if e.response:
                    self.log_message(f"Код ответа: {e.response.status_code}")
                    self.log_message(f"Тело ответа: {e.response.text}")
                    self.log_message(f"Заголовки ответа: {e.response.headers}")
                else:
                    self.log_message("Сервер не вернул ответа")
                if "401" in str(e):
                    self.log_message("Проверьте действительность API-ключа и доступ к эндпоинту.")
                break
        return {"orders": all_orders}

    def get_ozon_orders(self, api_key):
        """Получение заказов с Ozon."""
        self.log_message("Подключение к API Ozon...")
        headers = {"Client-Id": OZON_CLIENT_ID, "Api-Key": api_key, "Content-Type": "application/json"}
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        all_orders = []
        offset = 0
        url = "https://api-seller.ozon.ru/v3/posting/fbs/list"
        while True:
            payload = {
                "filter": {
                    "since": date_from,
                    "to": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "status": "awaiting_packaging"
                },
                "limit": 1000,
                "offset": offset
            }
            try:
                response = self.retry_request(requests.post, url, headers=headers, json=payload, timeout=10)
                orders = response.json().get("result", {}).get("postings", [])
                all_orders.extend(orders)
                if len(orders) < 1000:
                    break
                offset += 1000
            except requests.RequestException as e:
                self.log_message(f"Ошибка запроса к API Ozon: {e}")
                break
        return all_orders

    def process_wildberries_order(self, order, existing_orders, conn, cursor):
        """Обработка заказа Wildberries."""
        try:
            external_id = str(order.get("id", f"wb_{datetime.now().timestamp()}"))
            # Проверяем, существует ли заказ
            cursor.execute("SELECT 1 FROM orders WHERE external_id = ?", (external_id,))
            if cursor.fetchone():
                return  # Заказ уже существует, пропускаем

            status_map = {"new": "Новый", "confirmed": "Новый", "processing": "Готов", "delivered": "Готов", "cancelled": "Готов"}
            status = status_map.get(order.get("status", "new"), "Новый")

            products = order.get("products", [])
            if not products:
                self.log_message(f"Заказ Wildberries {external_id} не содержит продуктов, пропуск")
                return
            product = products[0]
            cursor.execute("""
                INSERT INTO orders (external_id, product_image, product_name, product_link, quantity, price, source, status, comment, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                external_id,
                CONFIG["default_image"],
                product.get("name", "Товар Wildberries"),
                product.get("link", ""),
                int(product.get("quantity", 1)),
                float(product.get("price", 0.0)),
                "Wildberries",
                status,
                "",  # Пустой комментарий по умолчанию
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            self.log_message(f"Добавлен заказ Wildberries: {product.get('name', 'Товар Wildberries')}")
        except Exception as e:
            self.log_message(f"Ошибка обработки заказа Wildberries {external_id}: {e}")

    def process_ozon_order(self, order, existing_orders, conn, cursor):
        """Обработка заказа Ozon."""
        try:
            external_id = str(order.get("posting_number", f"ozon_{datetime.now().timestamp()}"))
            # Проверяем, существует ли заказ
            cursor.execute("SELECT 1 FROM orders WHERE external_id = ?", (external_id,))
            if cursor.fetchone():
                return  # Заказ уже существует, пропускаем

            status_map = {"awaiting_packaging": "Новый", "awaiting_deliver": "Новый", "delivering": "Готов", "delivered": "Готов", "cancelled": "Готов"}
            status = status_map.get(order.get("status", "awaiting_packaging"), "Новый")

            product = order.get("products", [{}])[0]
            offer_id = product.get("offer_id", "")
            cursor.execute("""
                INSERT INTO orders (external_id, product_image, product_name, product_link, quantity, price, source, status, comment, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                external_id,
                CONFIG["default_image"],
                product.get("name", "Товар Ozon"),
                f"https://www.ozon.ru/product/{offer_id}" if offer_id else "",
                int(product.get("quantity", 1)),
                float(product.get("price", 0.0)),
                "Ozon",
                status,
                "",  # Пустой комментарий по умолчанию
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            self.log_message(f"Добавлен заказ Ozon: {product.get('name', 'Товар Ozon')}")
        except Exception as e:
            self.log_message(f"Ошибка обработки заказа Ozon: {e}")

    def process_avito_order(self, order, existing_orders, conn, cursor):
        """Обработка заказа Avito."""
        try:
            order_str = str(order)[:500] + "..." if len(str(order)) > 500 else str(order)
            self.log_message(f"Обработка заказа Avito: {order_str}")

            if not isinstance(order, dict):
                self.log_message(f"Неизвестный формат заказа Avito: {type(order)}")
                return

            external_id = str(order.get("id"))
            if not external_id:
                external_id = f"avito_{datetime.now().timestamp()}"
                self.log_message(f"ID заказа не найден, использую временный ID: {external_id}")

            # Проверяем, существует ли заказ
            cursor.execute("SELECT 1 FROM orders WHERE external_id = ?", (external_id,))
            if cursor.fetchone():
                return  # Заказ уже существует, пропускаем

            status_map = {
                "Ожидает подтверждения": "Новый",
                "Подтверждён": "Новый",
                "Отправьте заказ": "Новый",
                "Готов к выдаче": "Готов",
                "Выдан": "Готов",
                "Отменён": "Готов",
                "Неизвестный статус": "Новый"
            }
            raw_status = order.get("status", "Неизвестный статус")
            status = status_map.get(raw_status, "Новый")
            self.log_message(f"Маппинг статуса для заказа {external_id}: '{raw_status}' -> '{status}'")

            items = order.get("items", [])
            if not items:
                self.log_message(f"Заказ Avito {external_id} не содержит товаров, пропуск")
                return
            item = items[0]

            product_name = item.get("title", "Товар Avito")
            product_link = f"https://www.avito.ru/orders/{item.get('avitoId', '')}?source=orders_list" if item.get('avitoId') else ""
            quantity = int(item.get("count", 1))

            prices = item.get("prices", {})
            price = float(prices.get("price", 0.0))

            cursor.execute("""
                INSERT INTO orders (external_id, product_image, product_name, product_link, quantity, price, source, status, comment, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                external_id,
                CONFIG["default_image"],
                product_name,
                product_link,
                quantity,
                price,
                "Avito",
                status,
                "",  # Пустой комментарий по умолчанию
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            self.log_message(f"Добавлен заказ Avito: {product_name}, Статус: {status}, Ссылка: {product_link}")

        except Exception as e:
            self.log_message(f"Ошибка обработки заказа Avito: {e}")
            import traceback
            self.log_message(f"Трассировка: {traceback.format_exc()}")

    def copy_log(self):
        """Копирование лога в буфер обмена."""
        try:
            log_content = "".join(self.log_lines)
            self.clipboard_clear()
            self.clipboard_append(log_content)
            self.log_message("Лог скопирован в буфер обмена")
        except Exception as e:
            self.log_message(f"Ошибка копирования лога: {e}")
            messagebox.showerror("Ошибка", "Не удалось скопировать лог.")

    def close(self):
        """Закрытие приложения."""
        super().destroy()

if __name__ == "__main__":
    app = MarketplaceCRM()
    app.mainloop()