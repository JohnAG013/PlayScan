from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from html import escape
import logging

from database import (
    user_exists, add_user, get_user_profile,
    set_user_currency, set_user_device, set_user_region,
    CURRENCIES, DEVICES, can_search, increment_search_count,
    add_alert, get_user_alerts, remove_alert,
)
from services import search_games, get_game_deals, search_deals, get_stores_list, enrich_deals_with_official_links, get_regional_prices, ALL_REGIONS, search_console_game
from price_fetcher import search_playfetch

router = Router()
logger = logging.getLogger(__name__)

PLATFORM_LABELS = {
    "pc": "🖥️ PC",
    "ps": "🎮 PlayStation",
    "xbox": "🟩 Xbox",
    "nintendo": "🔴 Nintendo",
    "all": "🌐 Все",
}


# ─────────────── Утилиты ───────────────

def _format_deals_list(deals: list[dict], title: str, currency: str) -> str:
    """Единый формат для списка цен в HTML."""
    cur_symbol = CURRENCIES.get(currency, currency)
    text = f"🎮 <b>{escape(title)}</b>\n"

    if currency != "USD":
        text += f"💱 Цены: USD / {currency}\n"

    text += "\n"

    for i, deal in enumerate(deals, 1):
        plat = PLATFORM_LABELS.get(deal["platform"], deal["platform"])

        # Для консольных игр (нет цены в API)
        if deal.get("note"):
            store_link = f"<a href=\"{deal['link']}\">{escape(deal['store'])}</a>"
            game_link = f"<a href=\"{deal['link']}\">{escape(deal['title'])}</a>"

            text += (
                f"<b>{i}.</b> {game_link}\n"
                f"    🏪 {store_link} • {plat}\n"
                f"    💰 <i>{deal['note']}</i>\n\n"
            )
        else:
            # Для PC игр с ценами
            savings = deal.get("savings", 0)
            discount_tag = f" (-{savings:.0f}%)" if savings > 0 else ""

            price_line = f"${deal.get('price_usd', '?')}"
            if deal.get("price_converted") and currency != "USD":
                price_line += f" / {cur_symbol}{deal['price_converted']}"

            store_link = f"<a href=\"{deal['link']}\">{escape(deal['store'])}</a>"
            game_url = deal.get("official_link") or deal.get("game_link", deal.get('link', ''))
            game_link = f"<a href=\"{game_url}\">{escape(deal['title'])}</a>"

            text += (
                f"<b>{i}.</b> {game_link}\n"
                f"    🏪 {store_link} • {plat}\n"
                f"    💰 <b>{price_line}</b>{discount_tag}\n\n"
            )

    return text


def _chunk_text(text: str, max_len: int = 4000) -> list[str]:
    """Разбивает текст на части по строкам, не превышая max_len."""
    lines = text.split("\n")
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        chunks.append(current)
    return chunks


# ─────────────── /start ───────────────

@router.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        full_name = message.from_user.full_name

        is_registered = await user_exists(user_id)

        if is_registered:
            await message.answer(
                f"Рад видеть тебя снова, <b>{escape(full_name)}</b>!\n\n"
                "Отправь название игры — я найду лучшие цены.\n"
                "/profile — настрой профиль\n/stores — список магазинов\n/help — справка"
            )
        else:
            await add_user(user_id, username)
            await message.answer(
                f"Привет, <b>{escape(full_name)}</b>!\n\n"
                "Я ищу цены на игры в разных магазинах мира.\n\n"
                "Отправь название игры — и я покажу лучшие предложения.\n"
                "/profile — настроить валюту и платформу\n/help — справка"
            )
    except Exception as e:
        logger.error(f"Ошибка в /start: {e}")
        try:
            await message.answer("Произошла ошибка. Попробуй снова.")
        except Exception:
            pass


# ─────────────── /help ───────────────

@router.message(Command("help"))
async def command_help_handler(message: types.Message) -> None:
    try:
        await message.answer(
            "🎮 <b>PlayScan — бот для поиска цен на игры</b>\n\n"
            "Просто отправь название игры — бот покажет лучшие цены!\n\n"
            "<b>Основное:</b>\n"
            "• Отправь название игры для поиска цен\n"
            "• Используй кнопки для выбора предложений\n\n"
            "<b>Команды:</b>\n\n"
            "🔍 <b>/region Название</b> — цены по регионам\n"
            "   Пример: <code>/region Cyberpunk 2077</code>\n"
            "   С фильтром: <code>/region Cyberpunk 2077 ru</code>\n"
            "   Регионы: ru, us, de, uk, fr, it, jp, cn и др.\n\n"
            "🔔 <b>/alert Игра Цена</b> — оповещение о скидке\n"
            "   Пример: <code>/alert Cyberpunk 2077 20</code>\n"
            "   Уведомит когда цена упадёт ниже указанной\n\n"
            "📋 <b>/alerts</b> — список твоих оповещений\n"
            "❌ <b>/remove_alert Игра</b> — удалить оповещение\n\n"
            "👤 <b>/profile</b> — настройки (валюта, регион, платформа)\n"
            "🏪 <b>/stores</b> — список магазинов\n"
            "☕ <b>/support</b> — поддержать автора\n"
            "ℹ️ <b>/about</b> — информация о боте",
        )
    except Exception as e:
        logger.error(f"Ошибка в /help: {e}")


# ─────────────── /alerts ───────────────

@router.message(Command("alerts"))
async def command_alerts_handler(message: types.Message) -> None:
    try:
        user_id = message.from_user.id
        profile = await get_user_profile(user_id)
        role = profile.get("role", "user") if profile else "user"

        if role == "user":
            await message.answer(
                "🔔 <b>Оповещения о ценах</b> — функция Premium.\n\n"
                "Когда цена на игру упадёт ниже указанной — бот напишет тебе!\n\n"
                "Чтобы получить Premium, напиши /premium"
            )
            return

        alerts = await get_user_alerts(user_id)
        if not alerts:
            await message.answer(
                "🔔 У тебя нет активных оповещений.\n\n"
                "Чтобы добавить, напиши:\n"
                "<code>/alert Cyberpunk 2077 20</code>"
            )
            return

        text = "🔔 <b>Твои оповещения:</b>\n\n"
        for i, alert in enumerate(alerts, 1):
            currency = alert.get("currency", "USD")
            cur_symbol = CURRENCIES.get(currency, currency)
            text += f"{i}. {escape(alert['game_title'])} — до {cur_symbol}{alert['target_price']} ({currency})\n"

        text += "\nУдалить: <code>/remove_alert Название игры</code>"
        await message.answer(text)

    except Exception as e:
        logger.error(f"Ошибка в /alerts: {e}")


@router.message(Command("alert"))
async def command_alert_handler(message: types.Message) -> None:
    try:
        user_id = message.from_user.id
        profile = await get_user_profile(user_id)
        role = profile.get("role", "user") if profile else "user"

        if role == "user":
            await message.answer(
                "⭐ Эта функция доступна в <b>Premium</b>.\n\n"
                "Напиши /premium для подробностей"
            )
            return

        # Получаем валюту пользователя
        user_currency = profile.get("currency", "USD") if profile else "USD"
        cur_symbol = CURRENCIES.get(user_currency, user_currency)

        # Парсим команду: /alert Game Title 20
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer(
                f"Использование: <code>/alert Название игры ЦЕНА</code>\n\n"
                f"Твоя валюта: <b>{user_currency}</b> ({cur_symbol})\n\n"
                f"Пример: <code>/alert Cyberpunk 2077 20</code>\n"
                f"Бот уведомит когда цена упадёт ниже 20 {user_currency}"
            )
            return

        # Ищем цену в конце
        parts = args[1].rsplit(maxsplit=1)
        if len(parts) < 2 or not parts[1].replace(".", "").isdigit():
            await message.answer(
                f"Укажи цену числом.\n\n"
                f"Пример: <code>/alert Cyberpunk 2077 20</code>\n"
                f"Цена будет в {user_currency} ({cur_symbol})"
            )
            return

        game_title = parts[0]
        target_price = float(parts[1])

        success = await add_alert(user_id, game_title, target_price, user_currency)
        if success:
            await message.answer(
                f"✅ Оповещение установлено!\n\n"
                f"🎮 {escape(game_title)}\n"
                f"💰 Целевая цена: {cur_symbol}{target_price} ({user_currency})\n\n"
                f"Уведомлю когда цена упадёт!"
            )
        else:
            await message.answer("❌ Не удалось установить оповещение. Попробуй снова.")

    except Exception as e:
        logger.error(f"Ошибка в /alert: {e}")


@router.message(Command("remove_alert"))
async def command_remove_alert_handler(message: types.Message) -> None:
    try:
        user_id = message.from_user.id
        args = message.text.split(maxsplit=1)

        if len(args) < 2:
            await message.answer("Укажи название игры: <code>/remove_alert Название</code>")
            return

        game_title = args[1]
        success = await remove_alert(user_id, game_title)

        if success:
            await message.answer(f"✅ Оповещение на <b>{escape(game_title)}</b> удалено.")
        else:
            await message.answer("❌ Оповещение не найдено.")

    except Exception as e:
        logger.error(f"Ошибка в /remove_alert: {e}")


# ─────────────── /premium ───────────────

@router.message(Command("premium"))
async def command_premium_handler(message: types.Message) -> None:
    try:
        profile = await get_user_profile(message.from_user.id)
        role = profile.get("role", "user") if profile else "user"

        if role in ("premium", "admin", "creator"):
            await message.answer("⭐ У тебя уже есть Premium! Спасибо за поддержку!")
            return

        await message.answer(
            "⭐ <b>Premium — $1/мес</b>\n\n"
            "<b>Бесплатно:</b>\n"
            "• 5 поисков в день\n"
            "• Просмотр цен\n\n"
            "<b>Premium:</b>\n"
            "• Безлимитные поиски\n"
            "• Оповещения о скидках\n"
            "• Приоритет в очереди\n\n"
            "Оплата: Telegram Stars\n\n"
            "Чтобы активировать, напиши /buy_premium"
        )

    except Exception as e:
        logger.error(f"Ошибка в /premium: {e}")


@router.message(Command("buy_premium"))
async def command_buy_premium_handler(message: types.Message) -> None:
    await message.answer(
        "⭐ <b>Покупка Premium</b>\n\n"
        "Стоимость: 25 Telegram Stars (~$1)\n\n"
        "Оплата скоро будет доступна!\n"
        "Следи за обновлениями."
    )


# ─────────────── /region — Региональные цены ───────────────

@router.message(Command("region"))
async def command_region_handler(message: types.Message) -> None:
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer(
                "🌍 <b>Цены по регионам</b>\n\n"
                "Покажет цены на игру в разных магазинах.\n\n"
                "<b>Использование:</b>\n"
                "• <code>/region Название игры</code> — все регионы\n"
                "• <code>/region Название игры регион</code> — конкретный регион\n\n"
                "<b>Регионы:</b> ru, us, de, uk, fr, it, global\n\n"
                "<b>Примеры:</b>\n"
                "• <code>/region Cyberpunk 2077</code>\n"
                "• <code>/region Cyberpunk 2077 ru</code>\n"
                "• <code>/region Cyberpunk 2077 global</code>"
            )
            return

        # Парсим: /region Game Title [region]
        parts = args[1].rsplit(maxsplit=1)
        filter_region = None

        # Проверяем, последний аргумент — это регион?
        from services import REGION_ALIASES
        if len(parts) == 2 and parts[1].lower() in REGION_ALIASES:
            game_title = parts[0]
            filter_region = REGION_ALIASES[parts[1].lower()]
        else:
            game_title = args[1]

        user_id = message.from_user.id
        profile = await get_user_profile(user_id)
        currency = profile.get("currency", "USD") if profile else "USD"
        cur_symbol = CURRENCIES.get(currency, currency)

        region_label = f" ({filter_region})" if filter_region else ""
        status_message = await message.answer(
            f"🌍 Ищу цены{region_label}: <b>{escape(game_title)}</b>..."
        )

        regional_prices = await get_regional_prices(game_title, currency, filter_region)

        if not regional_prices:
            await status_message.edit_text(
                f"❌ По запросу <b>{escape(game_title)}</b>{region_label} цены не найдены."
            )
            return

        # Если указан регион — показываем все предложения в этом регионе
        if filter_region:
            # Получаем все сделки для этого региона
            all_deals = await get_regional_deals(game_title, currency, filter_region)

            if not all_deals:
                await status_message.edit_text(
                    f"❌ По запросу <b>{escape(game_title)}</b> в регионе {filter_region} цены не найдены."
                )
                return

            region_name = ALL_REGIONS.get(filter_region, {}).get("name", filter_region)
            text = f"🌍 <b>{escape(game_title)}</b> — {region_name}\n\n"

            for i, deal in enumerate(all_deals[:15], 1):
                price = deal.get("price_converted") or deal.get("price_usd", "?")
                savings = deal.get("savings", 0)
                discount = f" (-{savings:.0f}%)" if savings > 0 else ""
                store = deal.get("store", "Магазин")
                link = deal.get("link", "#")

                text += f"<b>{i}. {store}</b>\n"
                text += f"    💰 <b>{cur_symbol}{price}</b>{discount}\n"
                text += f"    🔗 <a href=\"{link}\">Купить</a>\n\n"

            text += f"💰 <i>Всего предложений: {len(all_deals)}</i>"
        else:
            # Без фильтра — общая сводка по регионам
            text = f"🌍 <b>{escape(game_title)}</b>\n\n"

            for i, region in enumerate(regional_prices[:10], 1):
                price = region["best_price_converted"] or region["best_price_usd"]
                savings = region["savings"]
                discount = f" (-{savings:.0f}%)" if savings > 0 else ""

                text += (
                    f"<b>{i}. {region['region']}</b>\n"
                    f"    💰 <b>{cur_symbol}{price}</b> ({region['store']}){discount}\n"
                    f"    📊 Предложений: {region['total_deals']}\n\n"
                )

            text += "💰 <i>Сортировка: от дешёвых к дорогим</i>"

        await status_message.edit_text(text, disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Ошибка в /region: {e}")
        try:
            await message.answer("Произошла ошибка. Попробуй снова.")
        except Exception:
            pass


# ─────────────── /sub — Информация о подписках (выключено) ───────────────

# @router.message(Command("sub"))
# async def command_sub_handler(message: types.Message) -> None:
#     try:
#         args = message.text.split(maxsplit=1)
#         if len(args) < 2:
#             text = (
#                 "🎮 <b>Подписочные сервисы</b>\n\n"
#                 "Проверь, есть ли игра в подписке!\n\n"
#                 "Использование: <code>/sub Название игры</code>\n\n"
#                 "Пример: <code>/sub Cyberpunk 2077</code>\n\n"
#                 "<b>Поддерживаемые сервисы:</b>\n"
#             )
#             for key, service in SUBSCRIPTION_SERVICES.items():
#                 text += f"{service['emoji']} {service['name']}\n"
#
#             await message.answer(text)
#             return
#
#         game_title = args[1]
#
#         status_message = await message.answer(
#             f"🎮 Ищу информацию о подписках: <b>{escape(game_title)}</b>..."
#         )
#
#         # Онлайн-поиск + локальная база
#         result = await check_subscription(game_title)
#         subscriptions = result["subscriptions"]
#         found_online = result["found_online"]
#
#         if not subscriptions:
#             await status_message.edit_text(
#                 f"❌ <b>{escape(game_title)}</b> не найдена в подписках.\n\n"
#                 "Но ты можешь купить её со скидкой!\n"
#                 "Просто отправь название игры для поиска цен."
#             )
#             return
#
#         source_label = "🌐 (онлайн)" if found_online else "📦 (локальная база)"
#
#         text = f"🎮 <b>{escape(game_title)}</b> — найдено в подписках {source_label}:\n\n"
#
#         for sub in subscriptions:
#             service = sub.get("service", "")
#             # Определяем эмодзи по названию сервиса
#             if "PS Plus" in service:
#                 emoji = "🎮"
#             elif "Xbox" in service:
#                 emoji = "🟩"
#             elif "EA Play" in service:
#                 emoji = "🎯"
#             elif "Ubisoft" in service:
#                 emoji = "🏰"
#             else:
#                 emoji = "🎮"
#
#             text += f"{emoji} <b>{service}</b>\n"
#
#         text += "\n💡 <i>Проверь актуальность на сайте сервиса</i>"
#
#         await status_message.edit_text(text)
#
#     except Exception as e:
#         logger.error(f"Ошибка в /sub: {e}")
#         try:
#             await message.answer("Произошла ошибка. Попробуй снова.")
#         except Exception:
#             pass


# ─────────────── /support — Поддержать автора ───────────────

@router.message(Command("support"))
async def command_support_handler(message: types.Message) -> None:
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ 1 звезда", callback_data="support:1")],
            [InlineKeyboardButton(text="⭐⭐ 10 звёзд", callback_data="support:10")],
            [InlineKeyboardButton(text="⭐⭐⭐ 25 звёзд", callback_data="support:25")],
            [InlineKeyboardButton(text="💎 100 звёзд", callback_data="support:100")],
            [InlineKeyboardButton(text="✏️ Своя сумма", callback_data="support:custom")],
        ])

        await message.answer(
            "☕ <b>Поддержать автора</b>\n\n"
            "Если бот помог тебе сэкономить — можно угостить автора кофе!\n"
            "Каждая звезда помогает развивать бота.\n\n"
            "Выбери сумму или введи свою:",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Ошибка в /support: {e}")


@router.callback_query(lambda c: c.data.startswith("support:"))
async def callback_support(callback: types.CallbackQuery) -> None:
    try:
        amount = callback.data.split(":", 1)[1]

        if amount == "custom":
            await callback.message.edit_text(
                "✏️ <b>Своя сумма</b>\n\n"
                "Напиши количество звёзд числом.\n"
                "Пример: <code>50</code>"
            )
            await callback.answer()
            return

        # Отправляем инвойс через Telegram Stars
        from aiogram.types import LabeledPrice

        await callback.message.delete()

        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title="Поддержка бота PlayScan",
            description=f"Донат: {amount} звёзд. Спасибо за поддержку!",
            payload=f"support_{amount}",
            currency="XTR",
            prices=[LabeledPrice(label="Звёзды", amount=int(amount))],
        )

        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в support callback: {e}")
        await callback.answer("Ошибка при создании платежа", show_alert=True)


@router.message(lambda m: m.text and m.text.isdigit())
async def custom_support_handler(message: types.Message) -> None:
    """Обработка пользовательского ввода суммы для доната."""
    try:
        user_id = message.from_user.id
        profile = await get_user_profile(user_id)

        # Проверяем что это ответ на custom support
        # (если пользователь в чате, а не в инлайне)
        from aiogram.types import LabeledPrice

        amount = int(message.text)

        if amount < 1 or amount > 10000:
            await message.answer("Сумма должна быть от 1 до 10,000 звёзд.")
            return

        await message.delete()

        await message.bot.send_invoice(
            chat_id=user_id,
            title="Поддержка бота PlayScan",
            description=f"Донат: {amount} звёзд. Спасибо за поддержку!",
            payload=f"support_{amount}",
            currency="XTR",
            prices=[LabeledPrice(label="Звёзды", amount=amount)],
        )

    except Exception as e:
        logger.error(f"Ошибка в custom support: {e}")


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query) -> None:
    """Подтверждение платежа."""
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: types.Message) -> None:
    """Обработка успешного платежа."""
    amount = message.successful_payment.total_amount
    await message.answer(
        f"🎉 <b>Спасибо за поддержку!</b>\n\n"
        f"Ты отправил {amount} звёзд.\n"
        "Это помогает развивать бота и добавлять новые функции!"
    )


# ─────────────── /about — О боте ───────────────

@router.message(Command("about"))
async def command_about_handler(message: types.Message) -> None:
    try:
        await message.answer(
            "ℹ️ <b>PlayScan</b> v1.1\n\n"
            "Бот для поиска лучших цен на игры.\n"
            "Создан по заказу пользователей.\n\n"
            "<b>Возможности:</b>\n"
            "• Поиск цен на PC\n"
            "• Цены на PlayStation, Xbox, Nintendo\n"
            "• Цены по регионам\n"
            "• Оповещения о скидках\n\n"
            "<b>Автор:</b> John\n"
            "<b>Версия:</b> 1.1"
        )
    except Exception as e:
        logger.error(f"Ошибка в /about: {e}")


# ─────────────── /stores ───────────────

@router.message(Command("stores"))
async def command_stores_handler(message: types.Message) -> None:
    try:
        status = await message.answer("Загружаю список магазинов...")
        stores = await get_stores_list()
        if not stores:
            await status.edit_text("Не удалось загрузить список магазинов.")
            return

        active = [s for s in stores if s["active"]]
        text = "🏪 <b>Доступные магазины:</b>\n\n"
        for s in active:
            plat = PLATFORM_LABELS.get(s["platform"], s["platform"])
            text += f"• {escape(s['name'])} — {plat}\n"

        await status.edit_text(text, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Ошибка в /stores: {e}")
        try:
            await message.answer("Произошла ошибка при загрузке магазинов.")
        except Exception:
            pass


# ─────────────── /profile ───────────────

@router.message(Command("profile"))
async def command_profile_handler(message: types.Message) -> None:
    try:
        user_id = message.from_user.id
        profile = await get_user_profile(user_id)
        if not profile:
            await message.answer("Сначала отправь /start для регистрации.")
            return

        cur = profile["currency"]
        dev = profile["device"]
        region = profile.get("region", "global")
        role = profile.get("role", "user")
        cur_symbol = CURRENCIES.get(cur, cur)
        dev_label = PLATFORM_LABELS.get(dev, dev)

        ROLE_LABELS = {
            "user": "👤 Пользователь",
            "admin": "🛡️ Админ",
            "premium": "⭐ Премиум",
            "creator": "👑 Создатель",
        }
        role_label = ROLE_LABELS.get(role, role)

        # Получаем название региона
        from services import ALL_REGIONS
        region_info = ALL_REGIONS.get(region, ALL_REGIONS["global"])
        region_label = region_info["name"]

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💱 Валюта: {cur} ({cur_symbol})", callback_data="profile:currency")],
            [InlineKeyboardButton(text=f"📱 Устройство: {dev_label}", callback_data="profile:device")],
            [InlineKeyboardButton(text=f"🌍 Регион: {region_label}", callback_data="profile:region")],
        ])

        username = profile.get("username", "") if profile else ""
        username_display = f" ({username})" if username else ""

        await message.answer(
            f"👤 <b>Твой профиль{username_display}:</b>\n\n"
            f"💱 Валюта: <b>{cur}</b> ({cur_symbol})\n"
            f"📱 Устройство: <b>{dev_label}</b>\n"
            f"🌍 Регион: <b>{region_label}</b>\n\n"
            f"Нажми кнопку ниже, чтобы изменить.",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Ошибка в /profile: {e}")


@router.callback_query(lambda c: c.data == "profile:currency")
async def callback_profile_currency(callback: types.CallbackQuery) -> None:
    try:
        buttons = []
        row = []
        for code, symbol in CURRENCIES.items():
            row.append(InlineKeyboardButton(text=f"{code} ({symbol})", callback_data=f"set_currency:{code}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        await callback.message.edit_text(
            "💱 <b>Выбери валюту:</b>\n\nЦена будет показана в выбранной валюте рядом с USD.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    except Exception as e:
        logger.error(f"Ошибка в profile:currency: {e}")
    finally:
        await callback.answer()


@router.callback_query(lambda c: c.data.startswith("set_currency:"))
async def callback_set_currency(callback: types.CallbackQuery) -> None:
    try:
        currency = callback.data.split(":", 1)[1]
        if currency not in CURRENCIES:
            await callback.answer("Неизвестная валюта", show_alert=True)
            return
        await set_user_currency(callback.from_user.id, currency)
        symbol = CURRENCIES[currency]

        # Показываем профиль
        profile = await get_user_profile(callback.from_user.id)
        username = profile.get("username", "") if profile else ""
        username_display = f" ({username})" if username else ""

        cur = profile["currency"] if profile else "USD"
        dev = profile["device"] if profile else "all"
        region = profile.get("region", "global") if profile else "global"
        role = profile.get("role", "user") if profile else "user"
        cur_symbol = CURRENCIES.get(cur, cur)
        dev_label = PLATFORM_LABELS.get(dev, dev)

        ROLE_LABELS = {
            "user": "👤 Пользователь",
            "admin": "🛡️ Админ",
            "premium": "⭐ Премиум",
            "creator": "👑 Создатель",
        }
        role_label = ROLE_LABELS.get(role, role)

        from services import ALL_REGIONS
        region_info = ALL_REGIONS.get(region, ALL_REGIONS["global"])
        region_label = region_info["name"]

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💱 Валюта: {cur} ({cur_symbol})", callback_data="profile:currency")],
            [InlineKeyboardButton(text=f"📱 Устройство: {dev_label}", callback_data="profile:device")],
            [InlineKeyboardButton(text=f"🌍 Регион: {region_label}", callback_data="profile:region")],
        ])

        await callback.message.edit_text(
            f"✅ <b>Выбрано:</b> Валюта {currency} ({symbol})\n\n"
            f"👤 <b>Твой профиль{username_display}:</b>\n\n"
            f"💱 Валюта: <b>{cur}</b> ({cur_symbol})\n"
            f"📱 Устройство: <b>{dev_label}</b>\n"
            f"🌍 Регион: <b>{region_label}</b>\n\n"
            f"Нажми кнопку ниже, чтобы изменить.",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Ошибка в set_currency: {e}")
    finally:
        await callback.answer()


@router.callback_query(lambda c: c.data == "profile:device")
async def callback_profile_device(callback: types.CallbackQuery) -> None:
    try:
        buttons = [
            [InlineKeyboardButton(text=label, callback_data=f"set_device:{key}")]
            for key, label in PLATFORM_LABELS.items()
        ]
        await callback.message.edit_text(
            "📱 <b>Выбери платформу:</b>\n\nБот будет показывать цены только для выбранной платформы.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    except Exception as e:
        logger.error(f"Ошибка в profile:device: {e}")
    finally:
        await callback.answer()


@router.callback_query(lambda c: c.data.startswith("set_device:"))
async def callback_set_device(callback: types.CallbackQuery) -> None:
    try:
        device = callback.data.split(":", 1)[1]
        if device not in DEVICES:
            await callback.answer("Неизвестное устройство", show_alert=True)
            return
        await set_user_device(callback.from_user.id, device)
        label = PLATFORM_LABELS.get(device, device)

        # Показываем профиль
        profile = await get_user_profile(callback.from_user.id)
        username = profile.get("username", "") if profile else ""
        username_display = f" ({username})" if username else ""

        cur = profile["currency"] if profile else "USD"
        dev = profile["device"] if profile else "all"
        region = profile.get("region", "global") if profile else "global"
        role = profile.get("role", "user") if profile else "user"
        cur_symbol = CURRENCIES.get(cur, cur)
        dev_label = PLATFORM_LABELS.get(dev, dev)

        ROLE_LABELS = {
            "user": "👤 Пользователь",
            "admin": "🛡️ Админ",
            "premium": "⭐ Премиум",
            "creator": "👑 Создатель",
        }
        role_label = ROLE_LABELS.get(role, role)

        from services import ALL_REGIONS
        region_info = ALL_REGIONS.get(region, ALL_REGIONS["global"])
        region_label = region_info["name"]

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💱 Валюта: {cur} ({cur_symbol})", callback_data="profile:currency")],
            [InlineKeyboardButton(text=f"📱 Устройство: {dev_label}", callback_data="profile:device")],
            [InlineKeyboardButton(text=f"🌍 Регион: {region_label}", callback_data="profile:region")],
        ])

        await callback.message.edit_text(
            f"✅ <b>Выбрано:</b> Платформа {label}\n\n"
            f"👤 <b>Твой профиль{username_display}:</b>\n\n"
            f"💱 Валюта: <b>{cur}</b> ({cur_symbol})\n"
            f"📱 Устройство: <b>{dev_label}</b>\n"
            f"🌍 Регион: <b>{region_label}</b>\n\n"
            f"Нажми кнопку ниже, чтобы изменить.",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Ошибка в set_device: {e}")
    finally:
        await callback.answer()


# ─────────────── Регион ───────────────

@router.callback_query(lambda c: c.data == "profile:region")
async def callback_profile_region(callback: types.CallbackQuery) -> None:
    try:
        from services import ALL_REGIONS

        buttons = []
        row = []
        for key, info in ALL_REGIONS.items():
            row.append(InlineKeyboardButton(text=info["name"], callback_data=f"set_region:{key}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        await callback.message.edit_text(
            "🌍 <b>Выбери регион:</b>\n\nЦены будут показаны для магазинов твоего региона.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    except Exception as e:
        logger.error(f"Ошибка в profile:region: {e}")
    finally:
        await callback.answer()


@router.callback_query(lambda c: c.data.startswith("set_region:"))
async def callback_set_region(callback: types.CallbackQuery) -> None:
    try:
        from services import ALL_REGIONS

        region = callback.data.split(":", 1)[1]
        if region not in ALL_REGIONS:
            await callback.answer("Неизвестный регион", show_alert=True)
            return

        await set_user_region(callback.from_user.id, region)
        region_name = ALL_REGIONS[region]["name"]

        # Показываем профиль
        profile = await get_user_profile(callback.from_user.id)
        username = profile.get("username", "") if profile else ""
        username_display = f" ({username})" if username else ""

        cur = profile["currency"] if profile else "USD"
        dev = profile["device"] if profile else "all"
        region = profile.get("region", "global") if profile else "global"
        role = profile.get("role", "user") if profile else "user"
        cur_symbol = CURRENCIES.get(cur, cur)
        dev_label = PLATFORM_LABELS.get(dev, dev)

        ROLE_LABELS = {
            "user": "👤 Пользователь",
            "admin": "🛡️ Админ",
            "premium": "⭐ Премиум",
            "creator": "👑 Создатель",
        }
        role_label = ROLE_LABELS.get(role, role)

        region_info = ALL_REGIONS.get(region, ALL_REGIONS["global"])
        region_label = region_info["name"]

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💱 Валюта: {cur} ({cur_symbol})", callback_data="profile:currency")],
            [InlineKeyboardButton(text=f"📱 Устройство: {dev_label}", callback_data="profile:device")],
            [InlineKeyboardButton(text=f"🌍 Регион: {region_label}", callback_data="profile:region")],
        ])

        await callback.message.edit_text(
            f"✅ <b>Выбрано:</b> Регион {region_name}\n\n"
            f"👤 <b>Твой профиль{username_display}:</b>\n\n"
            f"💱 Валюта: <b>{cur}</b> ({cur_symbol})\n"
            f"📱 Устройство: <b>{dev_label}</b>\n"
            f"🌍 Регион: <b>{region_label}</b>\n\n"
            f"Нажми кнопку ниже, чтобы изменить.",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Ошибка в set_region: {e}")
    finally:
        await callback.answer()


# ─────────────── Поиск игр ───────────────

@router.callback_query(lambda c: c.data.startswith("search:"))
async def callback_search_again(callback: types.CallbackQuery) -> None:
    """Кнопка 'назад к поиску'."""
    try:
        query = callback.data.split(":", 1)[1]
        await callback.answer("Ищу снова...")
        profile = await get_user_profile(callback.from_user.id)
        currency = profile["currency"] if profile else "USD"
        device = profile["device"] if profile else "all"

        # Гибридный подход: сначала PlayFetch, потом CheapShark
        deals = []

        # Сначала пробуем PlayFetch (Steam, PS, Xbox, GOG, Nintendo)
        try:
            pf_deals = await search_playfetch(query, user_region=profile.get("region", "us"), device=device, target_currency=currency)
            if pf_deals:
                deals.extend(pf_deals)
                logger.info(f"PlayFetch found {len(pf_deals)} deals for {query}")
        except Exception as e:
            logger.warning(f"PlayFetch failed for {query}: {e}")

        # CheapShark для PC магазинов (Humble, Fanatical, Epic и т.д.)
        # Всегда добавляем CheapShark результаты для PC
        try:
            cs_deals = await search_deals(query, limit=50, target_currency=currency, target_platform="pc")
            # Добавляем только те, которых нет в PlayFetch (для дедупликации)
            existing_titles = {d["title"].lower() for d in deals}
            for d in cs_deals:
                if d["title"].lower() not in existing_titles:
                    deals.append(d)
            if cs_deals:
                logger.info(f"CheapShark found {len(cs_deals)} deals for {query}")
        except Exception as e:
            logger.warning(f"CheapShark failed for {query}: {e}")

        if not deals:
            await callback.message.edit_text(f"❌ По запросу <b>{escape(query)}</b> ничего не найдено.")
            return

        # Формируем результат (без медленного обогащения ссылками)
        full_text = _format_deals_list(deals, query, currency)
        chunks = _chunk_text(full_text)

        if len(chunks) == 1:
            await callback.message.edit_text(chunks[0], disable_web_page_preview=True)
        else:
            await callback.message.edit_text(chunks[0], disable_web_page_preview=True)
            for chunk in chunks[1:]:
                await callback.message.answer(chunk, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Ошибка в search callback: {e}")
        try:
            await callback.message.edit_text("Произошла ошибка при поиске. Попробуй снова.")
        except Exception:
            pass
        await callback.answer()


@router.message()
async def search_game_handler(message: types.Message) -> None:
    game_query = message.text.strip()
    if not game_query:
        await message.answer("Введите название игры для поиска.")
        return

    status_message = None
    try:
        user_id = message.from_user.id
        profile = await get_user_profile(user_id)
        currency = profile["currency"] if profile else "USD"
        device = profile["device"] if profile else "all"

        status_message = await message.answer(
            f"🔍 Ищу: <b>{escape(game_query)}</b>...",
        )

        # Гибридный подход: сначала PlayFetch, потом CheapShark
        deals = []

        # Сначала пробуем PlayFetch (Steam, PS, Xbox, GOG, Nintendo)
        try:
            pf_deals = await search_playfetch(game_query, user_region=profile.get("region", "us"), device=device, target_currency=currency)
            if pf_deals:
                deals.extend(pf_deals)
                logger.info(f"PlayFetch found {len(pf_deals)} deals for {game_query}")
        except Exception as e:
            logger.warning(f"PlayFetch failed for {game_query}: {e}")

        # CheapShark для PC магазинов (Humble, Fanatical, Epic и т.д.)
        # Всегда добавляем CheapShark результаты для PC
        try:
            cs_deals = await search_deals(game_query, limit=50, target_currency=currency, target_platform="pc")
            # Добавляем только те, которых нет в PlayFetch (для дедупликации)
            existing_titles = {d["title"].lower() for d in deals}
            for d in cs_deals:
                if d["title"].lower() not in existing_titles:
                    deals.append(d)
            if cs_deals:
                logger.info(f"CheapShark found {len(cs_deals)} deals for {game_query}")
        except Exception as e:
            logger.warning(f"CheapShark failed for {game_query}: {e}")

        if not deals:
            games = await search_games(game_query, limit=10)
            if not games:
                await status_message.edit_text(
                    f"❌ По запросу <b>{escape(game_query)}</b> ничего не найдено.",
                )
                return

            text = f"🎮 <b>Найденные игры:</b> {escape(game_query)}\n\n"
            buttons = []
            for i, game in enumerate(games, 1):
                text += f"{i}. {escape(game['title'])} — от <b>${game['cheapest']}</b>\n\n"
                buttons.append([
                    InlineKeyboardButton(text=f"📊 {game['title'][:40]}", callback_data=f"search:{game['title']}")
                ])

            await status_message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
            return

        # Формируем результат (без медленного обогащения ссылками)
        full_text = _format_deals_list(deals, game_query, currency)
        chunks = _chunk_text(full_text)

        if len(chunks) == 1:
            await status_message.edit_text(chunks[0], disable_web_page_preview=True)
        else:
            await status_message.edit_text(chunks[0], disable_web_page_preview=True)
            for chunk in chunks[1:]:
                await message.answer(chunk, disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Ошибка при поиске '{game_query}': {e}")
        if status_message:
            try:
                await status_message.edit_text("Произошла ошибка при поиске. Попробуй снова.")
            except Exception:
                pass
        else:
            try:
                await message.answer("Произошла ошибка при поиске. Попробуй снова.")
            except Exception:
                pass
