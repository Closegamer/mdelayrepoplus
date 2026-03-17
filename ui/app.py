import os
import hashlib
import hmac
import time
from pathlib import Path
from datetime import datetime, timedelta
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
TIMEOUT_SECONDS = 15
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
LOGIN_TOKEN_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

# Создание токена авторизации для сохранения входа
def make_login_token(password: str, timestamp: int | None = None) -> str:
    ts = int(timestamp or time.time())
    payload = str(ts).encode("utf-8")
    digest = hmac.new(password.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"{ts}.{digest}"

# Проверка валидности токена авторизации
def is_login_token_valid(password: str, token: str) -> bool:
    if not password or not token or "." not in token:
        return False
    ts_text, signature = token.split(".", 1)
    if not ts_text.isdigit():
        return False
    ts = int(ts_text)
    now = int(time.time())
    if ts > now or (now - ts) > LOGIN_TOKEN_MAX_AGE_SECONDS:
        return False
    expected = make_login_token(password, ts).split(".", 1)[1]
    return hmac.compare_digest(signature, expected)

# Подключение глобальных стилей страницы
def inject_global_styles() -> None:
    css = Path(__file__).with_name("styles.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

# Выполнение GET запроса к API и возврат JSON
def api_get(path: str, params: dict | None = None):
    response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()

# Выполнение DELETE запроса к API
def api_delete(path: str):
    response = requests.delete(f"{API_BASE_URL}{path}", timeout=TIMEOUT_SECONDS)
    return response

# Инициализация состояния авторизации в сессии
def ensure_auth_state() -> None:
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "admin_password" not in st.session_state:
        st.session_state.admin_password = ADMIN_PASSWORD
    configured_password = st.session_state.get("admin_password", "")
    auth_token = st.query_params.get("auth", "")
    if is_login_token_valid(configured_password, auth_token):
        st.session_state.logged_in = True

# Рендер формы входа в админку
def render_login() -> bool:
    top_spacer, _, _ = st.columns([1, 1, 1])
    with top_spacer:
        st.write("")
        st.write("")
    left, center, right = st.columns([2, 3, 2])
    with center:
        with st.form("admin_login_form", clear_on_submit=False):
            st.text_input(
                "Пароль администратора",
                type="password",
                placeholder="Стой, кто идет? Нужен пароль!",
                label_visibility="collapsed",
                key="admin_password_input",
            )
            submitted = st.form_submit_button("Войти", use_container_width=True)
        if submitted:
            entered_password = st.session_state.get("admin_password_input", "")
            configured_password = st.session_state.get("admin_password", "")
            if entered_password == configured_password and configured_password:
                st.session_state.logged_in = True
                st.query_params["auth"] = make_login_token(configured_password)
                st.rerun()
            st.error("Неверный пароль.")
    return st.session_state.logged_in

# Рендер блока основных метрик
def render_overview() -> None:
    overview = api_get("/api/admin/overview")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi_card("Всего сообщений", overview["total_messages"], "default")
    with c2:
        render_kpi_card("Пользователей", overview["total_users"], "success")
    with c3:
        render_kpi_card("Тревог", overview["total_alerts"], "danger")
    with c4:
        render_kpi_card("Активные проверки", overview["active_checks"], "warn")
    c5, c6, c7 = st.columns(3)
    with c5:
        render_kpi_card("Check1 SENT", overview["check1_sent"], "default")
    with c6:
        render_kpi_card("Check2 SENT", overview["check2_sent"], "default")
    with c7:
        render_kpi_card("Check3 SENT", overview["check3_sent"], "default")

# Рендер карточки одной метрики
def render_kpi_card(label: str, value: int, tone: str) -> None:
    st.markdown(
        (
            f"<div class='kpi-card {tone}'>"
            f"<div class='kpi-label'>{label}</div>"
            f"<div class='kpi-value'>{value}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

# Вычисление статуса слежения для строки таблицы
def row_tracking_status(item: dict) -> str:
    is_finished = item.get("check3_res") == "ESCALATED" or any(
        item.get(field) == "Я в порядке" for field in ("check1_res", "check2_res", "check3_res")
    )
    return "Завершено" if is_finished else "Выполняется"

# Вычисление итогового результата для строки таблицы
def row_result_status(item: dict) -> str:
    if any(item.get(field) == "Я в порядке" for field in ("check1_res", "check2_res", "check3_res")):
        return "Порядок"
    if item.get("check3_res") == "ESCALATED":
        return "Тревога"
    return "-"

# Форматирование ответа конкретной проверки
def format_check_response(item: dict, check_no: int) -> str:
    value = item.get(f"check{check_no}_res")
    if not value or value == "SENT":
        return "-"
    if value == "ESCALATED":
        if check_no == 3 and item.get("check3_time"):
            response_text = (item.get("user_response_text") or "").strip()
            if response_text:
                return response_text
        return "-"
    return value

# Вычисление времени первого запроса
def format_first_request_time(item: dict) -> str:
    check1_time = item.get("check1_time")
    if check1_time:
        return format_created_at(check1_time)
    time_created = item.get("timecreated")
    delay_seconds = int(item.get("check1_delay_seconds") or 0)
    if not time_created or delay_seconds <= 0:
        return "-"
    raw = str(time_created).replace("Z", "+00:00")
    try:
        created_dt = datetime.fromisoformat(raw)
    except ValueError:
        return "-"
    return (created_dt + timedelta(seconds=delay_seconds)).strftime("%d.%m.%Y %H:%M")

# Преобразование API записей в формат таблицы UI
def map_table_rows(rows: list[dict]) -> list[dict]:
    mapped = []
    for item in rows:
        tracking = row_tracking_status(item)
        result = row_result_status(item)
        mapped.append(
            {
                "ID": item.get("id"),
                "UserID": item.get("user_id"),
                "Username": item.get("username") or "-",
                "Режим": item.get("message_mode") or "Реальный",
                "Сообщение": shorten_message(item.get("message") or ""),
                "Создано": format_created_at(item.get("timecreated")),
                "Первый запрос": format_first_request_time(item),
                "Ответ Check1": format_check_response(item, 1),
                "Ответ Check2": format_check_response(item, 2),
                "Ответ Check3": format_check_response(item, 3),
                "Слежение": tracking,
                "Результат": result,
            }
        )
    return mapped

# Сокращение длинного текста сообщения
def shorten_message(value: str, limit: int = 90) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."

# Форматирование даты в человекочитаемый вид
def format_created_at(value: str | None) -> str:
    if not value:
        return "-"
    raw = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
        return dt.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value

# Инициализация смещения пагинации для вкладки
def ensure_page_offset_state(key: str) -> None:
    if key not in st.session_state:
        st.session_state[key] = 0

# Рендер таблицы с пагинацией и удалением
def render_table(title: str, endpoint: str, page_size: int, page_key: str) -> None:
    ensure_page_offset_state(page_key)
    offset = int(st.session_state[page_key])
    st.subheader(title)
    rows = api_get(endpoint, params={"limit": page_size, "offset": offset})
    if not rows:
        st.info("Нет данных.")
        if offset > 0:
            st.session_state[page_key] = max(0, offset - page_size)
            st.rerun()
        return
    mapped_rows = map_table_rows(rows)
    st.table(mapped_rows)
    ids = [row.get("ID") for row in mapped_rows if row.get("ID") is not None]
    if ids:
        delete_select_col, delete_btn_col, _ = st.columns([3, 2, 5], vertical_alignment="bottom")
        with delete_select_col:
            selected_id = st.selectbox("ID для удаления", ids, key=f"{page_key}_delete_id")
        with delete_btn_col:
            if st.button("Удалить запись", key=f"{page_key}_delete_button", use_container_width=True):
                try:
                    response = api_delete(f"/api/admin/messages/{selected_id}")
                    if response.status_code == 204:
                        st.success(f"Запись {selected_id} удалена.")
                        st.rerun()
                    elif response.status_code == 404:
                        st.warning("Запись не найдена или уже удалена.")
                    else:
                        st.error("Не удалось удалить запись.")
                except Exception as exc:
                    st.error(f"Ошибка удаления: {exc}")
    page_number = (offset // page_size) + 1
    _, nav_left, nav_center, nav_right, _ = st.columns([2, 2, 2, 2, 2], vertical_alignment="center")
    with nav_left:
        back_clicked = st.button("Назад", key=f"{page_key}_back", use_container_width=True, disabled=offset == 0)
    with nav_center:
        st.markdown(f"<div style='text-align:center;'>Страница {page_number}</div>", unsafe_allow_html=True)
    with nav_right:
        forward_disabled = len(rows) < page_size
        next_clicked = st.button("Вперед", key=f"{page_key}_next", use_container_width=True, disabled=forward_disabled)
    if back_clicked:
        st.session_state[page_key] = max(0, offset - page_size)
        st.rerun()
    if next_clicked:
        st.session_state[page_key] = offset + page_size
        st.rerun()

# Рендер верхней части страницы и кнопки выхода
def render_header() -> None:
    left, right = st.columns([9, 1], vertical_alignment="top")
    with left:
        st.title("KakDelaTorBot - Центр мониторинга и управления")
    with right:
        if st.button("Выйти", use_container_width=True):
            st.session_state.logged_in = False
            if "auth" in st.query_params:
                del st.query_params["auth"]
            st.rerun()

# Рендер панели фильтров и управления страницей
def render_filters() -> int:
    f1, f2, f3, _ = st.columns([2, 1, 1, 6], vertical_alignment="bottom")
    with f1:
        page_size = st.selectbox("Количество записей", [12, 24, 48, 96], index=1)
    with f2:
        apply_clicked = st.button("Применить", use_container_width=True)
    with f3:
        refresh_clicked = st.button("Обновить", use_container_width=True)
    if apply_clicked:
        st.session_state["messages_offset"] = 0
        st.session_state["alerts_offset"] = 0
        st.session_state["active_offset"] = 0
        st.rerun()
    if refresh_clicked:
        st.rerun()
    return page_size

# Рендер нижнего футера страницы
def render_footer() -> None:
    st.markdown("---")
    st.markdown(
        "<div style='text-align:center;'>writtenBy(Closegamer, 2026, All rights reserved)</div>",
        unsafe_allow_html=True,
    )

# Точка входа Streamlit приложения
def main() -> None:
    st.set_page_config(page_title="KakDelaTorBot Adminka", layout="wide")
    inject_global_styles()
    ensure_auth_state()
    if not st.session_state.logged_in:
        render_login()
        return
    render_header()
    page_size = render_filters()
    try:
        render_overview()
        tab_messages, tab_alerts, tab_active = st.tabs(["Сообщения", "Тревоги", "Активные проверки"])
        with tab_messages:
            render_table("Последние сообщения", "/api/admin/messages", page_size, "messages_offset")
        with tab_alerts:
            render_table("Последние тревоги", "/api/admin/alerts", page_size, "alerts_offset")
        with tab_active:
            render_table("Активные проверки", "/api/admin/active-checks", page_size, "active_offset")
    except Exception as exc:
        st.error(f"Ошибка загрузки данных: {exc}")
    render_footer()

if __name__ == "__main__":
    main()
