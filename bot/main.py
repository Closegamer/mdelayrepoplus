import logging
import os
import requests
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
STATE_KEY = "state"
STATE_IDLE = "idle"
STATE_WAIT_MESSAGE = "wait_message"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

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

def message_delete_keyboard(message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Удалить", callback_data=f"msg_delete:{message_id}")]])

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

async def try_submit_check_response(update: Update, text: str) -> bool:
    user = update.effective_user
    if not user:
        return False
    active_response = api_get(f"/api/users/{user.id}/active-check")
    if active_response.status_code == 404:
        return False
    if not active_response.ok:
        raise RuntimeError(f"active-check status {active_response.status_code}")
    submit_response = api_post("/api/messages/response", {"user_id": user.id, "response_text": text})
    if not submit_response.ok:
        raise RuntimeError(f"response submit status {submit_response.status_code}")
    await update.message.reply_text("Ответ принят. Спасибо.", reply_markup=main_menu_keyboard())
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_state(context)
    context.user_data[STATE_KEY] = STATE_IDLE
    await update.message.reply_text(
        "Здравствуйте! mDelayPlusBot запущен.\nВыберите действие в меню.",
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
    if text == "Написать новое сообщение":
        context.user_data[STATE_KEY] = STATE_WAIT_MESSAGE
        await update.message.reply_text("Введите текст одним сообщением.", reply_markup=main_menu_keyboard())
        return
    if text == "Прочитать свои сообщения":
        context.user_data[STATE_KEY] = STATE_IDLE
        await show_user_messages(update)
        return
    if state == STATE_IDLE:
        try:
            accepted = await try_submit_check_response(update, text)
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
        try:
            response = api_post(
                "/api/messages",
                {
                    "user_id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "message": text,
                },
            )
            if not response.ok:
                raise RuntimeError(f"api status {response.status_code}")
            context.user_data[STATE_KEY] = STATE_IDLE
            await update.message.reply_text("Сообщение сохранено.", reply_markup=main_menu_keyboard())
            return
        except Exception:
            logger.exception("Failed to create message")
            await update.message.reply_text("Не удалось сохранить сообщение.", reply_markup=main_menu_keyboard())
            context.user_data[STATE_KEY] = STATE_IDLE
            return
    await update.message.reply_text("Используйте /start или кнопки меню.", reply_markup=main_menu_keyboard())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    if not data.startswith("msg_delete:"):
        return
    try:
        message_id = int(data.split(":", 1)[1])
    except ValueError:
        await query.edit_message_text("Некорректный идентификатор сообщения.")
        return
    user = query.from_user
    try:
        response = api_delete(f"/api/messages/{message_id}", params={"user_id": user.id})
        if response.status_code == 204:
            await query.edit_message_text("Сообщение удалено.")
            return
        if response.status_code == 404:
            await query.edit_message_text("Сообщение не найдено или уже удалено.")
            return
        await query.edit_message_text("Не удалось удалить сообщение.")
    except Exception:
        logger.exception("Failed to delete message")
        await query.edit_message_text("Ошибка удаления сообщения.")

async def setup_bot_commands(application: Application) -> None:
    try:
        await application.bot.set_my_commands([BotCommand("start", "Запуск главного меню")])
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
