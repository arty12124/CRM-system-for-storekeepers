# CRM-system-for-storekeepers

Это CRM-система для кладовщиков, которая помогает управлять заказами с маркетплейсов, таких как Wildberries, Ozon и Avito. Она написана на Python с использованием библиотек customtkinter для интерфейса, playwright для парсинга и sqlite3 для хранения данных.

Что делает программа:
Собирает заказы:
  Подключается к Wildberries и Ozon через API, а к Avito — через парсинг страницы (с помощью браузера Chrome и Playwright).
  Извлекает данные о заказах: ID, название товара, количество, цену, статус, дату и ссылку на заказ.
  Сохраняет данные:
Все заказы сохраняются в локальную базу данных SQLite (orders.db).
Дубликаты заказов автоматически пропускаются.
Отображает заказы:
Показывает заказы в удобной таблице с фильтрами по статусу ("Новый", "Готов") и источнику (Wildberries, Ozon, Avito).
В таблице есть столбцы: чекбокс, ID, название, количество, цена, источник, статус, комментарий, дата и ссылка.
Позволяет управлять заказами:
Можно менять статус заказа ("Новый" ↔ "Готов") двойным кликом.
Отмечать заказы чекбоксом и массово менять статус на "Готов" кнопкой "Выполнено".
Фильтровать заказы по статусу и источнику.
Открывать ссылки на заказы в браузере.
Автоматизация и уведомления:
Поддерживает автообновление заказов (каждую минуту, если включено).
Уведомляет о новых заказах (всплывающее окно и звуковой сигнал).
Логирует все действия и ошибки в текстовое поле в интерфейсе.
Зачем нужна:
Для кладовщиков: Программа упрощает работу с заказами, позволяя быстро видеть новые заказы, отслеживать их статус и отмечать выполненные.
Для автоматизации: Снижает ручной труд — не нужно вручную проверять заказы на сайтах маркетплейсов.
Для контроля: Все данные хранятся в одном месте, с фильтрами и возможностью управления статусами, что помогает не пропустить важные заказы.
Программа полезна для небольших складов или частных продавцов, которые работают с несколькими маркетплейсами и хотят централизованно управлять заказами.

![{6493AC67-9C55-4F6C-8D03-B99E86AEB48B}](https://github.com/user-attachments/assets/f455040d-8b90-41d9-8a53-8db842897af1)
![{BCD929E4-A965-492F-A67B-7A4C930A095A}](https://github.com/user-attachments/assets/6ec538ad-02e0-4a01-b695-cbf979ef14f4)



# CRM-system-for-storekeepers

It is a CRM system for storekeepers that helps manage orders from marketplaces such as Wildberries, Ozon and Avito. It is written in Python using the customtkinter libraries for the interface, playwright for parsing, and sqlite3 for data storage.

What the program does:
Collects orders:
Connects to Wildberries and Ozon via the API, and to Avito via page parsing (using the Chrome browser and Playwright).
Retrieves order data: ID, product name, quantity, price, status, date, and order link.
Saves data:
All orders are saved to the local SQLite database (orders.db).
Duplicate orders are automatically skipped.
Displays orders:
It shows orders in a convenient table with filters by status ("New", "Ready") and source (Wildberries, Ozon, Avito).
The table has columns: checkbox, ID, name, quantity, price, source, status, comment, date, and link.
Allows you to manage orders:
You can change the order status ("New", "Ready") with a double click.
Mark orders with a checkbox and massively change the status to "Ready" with the "Completed" button.
Filter orders by status and source.
Open links to orders in the browser.
Automation and notifications:
Supports auto-updating of orders (every minute if enabled).
Notifies you of new orders (pop-up window and beep).
Logs all actions and errors in a text field in the interface.
Why it is needed:
For storekeepers: The program simplifies work with orders, allowing you to quickly see new orders, track their status and mark completed ones.
For automation: Reduces manual labor — no need to manually check orders on marketplace sites.
For control: All data is stored in one place, with filters and the ability to manage statuses, which helps not to miss important orders.
The program is useful for small warehouses or private sellers who work with multiple marketplaces and want to centrally manage orders.
