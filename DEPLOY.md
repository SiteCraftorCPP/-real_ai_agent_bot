# Инструкция по загрузке бота на сервер

## Шаг 1: Загрузка файлов на сервер

Откройте PowerShell или командную строку на вашем компьютере и выполните команды для загрузки файлов на сервер:

### Вариант 1: Загрузка всего проекта одной командой (рекомендуется)

```powershell
# Перейдите в папку с проектом
cd "C:\Users\EscoM\Desktop\GPT5 bot zakaz"

# Создайте архив (опционально, но удобнее)
# Можно пропустить и загружать напрямую через SCP

# Загрузите все файлы на сервер (исключая __pycache__)
scp -r bot assets README.md requirements.txt root@31.130.148.228:/root/telegram-bot/
```

### Вариант 2: Загрузка через WinSCP (GUI)

1. Скачайте и установите [WinSCP](https://winscp.net/)
2. Подключитесь к серверу:
   - Host: `31.130.148.228`
   - Username: `root`
   - Password: (введите ваш пароль)
3. Скопируйте папки `bot`, `assets` и файлы `README.md`, `requirements.txt` в `/root/telegram-bot/`

## Шаг 2: Подключение к серверу

```powershell
ssh root@31.130.148.228
```

## Шаг 3: Установка Python и зависимостей на сервере

На сервере выполните следующие команды:

```bash
# Обновление системы
apt update && apt upgrade -y

# Установка Python 3.10+ и pip (если еще не установлены)
apt install -y python3 python3-pip python3-venv

# Создание директории для бота (если еще не создана)
mkdir -p /root/telegram-bot
cd /root/telegram-bot

# Создание виртуального окружения
python3 -m venv venv

# Активация виртуального окружения
source venv/bin/activate

# Установка зависимостей
pip install --upgrade pip
pip install -r requirements.txt
```

## Шаг 4: Создание файла .env

Создайте файл `.env` с настройками бота:

```bash
nano .env
```

Добавьте следующее содержимое (замените значения на ваши):

```env
BOT_TOKEN=your_bot_token_here
ADMIN_CHAT_IDS=123456789,987654321
ADMIN_USERNAMES=admin1,admin2
LOGO_PATH=assets/logo.png

# LLM Provider selection (proxyapi or openrouter)
LLM_PROVIDER=proxyapi

# ProxyAPI configuration (основной провайдер)
PROXYAPI_API_KEY=put_key_here
PROXYAPI_BASE_URL=https://openai.api.proxyapi.ru/v1
PROXYAPI_MODEL=openai/gpt-5.1
PROXYAPI_MAX_TOKENS=1500

# OpenRouter configuration (опционально, для отката)
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-5.1
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_SITE_URL=http://localhost
OPENROUTER_APP_NAME=Welhome Bot
OPENROUTER_MAX_TOKENS=1500
```

Сохраните файл: `Ctrl+O`, затем `Enter`, затем `Ctrl+X`

## Шаг 5: Проверка структуры файлов

Убедитесь, что все файлы на месте:

```bash
cd /root/telegram-bot
ls -la
# Должны быть видны: bot/, assets/, .env, requirements.txt, README.md
```

## Шаг 6: Первый запуск бота (тестовый)

```bash
cd /root/telegram-bot
source venv/bin/activate
python3 -m bot.main
```

Если бот запустился без ошибок, остановите его: `Ctrl+C`

## Шаг 7: Настройка автозапуска через systemd

Создайте systemd сервис для автоматического запуска бота:

```bash
nano /etc/systemd/system/telegram-bot.service
```

Добавьте следующее содержимое:

```ini
[Unit]
Description=Telegram Bot Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/telegram-bot
Environment="PATH=/root/telegram-bot/venv/bin"
ExecStart=/root/telegram-bot/venv/bin/python3 -m bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Сохраните и выйдите: `Ctrl+O`, `Enter`, `Ctrl+X`

Активируйте и запустите сервис:

```bash
# Перезагрузка systemd
systemctl daemon-reload

# Включение автозапуска при загрузке системы
systemctl enable telegram-bot

# Запуск бота
systemctl start telegram-bot

# Проверка статуса
systemctl status telegram-bot

# Просмотр логов
journalctl -u telegram-bot -f
```

## Полезные команды для управления ботом

```bash
# Остановить бота
systemctl stop telegram-bot

# Запустить бота
systemctl start telegram-bot

# Перезапустить бота
systemctl restart telegram-bot

# Посмотреть статус
systemctl status telegram-bot

# Посмотреть последние логи
journalctl -u telegram-bot -n 100

# Следить за логами в реальном времени
journalctl -u telegram-bot -f
```

## Обновление бота в будущем

Когда нужно обновить код бота:

```bash
# На вашем компьютере: загрузите обновленные файлы
cd "C:\Users\EscoM\Desktop\GPT5 bot zakaz"
scp -r bot/* root@31.130.148.228:/root/telegram-bot/bot/

# На сервере: перезапустите бота
ssh root@31.130.148.228
systemctl restart telegram-bot
```



