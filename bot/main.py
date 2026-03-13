import logging
import os
import re
from datetime import datetime, timezone
import requests
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
ALERT_CHAT_ID = os.getenv("ALERT_CHAT_ID", "")
STATE_KEY = "state"
STATE_IDLE = "idle"
STATE_WAIT_MESSAGE = "wait_message"
STATE_WAIT_FIRST_PERIOD = "wait_first_period"
DRAFT_MESSAGE_KEY = "draft_message_text"
DEFAULT_SECOND_DELAY_SECONDS = 3 * 60 * 60
DEFAULT_THIRD_DELAY_SECONDS = 1 * 60 * 60
OK_CANONICAL_TEXT = "Я в порядке"
OK_NORMALIZED_VARIANTS = {"я в порядке", "я впорядке", "явпорядке"}

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

def start_text(first_name: str) -> str:
    return (
        f"Здравствуйте, {first_name}! Вас приветствует бот mDelay!\n\n"
        "Если Вы собираетесь в опасное путешествие или в подозрительное место, "
        "Вы можете оставить сообщение, которое поможет Вас найти в случае непредвиденной ситуации "
        "или при отсутствии у Вас связи.\n\n"
        "Через определенное время бот спросит, как у Вас дела.\n\n"
        "Если Вы ответите на любой из запросов фразой \"Я в порядке\", бот прекратит следить за данным сообщением.\n\n"
        "Если Вы ответите что-то другое, бот сразу передаст сообщение службе спасения.\n\n"
        "Если Вы не ответите на все три запроса, бот передаст исходное сообщение службе спасения.\n\n"
        "Удачи Вам! Не теряйтесь - кому-то может быть без Вас грустно!\n\n"
    )

def api_get(path: str, params: dict | None = None) -> requests.Response:
    return requests.get(f"{API_BASE_URL}{path}", params=params, timeout=15)

def api_post(path: str, payload: dict) -> requests.Response:
    return requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=15)

def api_delete(path: str, params: dict | None = None) -> requests.Response:
    return requests.delete(f"{API_BASE_URL}{path}", params=params, timeout=15)

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["Написать новое сообщение"],
            ["Прочитать свои сообщения"],
        ],
        resize_keyboard=True,
    )

def flow_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["Назад в главное меню"]], resize_keyboard=True)

def first_period_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["Первый опрос через 1 час", "Первый опрос через 3 часа"],
            ["Первый опрос через 6 часов", "Первый опрос через 10 часов"],
            ["Первый опрос через 24 часа", "Первый опрос через 3 дня"],
            ["Первый опрос через 7 дней"],
            ["Тест: все опросы через 1 минуту"],
            ["Назад в главное меню"],
        ],
        resize_keyboard=True,
    )

def parse_first_period_choice(text: str) -> tuple[int, int, int, str] | None:
    if text == "Первый опрос через 1 час":
        return 1 * 60 * 60, DEFAULT_SECOND_DELAY_SECONDS, DEFAULT_THIRD_DELAY_SECONDS, "Реальный"
    if text == "Первый опрос через 3 часа":
        return 3 * 60 * 60, DEFAULT_SECOND_DELAY_SECONDS, DEFAULT_THIRD_DELAY_SECONDS, "Реальный"
    if text == "Первый опрос через 6 часов":
        return 6 * 60 * 60, DEFAULT_SECOND_DELAY_SECONDS, DEFAULT_THIRD_DELAY_SECONDS, "Реальный"
    if text == "Первый опрос через 10 часов":
        return 10 * 60 * 60, DEFAULT_SECOND_DELAY_SECONDS, DEFAULT_THIRD_DELAY_SECONDS, "Реальный"
    if text == "Первый опрос через 24 часа":
        return 24 * 60 * 60, DEFAULT_SECOND_DELAY_SECONDS, DEFAULT_THIRD_DELAY_SECONDS, "Реальный"
    if text == "Первый опрос через 3 дня":
        return 3 * 24 * 60 * 60, DEFAULT_SECOND_DELAY_SECONDS, DEFAULT_THIRD_DELAY_SECONDS, "Реальный"
    if text == "Первый опрос через 7 дней":
        return 7 * 24 * 60 * 60, DEFAULT_SECOND_DELAY_SECONDS, DEFAULT_THIRD_DELAY_SECONDS, "Реальный"
    if text == "Тест: все опросы через 1 минуту":
        return 60, 60, 60, "Тестовый"
    return None

def message_delete_keyboard(message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Удалить", callback_data=f"msg_delete:{message_id}")]])

def confirm_delete_keyboard(message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Подтвердить", callback_data=f"msg_delete_confirm:{message_id}"),
            InlineKeyboardButton("Отмена", callback_data=f"msg_delete_cancel:{message_id}"),
        ]]
    )

def ensure_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    if STATE_KEY not in context.user_data:
        context.user_data[STATE_KEY] = STATE_IDLE

def message_tracking_status(item: dict) -> str:
    is_finished = item.get("check3_res") == "ESCALATED" or any(
        item.get(field) == "Я в порядке" for field in ("check1_res", "check2_res", "check3_res")
    )
    return "Завершено" if is_finished else "Выполняется"

def message_result_status(item: dict) -> str:
    if any(item.get(field) == "Я в порядке" for field in ("check1_res", "check2_res", "check3_res")):
        return "Порядок"
    if item.get("check3_res") == "ESCALATED":
        return "Тревога"
    return "-"

def format_api_datetime(value: str | None) -> str:
    if not value:
        return "-"
    raw = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%d.%m.%Y %H:%M:%S")

def normalize_ok_input(value: str) -> str:
    normalized = value.strip().lower().replace("ё", "е")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.strip(" .,!?:;\"'`~+-=_()[]{}<>")
    return normalized

def is_ok_text(value: str) -> bool:
    return normalize_ok_input(value) in OK_NORMALIZED_VARIANTS

def is_test_period_message(recorded: dict) -> bool:
    if recorded.get("message_mode") == "Тестовый":
        return True
    return (
        int(recorded.get("check1_delay_seconds") or 0) == 60
        and int(recorded.get("check2_delay_seconds") or 0) == 60
        and int(recorded.get("check3_delay_seconds") or 0) == 60
    )

async def send_emergency_now(
    context: ContextTypes.DEFAULT_TYPE,
    user,
    recorded: dict,
    response_text: str,
) -> None:
    if not ALERT_CHAT_ID:
        raise RuntimeError("ALERT_CHAT_ID is not set")
    username_text = f"@{user.username}" if user and user.username else "-"
    full_name = " ".join(x for x in [(user.first_name if user else ""), (user.last_name if user else "")] if x) or "Пользователь"
    created_text = format_api_datetime(recorded.get("timecreated"))
    mode_text = "РЕЖИМ: ТЕСТОВЫЙ (все периоды по 1 минуте)\n\n" if is_test_period_message(recorded) else ""
    alert_text = (
        "АВАРИЙНОЕ СООБЩЕНИЕ\n\n"
        f"{mode_text}"
        f"ID сообщения: {recorded.get('id')}\n"
        f"User id: {user.id if user else '-'}\n"
        f"Username: {username_text}\n"
        f"Имя: {full_name}\n\n"
        f"Время создания сообщения: {created_text}\n\n"
        f"Текст сообщения:\n{recorded.get('message', '')}\n\n"
        f"Ответ пользователя:\n{response_text}"
    )
    await context.bot.send_message(chat_id=ALERT_CHAT_ID, text=alert_text)

async def try_submit_check_response(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    user = update.effective_user
    if not user:
        return False
    active_response = api_get(f"/api/users/{user.id}/active-check")
    if active_response.status_code == 404:
        return False
    if not active_response.ok:
        raise RuntimeError(f"active-check status {active_response.status_code}")
    submit_response_call = api_post("/api/messages/response", {"user_id": user.id, "response_text": text})
    if not submit_response_call.ok:
        raise RuntimeError(f"response submit status {submit_response_call.status_code}")
    recorded = submit_response_call.json()
    created_text = format_api_datetime(recorded.get("timecreated"))
    if recorded.get("check3_res") == "ESCALATED":
        try:
            await send_emergency_now(context, user, recorded, text)
            await update.message.reply_text(
                "Ответ на проверку сохранен.\n"
                "Ответ отличается от \"Я в порядке\", аварийное сообщение отправлено в службу спасения.\n\n"
                f"id сообщения: {recorded.get('id')}\n"
                f"Время создания: {created_text}\n"
                f"Ваш ответ: {text}",
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            logger.exception("Failed to send immediate emergency alert")
            await update.message.reply_text(
                "Ответ на проверку сохранен, но аварийное сообщение пока не отправилось.",
                reply_markup=main_menu_keyboard(),
            )
        return True
    await update.message.reply_text(
        "Принято. Вы в порядке.\n"
        "Бот прекращает следить за этим сообщением.\n\n"
        f"Время создания: {created_text}\n"
        f"Исходное сообщение: {recorded.get('message', '')}\n",
        reply_markup=main_menu_keyboard(),
    )
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_state(context)
    context.user_data[STATE_KEY] = STATE_IDLE
    user = update.effective_user
    first_name = (user.first_name if user else None) or "<Ваше имя не распознано>"
    await update.message.reply_text(
        start_text(first_name),
        reply_markup=main_menu_keyboard(),
    )

async def show_user_messages(update: Update) -> None:
    user = update.effective_user
    if not user:
        await update.message.reply_text("Не удалось определить пользователя.", reply_markup=main_menu_keyboard())
        return
    try:
        response = api_get("/api/messages", params={"user_id": user.id})
        if not response.ok:
            raise RuntimeError(f"api status {response.status_code}")
        items = response.json()
        if not items:
            await update.message.reply_text("У вас пока нет сохраненных сообщений.", reply_markup=main_menu_keyboard())
            return
        await update.message.reply_text(f"Ваши сообщения ({len(items)}):", reply_markup=main_menu_keyboard())
        for idx, item in enumerate(items, start=1):
            tracking = message_tracking_status(item)
            result = message_result_status(item)
            text = (
                f"{idx}. Текст: {item.get('message', '')}\n"
                f"Время отправки: {format_api_datetime(item.get('timecreated'))}\n"
                f"Слежение: {tracking}\n"
                f"Результат: {result}"
            )
            await update.message.reply_text(text, reply_markup=message_delete_keyboard(item["id"]))
    except Exception:
        logger.exception("Failed to load messages")
        await update.message.reply_text("Не удалось прочитать сообщения из базы.", reply_markup=main_menu_keyboard())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_state(context)
    text = (update.message.text or "").strip()
    state = context.user_data.get(STATE_KEY, STATE_IDLE)
    is_ok_phrase = is_ok_text(text)
    if text == "Назад в главное меню":
        context.user_data[STATE_KEY] = STATE_IDLE
        context.user_data.pop(DRAFT_MESSAGE_KEY, None)
        await update.message.reply_text("Главное меню:", reply_markup=main_menu_keyboard())
        return
    if text == "Написать новое сообщение":
        context.user_data[STATE_KEY] = STATE_WAIT_MESSAGE
        context.user_data.pop(DRAFT_MESSAGE_KEY, None)
        await update.message.reply_text("Введите текст одним сообщением.", reply_markup=flow_keyboard())
        return
    if text == "Прочитать свои сообщения":
        context.user_data[STATE_KEY] = STATE_IDLE
        await show_user_messages(update)
        return
    if state == STATE_IDLE:
        if is_ok_phrase:
            try:
                accepted = await try_submit_check_response(update, context, OK_CANONICAL_TEXT)
                if accepted:
                    return
                await update.message.reply_text("Нет активной проверки для подтверждения.", reply_markup=main_menu_keyboard())
                return
            except Exception:
                logger.exception("Failed to submit check response")
                await update.message.reply_text("Не удалось обработать ответ.", reply_markup=main_menu_keyboard())
                return
        try:
            accepted = await try_submit_check_response(update, context, text)
            if accepted:
                return
        except Exception:
            logger.exception("Failed to submit check response")
            await update.message.reply_text("Не удалось отправить ответ на проверку.", reply_markup=main_menu_keyboard())
            return
    if state == STATE_WAIT_MESSAGE:
        user = update.effective_user
        if not user:
            await update.message.reply_text("Не удалось определить пользователя.", reply_markup=main_menu_keyboard())
            context.user_data[STATE_KEY] = STATE_IDLE
            return
        if not text:
            await update.message.reply_text("Пустой текст. Введите сообщение еще раз.")
            return
        context.user_data[DRAFT_MESSAGE_KEY] = text
        context.user_data[STATE_KEY] = STATE_WAIT_FIRST_PERIOD
        await update.message.reply_text(
            "Выберите период до первого опроса.\n"
            "Второй опрос будет через 3 часа после первого, третий - еще через 1 час.",
            reply_markup=first_period_keyboard(),
        )
        return
    if state == STATE_WAIT_FIRST_PERIOD:
        user = update.effective_user
        if not user:
            await update.message.reply_text("Не удалось определить пользователя.", reply_markup=main_menu_keyboard())
            context.user_data[STATE_KEY] = STATE_IDLE
            context.user_data.pop(DRAFT_MESSAGE_KEY, None)
            return
        period = parse_first_period_choice(text)
        if period is None:
            await update.message.reply_text("Выберите один из вариантов периода кнопками ниже.", reply_markup=first_period_keyboard())
            return
        draft_message = context.user_data.get(DRAFT_MESSAGE_KEY, "").strip()
        if not draft_message:
            context.user_data[STATE_KEY] = STATE_IDLE
            await update.message.reply_text("Текст сообщения не найден. Введите сообщение заново.", reply_markup=main_menu_keyboard())
            return
        try:
            sent_at = (update.message.date if update.message else None) or datetime.now(timezone.utc)
            check1_delay, check2_delay, check3_delay, message_mode = period
            response = api_post(
                "/api/messages",
                {
                    "user_id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "message": draft_message,
                    "message_mode": message_mode,
                    "check1_delay_seconds": check1_delay,
                    "check2_delay_seconds": check2_delay,
                    "check3_delay_seconds": check3_delay,
                },
            )
            if not response.ok:
                raise RuntimeError(f"api status {response.status_code}")
            context.user_data[STATE_KEY] = STATE_IDLE
            context.user_data.pop(DRAFT_MESSAGE_KEY, None)
            sender_username = f"@{user.username}" if user.username else "-"
            sender_name = " ".join(x for x in [user.first_name, user.last_name] if x) or "Пользователь"
            await update.message.reply_text(
                "Сообщение сохранено.\n\n"
                f"Текст: {draft_message}\n"
                f"Отправитель: {sender_name} (username: {sender_username}, id: {user.id})\n"
                f"Время отправки: {sent_at.astimezone().strftime('%d.%m.%Y %H:%M:%S')}",
                reply_markup=main_menu_keyboard(),
            )
            return
        except Exception:
            logger.exception("Failed to create message")
            await update.message.reply_text("Не удалось сохранить сообщение в базу.", reply_markup=main_menu_keyboard())
            context.user_data[STATE_KEY] = STATE_IDLE
            context.user_data.pop(DRAFT_MESSAGE_KEY, None)
            return
    await update.message.reply_text("Используйте кнопки меню.", reply_markup=main_menu_keyboard())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    data = query.data or ""
    if data.startswith("msg_delete:"):
        try:
            message_id = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer("Некорректный идентификатор сообщения.", show_alert=True)
            return
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=confirm_delete_keyboard(message_id))
        return
    if data.startswith("msg_delete_cancel:"):
        try:
            message_id = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer("Некорректный идентификатор сообщения.", show_alert=True)
            return
        await query.answer("Удаление отменено.")
        await query.edit_message_reply_markup(reply_markup=message_delete_keyboard(message_id))
        return
    if not data.startswith("msg_delete_confirm:"):
        await query.answer()
        return
    user = query.from_user
    if not user:
        await query.answer("Не удалось определить пользователя.", show_alert=True)
        return
    try:
        message_id = int(data.split(":", 1)[1])
    except ValueError:
        await query.answer("Некорректный идентификатор сообщения.", show_alert=True)
        return
    try:
        response = api_delete(f"/api/messages/{message_id}", params={"user_id": user.id})
        if response.status_code == 204:
            await query.answer("Сообщение удалено.")
            try:
                await query.message.delete()
            except Exception:
                await query.edit_message_reply_markup(reply_markup=None)
                await query.edit_message_text("Сообщение удалено.")
            return
        if response.status_code == 404:
            await query.answer("Сообщение не найдено или уже удалено.", show_alert=True)
            return
        await query.answer("Не удалось удалить сообщение.", show_alert=True)
    except Exception:
        logger.exception("Failed to delete message")
        await query.answer("Не удалось удалить сообщение.", show_alert=True)

async def setup_bot_commands(application: Application) -> None:
    try:
        await application.bot.set_my_commands([BotCommand("start", "Главное меню")])
    except Exception:
        logger.exception("Failed to set bot commands")

def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")
    app = Application.builder().token(token).post_init(setup_bot_commands).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Bot is starting polling...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
