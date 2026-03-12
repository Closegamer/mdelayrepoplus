import os
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
TIMEOUT_SECONDS = 15
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

def api_get(path: str, params: dict | None = None):
    response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()

def ensure_auth_state() -> None:
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

def render_login() -> bool:
    left, center, right = st.columns([1, 2, 1])
    with center:
        with st.form("admin_login_form", clear_on_submit=False):
            password = st.text_input("Пароль администратора", type="password", placeholder="Введите пароль")
            submitted = st.form_submit_button("Войти", use_container_width=True)
        if submitted:
            if password == ADMIN_PASSWORD and ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            st.error("Неверный пароль.")
    return st.session_state.logged_in

def render_overview() -> None:
    overview = api_get("/api/admin/overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Всего сообщений", overview["total_messages"])
    c2.metric("Пользователей", overview["total_users"])
    c3.metric("Тревог", overview["total_alerts"])
    c4.metric("Активные проверки", overview["active_checks"])
    c5, c6, c7 = st.columns(3)
    c5.metric("Check1 SENT", overview["check1_sent"])
    c6.metric("Check2 SENT", overview["check2_sent"])
    c7.metric("Check3 SENT", overview["check3_sent"])

def render_table(title: str, endpoint: str, page_size: int) -> None:
    st.subheader(title)
    rows = api_get(endpoint, params={"limit": page_size, "offset": 0})
    if not rows:
        st.info("Нет данных.")
        return
    st.table(rows)

def main() -> None:
    st.set_page_config(page_title="mDelayPlusBot Admin", layout="wide")
    ensure_auth_state()
    if not st.session_state.logged_in:
        render_login()
        return
    st.title("mDelayPlusBot - Центр мониторинга и управления")
    if st.button("Выйти"):
        st.session_state.logged_in = False
        st.rerun()
    page_size = st.selectbox("Количество записей", [12, 24, 48, 96], index=1)
    st.button("Применить")
    try:
        render_overview()
        tab_messages, tab_alerts, tab_active = st.tabs(["Сообщения", "Тревоги", "Активные проверки"])
        with tab_messages:
            render_table("Последние сообщения", "/api/admin/messages", page_size)
        with tab_alerts:
            render_table("Последние тревоги", "/api/admin/alerts", page_size)
        with tab_active:
            render_table("Активные проверки", "/api/admin/active-checks", page_size)
    except Exception as exc:
        st.error(f"Ошибка загрузки данных: {exc}")

if __name__ == "__main__":
    main()
