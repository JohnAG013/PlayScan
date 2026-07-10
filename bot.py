import asyncio
import logging
import sys
from os import getenv
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Импортируем инициализацию базы данных и роутер с обработчиками
from database import init_db, get_all_active_alerts, trigger_alert, get_user_profile, CURRENCIES
from handlers import router
from services import get_best_price, convert_price, _get_exchange_rates

# Загружаем переменные окружения из файла .env
load_dotenv()

# Глобальная переменная для бота (чтобы отправлять уведомления из фоновой задачи)
_bot: Bot = None

async def check_alerts_periodically():
    """Фоновая задача: проверяет цены по алертам каждые 30 минут."""
    global _bot
    while True:
        try:
            await asyncio.sleep(1800)  # 30 минут

            if _bot is None:
                continue

            logging.info("Проверяю алерты на цены...")
            alerts = await get_all_active_alerts()

            if not alerts:
                logging.info("Активных алертов нет.")
                continue

            # Группируем алерты по игре (чтобы не проверять одну игру дважды)
            unique_games = {}
            for alert in alerts:
                game = alert["game_title"]
                if game not in unique_games:
                    unique_games[game] = []
                unique_games[game].append(alert)

            logging.info(f"Проверяю {len(unique_games)} уникальных игр...")

            for game_title, game_alerts in unique_games.items():
                try:
                    # Получаем лучшую цену
                    best_price = await get_best_price(game_title)

                    if not best_price:
                        continue

                    # Проверяем каждый алерт для этой игры
                    for alert in game_alerts:
                        user_id = alert["user_id"]
                        target_price = alert["target_price"]
                        currency = alert["currency"]

                        # Конвертируем цену в валюту пользователя
                        price_usd = best_price["price_usd"]

                        if currency != "USD":
                            rates = await _get_exchange_rates({})  # Получаем курсы
                            price_converted = convert_price(price_usd, currency, rates)
                            if price_converted is None:
                                price_converted = price_usd
                        else:
                            price_converted = price_usd

                        # Проверяем, достигнута ли целевая цена
                        if price_converted <= target_price:
                            cur_symbol = CURRENCIES.get(currency, currency)

                            # Формируем уведомление
                            savings = best_price.get("savings", 0)
                            discount_text = f" (-{savings:.0f}%)" if savings > 0 else ""

                            notification = (
                                f"🔔 <b>Цена упала!</b>\n\n"
                                f"🎮 {best_price['title']}\n"
                                f"💰 <b>{cur_symbol}{price_converted}</b> (было цель: {cur_symbol}{target_price}){discount_text}\n\n"
                                f"🔗 <a href=\"{best_price['link']}\">Купить</a>"
                            )

                            # Отправляем уведомление
                            try:
                                await _bot.send_message(
                                    user_id,
                                    notification,
                                    parse_mode="HTML",
                                    disable_web_page_preview=True,
                                )
                                logging.info(f"Отправлено уведомление {user_id}: {game_title} = {price_converted} {currency}")

                                # Деактивируем алерт
                                await trigger_alert(user_id, game_title)

                            except Exception as e:
                                logging.error(f"Ошибка отправки уведомления {user_id}: {e}")

                    # Пауза между играми
                    await asyncio.sleep(2)

                except Exception as e:
                    logging.error(f"Ошибка проверки алерта для {game_title}: {e}")
                    continue

            logging.info("Проверка алертов завершена.")

        except Exception as e:
            logging.error(f"Ошибка в фоновой задаче алертов: {e}")
            await asyncio.sleep(60)


async def on_startup(dispatcher: Dispatcher):
    """
    Действия, выполняемые при запуске бота:
    - Инициализация и создание таблиц в базе данных.
    """
    logging.info("Выполняется запуск бота и подготовка ресурсов...")
    # Создаем таблицы в БД, если их нет
    await init_db()

async def main() -> None:
    global _bot

    # Получаем токен из переменной окружения BOT_TOKEN
    bot_token = getenv("BOT_TOKEN")

    # Проверка, задан ли корректный токен
    if not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE" or bot_token.startswith("123456789:"):
        logging.error(
            "КРИТИЧЕСКАЯ ОШИБКА: Токен Telegram-бота (BOT_TOKEN) не задан или содержит демонстрационное значение!\n"
            "Пожалуйста, откройте файл '.env', расположенный в корневой папке проекта, "
            "и замените значение BOT_TOKEN на токен вашего бота от @BotFather."
        )
        sys.exit(1)

    # Создаем экземпляр бота
    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    _bot = bot  # Сохраняем для фоновой задачи

    # Создаем диспетчер
    dp = Dispatcher()

    # Подключаем роутер
    dp.include_router(router)

    # Регистрируем обработчик запуска
    dp.startup.register(on_startup)

    try:
        # Удаляем вебхуки
        await bot.delete_webhook(drop_pending_updates=True)

        logging.info("Бот успешно запущен и начинает опрос серверов Telegram (Polling)...")

        # Запускаем фоновую задачу проверки алертов
        asyncio.create_task(check_alerts_periodically())
        logging.info("Фоновая проверка алертов запущена (каждые 30 минут)")

        # Запускаем поллинг
        await dp.start_polling(bot)

    except Exception as e:
        logging.critical(f"Произошла непредвиденная ошибка при работе бота: {e}")
    finally:
        logging.info("Закрытие сессии бота...")
        await bot.session.close()

if __name__ == "__main__":
    # Настраиваем логирование
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout
    )

    # Запускаем асинхронный цикл событий
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен пользователем.")
