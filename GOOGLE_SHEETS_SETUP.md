# Настройка Google Sheets для бота

## Пошаговая инструкция

### Шаг 1: Создай Google Cloud проект

1. Перейди на https://console.cloud.google.com
2. Нажми "Выбрать проект" → "Новый проект"
3. Название: любое (например "PlayScan Bot")
4. Нажми "Создать"

### Шаг 2: Включи API

1. В левом меню → "APIs & Services" → "Library"
2. Найди и включи:
   - **Google Sheets API**
   - **Google Drive API**

### Шаг 3: Создай сервисный аккаунт

1. "APIs & Services" → "Credentials" → "Create Credentials" → "Service Account"
2. Имя: любое (например "playscan-bot")
3. Нажми "Create and Continue"
4. Роль: выбери "Editor"
5. Нажми "Done"

### Шаг 4: Скачай JSON-ключ

1. В списке сервисных аккаунтов нажми на созданный
2. Вкладка "Keys" → "Add Key" → "Create new key"
3. Выбери "JSON" → нажми "Create"
4. Файл скачается автоматически

### Шаг 5: Положи JSON в проект

1. Переименуй скачанный файл в `service_account.json`
2. Положи его в корень проекта (рядом с bot.py)

### Шаг 6: Создай таблицу в Google Sheets

1. Перейди на https://sheets.google.com
2. Создай новую таблицу
3. Назови первый лист "Users" (правый клик на лист → "Rename")
4. В первой строке напиши заголовки:

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| user_id | username | registration_date | currency | device | role |

5. Скопируй ID таблицы из URL:
   - URL выглядит так: `https://docs.google.com/spreadsheets/d/ВОТ_ЭТОТ_ID/edit`
   - Скопируй эту часть

### Шаг 7: Поделись таблицей с сервисным аккаунтом

1. В Google Sheets нажми "Sharing" (значок человека)
2. В поле "Add people and groups" впиши email сервисного аккаунта
   - Его можешь найти в JSON-файле (поле "client_email")
   - Выглядит как: `playscan-bot@project-name.iam.gserviceaccount.com`
3. Выбери роль "Editor"
4. Нажми "Send"

### Шаг 8: Добавь ID в .env

Открой файл `.env` и замени:

```
GOOGLE_SPREADSHEET_ID=YOUR_SPREADSHEET_ID_HERE
```

На скопированный ID таблицы.

### Шаг 9: Установи зависимости

```bash
pip install gspread google-auth
```

### Шаг 10: Запусти бота

```bash
python bot.py
```

## Готово!

Теперь:
- Бот читает пользователей из Google Sheets при запуске
- Новые пользователи записываются автоматически
- Данные хранятся в облаке и не теряются

## Где смотреть данные

Просто открой таблицу в Google Sheets и видишь всех пользователей:
- Кто зарегистрировался
- Какую валюту выбрал
- Какую платформу использует

## Частые ошибки

**"SpreadsheetNotFound"** → Проверь ID таблицы в .env

**"The caller does not have permission"** → Поделись таблицей с email сервисного аккаунта

**"File not found: service_account.json"** → Положи JSON-файл в корень проекта
