# 🛒 Telegram Shop Bot with Channel Showcase

Телеграм-магазин с интеграцией витрины в Telegram-канале, Deep Linking, автосидингом и админ-панелью.

## 📁 Структура проекта

- **[`bot.py`](file:///Users/axat/Projects/tg_bot_for_ai_sofi/bot.py)** — Главный файл запуска бота (`python bot.py`).
- **[`docs/`](file:///Users/axat/Projects/tg_bot_for_ai_sofi/docs)** — Вся документация вынесена в отдельную папку:
  - 📖 **[`docs/README.md`](file:///Users/axat/Projects/tg_bot_for_ai_sofi/docs/README.md)** — Полное руководство по установке, настройке `.env` и описанию системы.
  - 🧪 **[`docs/TESTING_FLOW.md`](file:///Users/axat/Projects/tg_bot_for_ai_sofi/docs/TESTING_FLOW.md)** — Пошаговый сценарий и чек-лист для проверки всех функций бота.
  - 📄 **[`docs/CHANNEL_SHOP_SPEC.md`](file:///Users/axat/Projects/tg_bot_for_ai_sofi/docs/CHANNEL_SHOP_SPEC.md)** — Техническая спецификация интеграции с каналом, альбомами и CRUD.
- **[`scripts/`](file:///Users/axat/Projects/tg_bot_for_ai_sofi/scripts)** — Сервисные скрипты:
  - **[`scripts/seed_demo_with_images.py`](file:///Users/axat/Projects/tg_bot_for_ai_sofi/scripts/seed_demo_with_images.py)** — Автосидинг с загрузкой фото одежды из Unsplash и постом в канал.
  - **[`scripts/seed_demo.py`](file:///Users/axat/Projects/tg_bot_for_ai_sofi/scripts/seed_demo.py)** — Быстрый сидинг без картинок.
  - **[`scripts/cleanup_channel.py`](file:///Users/axat/Projects/tg_bot_for_ai_sofi/scripts/cleanup_channel.py)** — Cron-скрипт удаления из канала товаров не в наличии (>7 дней).
- **[`shopbot/`](file:///Users/axat/Projects/tg_bot_for_ai_sofi/shopbot)** — Исходный код приложения.
- **[`tests/`](file:///Users/axat/Projects/tg_bot_for_ai_sofi/tests)** — Автоматические тесты (`python -m unittest discover tests`).

## ⚡ Быстрый старт

### macOS / Linux:
```bash
# 1. Активировать виртуальное окружение
source .venv/bin/activate

# 2. Наполнить базу товарами
python scripts/seed_demo.py
# или с фото и публикацией в канал:
# python scripts/seed_demo_with_images.py

# 3. Запустить бота
python bot.py
```

### Windows (PowerShell):
```powershell
# 1. Создать виртуальное окружение (если еще не создано)
python -m venv .venv

# 2. Активировать виртуальное окружение
.venv\Scripts\Activate.ps1
# (если возникает ошибка выполнения скриптов, выполните один раз: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Наполнить базу товарами
python scripts\seed_demo.py
# или с фото и публикацией в канал:
# python scripts\seed_demo_with_images.py

# 5. Запустить бота
python bot.py
```

### Windows (Командная строка CMD):
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
python scripts\seed_demo.py
python bot.py
```

Подробные инструкции по тестированию см. в **[`docs/TESTING_FLOW.md`](file:///Users/axat/Projects/tg_bot_for_ai_sofi/docs/TESTING_FLOW.md)**.
