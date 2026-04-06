import logging
import os
import re
import inspect
from html import escape
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests
from telegram import BotCommand, BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update, User
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Лимит длины одного текстового сообщения в Telegram API
TELEGRAM_MESSAGE_MAX_CHARS = 4096

# Безопасное чтение числовых переменных окружения для конфигурации polling
def get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer value for %s=%r, fallback to %s", name, raw, default)
        return default

# Необязательный числовой идентификатор из окружения (личный chat_id в Telegram = user id)
def get_env_optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning("Invalid integer value for %s=%r, ignored", name, raw)
        return None

# Безопасное чтение float переменных окружения
def get_env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid float value for %s=%r, fallback to %s", name, raw, default)
        return default

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
ALERT_CHAT_ID = os.getenv("ALERT_CHAT_ID", "")
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
POLLING_TIMEOUT_SECONDS = get_env_int("BOT_POLLING_TIMEOUT_SECONDS", 30)
POLLING_READ_TIMEOUT_SECONDS = get_env_int("BOT_POLLING_READ_TIMEOUT_SECONDS", 35)
POLLING_CONNECT_TIMEOUT_SECONDS = get_env_int("BOT_POLLING_CONNECT_TIMEOUT_SECONDS", 10)
POLLING_POOL_TIMEOUT_SECONDS = get_env_int("BOT_POLLING_POOL_TIMEOUT_SECONDS", 10)
POLLING_INTERVAL_SECONDS = get_env_float("BOT_POLLING_INTERVAL_SECONDS", 1.0)
STATE_KEY = "state"
STATE_IDLE = "idle"
STATE_WAIT_MESSAGE = "wait_message"
STATE_WAIT_FIRST_PERIOD = "wait_first_period"
STATE_WAIT_FEEDBACK = "wait_feedback"
DRAFT_MESSAGE_KEY = "draft_message_text"
DEFAULT_SECOND_DELAY_SECONDS = 1 * 60 * 60
DEFAULT_THIRD_DELAY_SECONDS = 1 * 60 * 60
ARCHITECT_USER_ID = 227287028
NASTAVNIK_USERNAME = "KayumovRU"
# Для пункта /readme в меню Telegram у наставника (в личке chat_id = user id). Кнопка «Наставник» работает и без этого.
NASTAVNIK_USER_ID = get_env_optional_int("NASTAVNIK_USER_ID")
NASTAVNIK_BUTTON_LABEL = "Наставник"
OK_CANONICAL_TEXT = "Я в порядке"
OK_NORMALIZED_VARIANTS = {"я в порядке", "я впорядке", "явпорядке"}
LATIN_TO_CYRILLIC_SIMILAR = str.maketrans(
    {
        "a": "а",
        "e": "е",
        "o": "о",
        "p": "р",
        "c": "с",
        "y": "у",
        "x": "х",
        "k": "к",
        "m": "м",
        "t": "т",
        "b": "в",
        "h": "н",
    }
)

# Формирование приветственного текста для команды /start
def start_text(first_name: str) -> str:
    safe_first_name = escape(first_name)
    return (
        f"Здравствуйте, {safe_first_name}! Вас приветствует бот KakDelaTorBot!\n\n"
        "Если Вы собираетесь в опасное путешествие или в подозрительное место, "
        "Вы можете оставить сообщение, которое поможет Вас найти в случае непредвиденной ситуации "
        "или при отсутствии у Вас связи.\n\n"
        "Через определенное время бот спросит, как у Вас дела.\n\n"
        "Если Вы ответите на любой из запросов фразой \"Я в порядке\", бот прекратит следить за данным сообщением.\n\n"
        "Если Вы ответите что-то другое, бот сразу передаст сообщение службе спасения.\n\n"
        "Если Вы не ответите на все три запроса, бот передаст исходное сообщение службе спасения.\n\n"
        "Удачи Вам! Не теряйтесь - кому-то может быть без Вас грустно!\n\n"
        "Начиная использовать бота, Вы соглашаетесь с Политикой конфиденциальности.\n"
        "Открыть ее можно соответствующей кнопкой в меню.\n\n"
    )

# Выполнение GET запроса к API
def api_get(path: str, params: dict | None = None) -> requests.Response:
    return requests.get(f"{API_BASE_URL}{path}", params=params, timeout=15)

# Выполнение POST запроса к API
def api_post(path: str, payload: dict) -> requests.Response:
    return requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=15)

# Выполнение DELETE запроса к API
def api_delete(path: str, params: dict | None = None) -> requests.Response:
    return requests.delete(f"{API_BASE_URL}{path}", params=params, timeout=15)

# Чтение текста политики конфиденциальности
def read_privacy_policy_text() -> str:
    policy_path = Path(__file__).resolve().parents[1] / "PRIVACY_POLICY.md"
    return policy_path.read_text(encoding="utf-8")

# Чтение README репозитория для показа по кнопке nastavnik
def read_readme_text() -> str:
    readme_path = Path(__file__).resolve().parents[1] / "README.md"
    return readme_path.read_text(encoding="utf-8")

# Фрагменты **заголовок** в файле политики преобразуются в Telegram HTML (<b>)
def privacy_policy_source_to_telegram_html(text: str) -> str:
    parts = re.split(r"\*\*(.+?)\*\*", text)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            out.append(escape(part))
        else:
            out.append(f"<b>{escape(part)}</b>")
    return "".join(out)

# Разбиение длинного текста на части по лимиту Telegram (без обрезки посередине абзаца, где возможно)
def split_text_for_telegram(text: str, max_len: int = TELEGRAM_MESSAGE_MAX_CHARS) -> list[str]:
    text = text.strip()
    if not text:
        return [""]
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= max_len:
            chunks.append(rest)
            break
        cut = rest.rfind("\n\n", 0, max_len)
        if cut == -1:
            cut = rest.rfind("\n", 0, max_len)
        if cut == -1 or cut < max_len // 2:
            cut = max_len
        chunk = rest[:cut].strip()
        if not chunk:
            chunk = rest[:max_len].rstrip()
            cut = max_len
        chunks.append(chunk)
        rest = rest[cut:].lstrip()
    return chunks

# Проверка, что Telegram-username совпадает с nastavnik (без @, без учёта регистра)
def is_nastavnik_username(username: str | None) -> bool:
    if not username:
        return False
    return username.casefold() == NASTAVNIK_USERNAME.casefold()

# Кнопка README (nastavnik) и команда /readme доступны наставнику и архитектору
def can_use_nastavnik_readme(user: User | None) -> bool:
    if not user:
        return False
    if user.id == ARCHITECT_USER_ID:
        return True
    if NASTAVNIK_USER_ID is not None and user.id == NASTAVNIK_USER_ID:
        return True
    return is_nastavnik_username(user.username)

# Возврат клавиатуры главного меню
def main_menu_keyboard(user_id: int | None = None, telegram_username: str | None = None) -> ReplyKeyboardMarkup:
    buttons = [
        ["Написать новое сообщение"],
        ["Прочитать свои сообщения"],
        ["Политика конфиденциальности"],
    ]
    if (
        is_nastavnik_username(telegram_username)
        or user_id == ARCHITECT_USER_ID
        or (NASTAVNIK_USER_ID is not None and user_id == NASTAVNIK_USER_ID)
    ):
        buttons.append([NASTAVNIK_BUTTON_LABEL])
    buttons.append(["Обратная связь"])
    if user_id == ARCHITECT_USER_ID:
        buttons.append(["Архитектор"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# Клавиатура главного меню по объекту пользователя Telegram
def main_menu_keyboard_for_user(user: User | None) -> ReplyKeyboardMarkup:
    return main_menu_keyboard(
        user.id if user else None,
        user.username if user else None,
    )

# Возврат клавиатуры для шага ввода
def flow_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["Назад в главное меню"]], resize_keyboard=True)

# Возврат клавиатуры выбора первого периода
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

# Преобразование выбранного периода в задержки проверок
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

# Возврат inline клавиатуры удаления сообщения
def message_delete_keyboard(message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Удалить", callback_data=f"msg_delete:{message_id}")]])

# Возврат inline клавиатуры подтверждения удаления
def confirm_delete_keyboard(message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Подтвердить", callback_data=f"msg_delete_confirm:{message_id}"),
            InlineKeyboardButton("Отмена", callback_data=f"msg_delete_cancel:{message_id}"),
        ]]
    )

# Инициализация состояния диалога пользователя
def ensure_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    if STATE_KEY not in context.user_data:
        context.user_data[STATE_KEY] = STATE_IDLE

# Определение статуса слежения для сообщения
def message_tracking_status(item: dict) -> str:
    is_finished = item.get("check3_res") == "ESCALATED" or any(
        item.get(field) == "Я в порядке" for field in ("check1_res", "check2_res", "check3_res")
    )
    return "Завершено" if is_finished else "Выполняется"

# Определение итогового результата обработки сообщения
def message_result_status(item: dict) -> str:
    if any(item.get(field) == "Я в порядке" for field in ("check1_res", "check2_res", "check3_res")):
        return "Порядок"
    if item.get("check3_res") == "ESCALATED":
        return "Тревога"
    return "-"

# Форматирование даты из API в локальный вид
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
    return dt.astimezone(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M:%S")

# Нормализация текста ответа пользователя
def normalize_ok_input(value: str) -> str:
    normalized = value.strip().lower().replace("ё", "е")
    normalized = normalized.translate(LATIN_TO_CYRILLIC_SIMILAR)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.strip(" .,!?:;\"'`~+-=_()[]{}<>")
    normalized = re.sub(r"[^a-zа-я0-9\s]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized

# Проверка эквивалентности ответа фразе Я в порядке
def is_ok_text(value: str) -> bool:
    normalized = normalize_ok_input(value)
    if normalized in OK_NORMALIZED_VARIANTS:
        return True
    if normalized.startswith("я в порядке"):
        return True
    return normalized.replace(" ", "") in OK_NORMALIZED_VARIANTS

# Определение создания сообщения в тестовом режиме
def is_test_period_message(recorded: dict) -> bool:
    if recorded.get("message_mode") == "Тестовый":
        return True
    return (
        int(recorded.get("check1_delay_seconds") or 0) == 60
        and int(recorded.get("check2_delay_seconds") or 0) == 60
        and int(recorded.get("check3_delay_seconds") or 0) == 60
    )

# Отправка немедленного аварийного сообщения
async def send_emergency_now(
    context: ContextTypes.DEFAULT_TYPE,
    user,
    recorded: dict,
    response_text: str,
) -> None:
    if not ALERT_CHAT_ID:
        raise RuntimeError("ALERT_CHAT_ID is not set")
    created_text = format_api_datetime(recorded.get("timecreated"))
    mode_text = "РЕЖИМ: ТЕСТОВЫЙ (все периоды по 1 минуте)\n\n" if is_test_period_message(recorded) else ""
    un = (user.username if user else None) or None
    fn = (user.first_name if user else None) or "-"
    ln = (user.last_name if user else None) or "-"
    username_line = f"Username: @{un}\n" if un else "Username: -\n"
    alert_text = (
        "АВАРИЙНОЕ СООБЩЕНИЕ\n\n"
        f"{mode_text}"
        f"ID сообщения: {recorded.get('id')}\n"
        f"User id: {user.id if user else '-'}\n"
        f"{username_line}"
        f"Имя: {fn}\n"
        f"Фамилия: {ln}\n"
        "\n"
        f"Время создания сообщения: {created_text}\n\n"
        f"Текст сообщения:\n{recorded.get('message', '')}\n\n"
        f"Ответ пользователя:\n{response_text}"
    )
    await context.bot.send_message(chat_id=ALERT_CHAT_ID, text=alert_text)

# Попытка сохранения ответа на активную проверку
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
                reply_markup=main_menu_keyboard_for_user(user),
            )
        except Exception:
            logger.exception("Failed to send immediate emergency alert")
            await update.message.reply_text(
                "Ответ на проверку сохранен, но аварийное сообщение пока не отправилось.",
                reply_markup=main_menu_keyboard_for_user(user),
            )
        return True
    await update.message.reply_text(
        "Принято. Вы в порядке.\n"
        "Бот прекращает следить за этим сообщением.\n\n"
        f"Время создания: {created_text}\n"
        f"Исходное сообщение: {recorded.get('message', '')}\n",
        reply_markup=main_menu_keyboard_for_user(user),
    )
    return True

# Обработка команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_state(context)
    context.user_data[STATE_KEY] = STATE_IDLE
    user = update.effective_user
    first_name = (user.first_name if user else None) or "<Ваше имя не распознано>"
    await update.message.reply_text(
        start_text(first_name),
        reply_markup=main_menu_keyboard_for_user(user),
    )

# Отправка текста политики конфиденциальности
async def privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    kb = main_menu_keyboard_for_user(user)
    message = update.message
    if not message:
        return
    try:
        body = read_privacy_policy_text()
    except FileNotFoundError:
        logger.exception("Privacy policy file not found")
        await message.reply_text(
            "Не удалось загрузить текст политики (файл на сервере не найден). Обратитесь к администратору.",
            reply_markup=kb,
        )
        return
    except OSError as exc:
        logger.exception("Privacy policy read failed: %s", exc)
        await message.reply_text(
            "Не удалось прочитать политику конфиденциальности. Попробуйте позже.",
            reply_markup=kb,
        )
        return
    html_body = privacy_policy_source_to_telegram_html(body)
    parts = split_text_for_telegram(html_body)
    parse_kw = {"parse_mode": "HTML"}
    await message.reply_text(parts[0], reply_markup=kb, **parse_kw)
    chat = update.effective_chat
    if chat and len(parts) > 1:
        for part in parts[1:]:
            await context.bot.send_message(chat_id=chat.id, text=part, **parse_kw)

# Отправка содержимого README (nastavnik)
async def show_readme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.message
    if not message:
        return
    kb = main_menu_keyboard_for_user(user)
    if not can_use_nastavnik_readme(user):
        await message.reply_text("Команда недоступна.", reply_markup=kb)
        return
    try:
        body = read_readme_text()
    except FileNotFoundError:
        logger.exception("README.md not found")
        await message.reply_text(
            "Файл README не найден на сервере. Обратитесь к администратору.",
            reply_markup=kb,
        )
        return
    except OSError as exc:
        logger.exception("README read failed: %s", exc)
        await message.reply_text(
            "Не удалось прочитать README. Попробуйте позже.",
            reply_markup=kb,
        )
        return
    parts = split_text_for_telegram(body)
    await message.reply_text(parts[0], reply_markup=kb)
    chat = update.effective_chat
    if chat and len(parts) > 1:
        for part in parts[1:]:
            await context.bot.send_message(chat_id=chat.id, text=part)

# Показ пользователю списка его сообщений
async def show_user_messages(update: Update) -> None:
    user = update.effective_user
    if not user:
        await update.message.reply_text("Не удалось определить пользователя.", reply_markup=main_menu_keyboard_for_user(user))
        return
    try:
        response = api_get("/api/messages", params={"user_id": user.id})
        if not response.ok:
            raise RuntimeError(f"api status {response.status_code}")
        items = response.json()
        if not items:
            await update.message.reply_text(
                "У вас пока нет сохраненных сообщений.",
                reply_markup=main_menu_keyboard_for_user(user),
            )
            return
        await update.message.reply_text(
            f"Ваши сообщения ({len(items)}):",
            reply_markup=main_menu_keyboard_for_user(user),
        )
        for idx, item in enumerate(items, start=1):
            tracking = message_tracking_status(item)
            result = message_result_status(item)
            un_item = item.get("username")
            un_item_disp = f"@{un_item}" if un_item else "-"
            fn_item = item.get("first_name") or "-"
            ln_item = item.get("last_name") or "-"
            text = (
                f"{idx}. Текст: {item.get('message', '')}\n"
                f"Username: {un_item_disp}\n"
                f"Имя: {fn_item}\n"
                f"Фамилия: {ln_item}\n"
                f"Время отправки: {format_api_datetime(item.get('timecreated'))}\n"
                f"Слежение: {tracking}\n"
                f"Результат: {result}"
            )
            await update.message.reply_text(text, reply_markup=message_delete_keyboard(item["id"]))
    except Exception:
        logger.exception("Failed to load messages")
        await update.message.reply_text(
            "Не удалось прочитать сообщения из базы.",
            reply_markup=main_menu_keyboard_for_user(user),
        )

def build_architect_summary(overview: dict) -> str:
    total = int(overview.get("total_messages") or 0)
    active = int(overview.get("active_checks") or 0)
    alerts = int(overview.get("total_alerts") or 0)
    completed = max(total - active, 0)
    return (
        "Отчет архитектора\n\n"
        f"Всего заявок в базе: {total}\n"
        f"В процессе: {active}\n"
        f"Завершено: {completed}\n"
        f"Тревоги: {alerts}\n"
        f"Пользователи: {int(overview.get('total_users') or 0)}\n"
        f"Check1 SENT: {int(overview.get('check1_sent') or 0)}\n"
        f"Check2 SENT: {int(overview.get('check2_sent') or 0)}\n"
        f"Check3 SENT: {int(overview.get('check3_sent') or 0)}"
    )

# Разделитель между блоком KPI отчёта архитектора и текстом README
ARCHITECT_REPORT_README_SEPARATOR = "\n\n──────────\nREADME\n──────────\n\n"

async def show_architect_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or user.id != ARCHITECT_USER_ID:
        await update.message.reply_text(
            "Команда недоступна",
            reply_markup=main_menu_keyboard_for_user(user),
        )
        return
    try:
        response = api_get("/api/admin/overview")
        if not response.ok:
            raise RuntimeError(f"api status {response.status_code}")
        stats = build_architect_summary(response.json())
        try:
            full_text = stats + ARCHITECT_REPORT_README_SEPARATOR + read_readme_text().strip()
        except (FileNotFoundError, OSError) as exc:
            logger.warning("Architect report: README unavailable: %s", exc)
            full_text = stats + "\n\nREADME: файл недоступен на сервере."
        parts = split_text_for_telegram(full_text)
        kb = main_menu_keyboard_for_user(user)
        await update.message.reply_text(parts[0], reply_markup=kb)
        chat = update.effective_chat
        if chat and len(parts) > 1:
            for part in parts[1:]:
                await context.bot.send_message(chat_id=chat.id, text=part)
    except Exception:
        logger.exception("Failed to load architect summary")
        await update.message.reply_text(
            "Не удалось получить отчет архитектора",
            reply_markup=main_menu_keyboard_for_user(user),
        )

# Обработка текстовых сообщений пользователя
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_state(context)
    user = update.effective_user
    text = (update.message.text or "").strip()
    state = context.user_data.get(STATE_KEY, STATE_IDLE)
    is_ok_phrase = is_ok_text(text)
    if text == "Назад в главное меню":
        context.user_data[STATE_KEY] = STATE_IDLE
        context.user_data.pop(DRAFT_MESSAGE_KEY, None)
        await update.message.reply_text("Главное меню:", reply_markup=main_menu_keyboard_for_user(user))
        return
    if text == "Написать новое сообщение":
        context.user_data[STATE_KEY] = STATE_WAIT_MESSAGE
        context.user_data.pop(DRAFT_MESSAGE_KEY, None)
        await update.message.reply_text("Введите текст одним сообщением максимально подробно, чтобы Вас могли найти.", reply_markup=flow_keyboard())
        return
    if text == "Прочитать свои сообщения":
        context.user_data[STATE_KEY] = STATE_IDLE
        await show_user_messages(update)
        return
    if text == "Политика конфиденциальности":
        context.user_data[STATE_KEY] = STATE_IDLE
        await privacy(update, context)
        return
    if text == NASTAVNIK_BUTTON_LABEL:
        context.user_data[STATE_KEY] = STATE_IDLE
        await show_readme(update, context)
        return
    if text == "Архитектор":
        context.user_data[STATE_KEY] = STATE_IDLE
        await show_architect_summary(update, context)
        return
    if text == "Обратная связь":
        context.user_data[STATE_KEY] = STATE_WAIT_FEEDBACK
        await update.message.reply_text(
            "Напишите ваше сообщение. Оно будет передано администрации.",
            reply_markup=flow_keyboard(),
        )
        return
    if state == STATE_IDLE:
        if is_ok_phrase:
            try:
                accepted = await try_submit_check_response(update, context, OK_CANONICAL_TEXT)
                if accepted:
                    return
                await update.message.reply_text(
                    "Нет активной проверки для подтверждения.",
                    reply_markup=main_menu_keyboard_for_user(user),
                )
                return
            except Exception:
                logger.exception("Failed to submit check response")
                await update.message.reply_text(
                    "Не удалось обработать ответ.",
                    reply_markup=main_menu_keyboard_for_user(user),
                )
                return
        try:
            accepted = await try_submit_check_response(update, context, text)
            if accepted:
                return
        except Exception:
            logger.exception("Failed to submit check response")
            await update.message.reply_text(
                "Не удалось отправить ответ на проверку.",
                reply_markup=main_menu_keyboard_for_user(user),
            )
            return
    if state == STATE_WAIT_MESSAGE:
        if not user:
            await update.message.reply_text("Не удалось определить пользователя.", reply_markup=main_menu_keyboard_for_user(user))
            context.user_data[STATE_KEY] = STATE_IDLE
            return
        if not text:
            await update.message.reply_text("Пустой текст. Введите сообщение еще раз.")
            return
        context.user_data[DRAFT_MESSAGE_KEY] = text
        context.user_data[STATE_KEY] = STATE_WAIT_FIRST_PERIOD
        await update.message.reply_text(
            "Выберите период до первого опроса.\n"
            "Второй опрос будет через 1 час после первого, третий - еще через 1 час."
            "\n(в тестовом режиме — все опросы через 1 минуту).",
            reply_markup=first_period_keyboard(),
        )
        return
    if state == STATE_WAIT_FIRST_PERIOD:
        if not user:
            await update.message.reply_text("Не удалось определить пользователя.", reply_markup=main_menu_keyboard_for_user(user))
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
            await update.message.reply_text(
                "Текст сообщения не найден. Введите сообщение заново.",
                reply_markup=main_menu_keyboard_for_user(user),
            )
            return
        try:
            sent_at = (update.message.date if update.message else None) or datetime.now(timezone.utc)
            check1_delay, check2_delay, check3_delay, message_mode = period
            response = api_post(
                "/api/messages",
                {
                    "user_id": user.id,
                    "message": draft_message,
                    "message_mode": message_mode,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "check1_delay_seconds": check1_delay,
                    "check2_delay_seconds": check2_delay,
                    "check3_delay_seconds": check3_delay,
                },
            )
            if not response.ok:
                raise RuntimeError(f"api status {response.status_code}")
            context.user_data[STATE_KEY] = STATE_IDLE
            context.user_data.pop(DRAFT_MESSAGE_KEY, None)
            un_disp = f"@{user.username}" if user.username else "-"
            fn_disp = user.first_name or "-"
            ln_disp = user.last_name or "-"
            await update.message.reply_text(
                "Сообщение сохранено.\n\n"
                f"Текст: {draft_message}\n"
                f"Отправитель: id {user.id}\n"
                f"Username: {un_disp}\n"
                f"Имя: {fn_disp}\n"
                f"Фамилия: {ln_disp}\n"
                f"Время отправки: {sent_at.astimezone(MOSCOW_TZ).strftime('%d.%m.%Y %H:%M:%S')}",
                reply_markup=main_menu_keyboard_for_user(user),
            )
            return
        except Exception:
            logger.exception("Failed to create message")
            await update.message.reply_text(
                "Не удалось сохранить сообщение в базу.",
                reply_markup=main_menu_keyboard_for_user(user),
            )
            context.user_data[STATE_KEY] = STATE_IDLE
            context.user_data.pop(DRAFT_MESSAGE_KEY, None)
            return
    if state == STATE_WAIT_FEEDBACK:
        if not user:
            context.user_data[STATE_KEY] = STATE_IDLE
            await update.message.reply_text("Не удалось определить пользователя.", reply_markup=main_menu_keyboard_for_user(user))
            return
        if not text:
            await update.message.reply_text("Пустой текст. Напишите ваше сообщение.")
            return
        try:
            response = api_post(
                "/api/feedback",
                {"user_id": user.id, "message": text},
            )
            if not response.ok:
                raise RuntimeError(f"api status {response.status_code}")
            context.user_data[STATE_KEY] = STATE_IDLE
            await update.message.reply_text(
                "Спасибо за обратную связь! Ваше сообщение будет рассмотрено.",
                reply_markup=main_menu_keyboard_for_user(user),
            )
        except Exception:
            logger.exception("Failed to submit feedback")
            await update.message.reply_text(
                "Не удалось отправить сообщение. Попробуйте позже.",
                reply_markup=main_menu_keyboard_for_user(user),
            )
        return
    await update.message.reply_text("Используйте кнопки меню.", reply_markup=main_menu_keyboard_for_user(user))

# Обработка нажатий inline кнопок
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

# Регистрация команд бота в меню Telegram
async def setup_bot_commands(application: Application) -> None:
    base_commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("privacy", "Политика конфиденциальности"),
    ]
    commands_with_readme = base_commands + [
        BotCommand("readme", "README / описание бота"),
    ]
    try:
        await application.bot.delete_webhook(drop_pending_updates=False)
        await application.bot.set_my_commands(base_commands)
        readme_chats: set[int] = {ARCHITECT_USER_ID}
        if NASTAVNIK_USER_ID is not None:
            readme_chats.add(NASTAVNIK_USER_ID)
        for chat_id in readme_chats:
            await application.bot.set_my_commands(
                commands_with_readme,
                scope=BotCommandScopeChat(chat_id=chat_id),
            )
    except Exception:
        logger.exception("Failed to initialize bot commands")

# Точка входа для запуска Telegram бота
def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")
    app = Application.builder().token(token).post_init(setup_bot_commands).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("privacy", privacy))
    app.add_handler(CommandHandler("readme", show_readme))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Bot is starting long polling...")
    polling_kwargs = {
        "drop_pending_updates": True,
        "allowed_updates": Update.ALL_TYPES,
        "poll_interval": POLLING_INTERVAL_SECONDS,
        "timeout": POLLING_TIMEOUT_SECONDS,
    }
    # Совместимость с разными версиями python-telegram-bot:
    # передаем дополнительные timeout-параметры только если они поддерживаются.
    optional_polling_kwargs = {
        "read_timeout": POLLING_READ_TIMEOUT_SECONDS,
        "connect_timeout": POLLING_CONNECT_TIMEOUT_SECONDS,
        "pool_timeout": POLLING_POOL_TIMEOUT_SECONDS,
    }
    supported_polling_params = set(inspect.signature(app.run_polling).parameters)
    for key, value in optional_polling_kwargs.items():
        if key in supported_polling_params:
            polling_kwargs[key] = value

    app.run_polling(
        **polling_kwargs,
    )

if __name__ == "__main__":
    main()
