import os
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
TIMEOUT_SECONDS = 15
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

def inject_global_styles() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {display: none;}
        [data-testid="collapsedControl"] {display: none;}
        </style>
        """,
        unsafe_allow_html=True,
    )

def api_get(path: str, params: dict | None = None):
    response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()

def ensure_auth_state() -> None:
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

def render_login() -> bool:
    st.markdown(
        """
        <style>
        div[data-testid="stForm"] {
            text-align: center;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    top_spacer, _, _ = st.columns([1, 1, 1])
    with top_spacer:
        st.write("")
        st.write("")
    left, center, right = st.columns([2, 3, 2])
    with center:
        with st.form("admin_login_form", clear_on_submit=False):
            password = st.text_input(
                "Пароль администратора",
                type="password",
                placeholder="Стой, кто идет?",
                label_visibility="collapsed",
            )
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

def ensure_page_offset_state(key: str) -> None:
    if key not in st.session_state:
        st.session_state[key] = 0

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
    st.table(rows)
    page_number = (offset // page_size) + 1
    nav_left, nav_center, nav_right = st.columns([3, 2, 3], vertical_alignment="center")
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

def render_header() -> None:
    left, right = st.columns([9, 1], vertical_alignment="top")
    with left:
        st.title("mDelayPlusBot - Центр мониторинга и управления")
    with right:
        if st.button("Выйти", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()

def render_filters() -> int:
    f1, f2, _ = st.columns([2, 1, 7], vertical_alignment="bottom")
    with f1:
        page_size = st.selectbox("Количество записей", [12, 24, 48, 96], index=1)
    with f2:
        apply_clicked = st.button("Применить", use_container_width=True)
    if apply_clicked:
        st.session_state["messages_offset"] = 0
        st.session_state["alerts_offset"] = 0
        st.session_state["active_offset"] = 0
        st.rerun()
    return page_size

def render_footer() -> None:
    st.markdown("---")
    st.markdown(
        "<div style='text-align:center;'>writtenBy(Closegamer, 2026, All rights reserved)</div>",
        unsafe_allow_html=True,
    )

def main() -> None:
    st.set_page_config(page_title="mDelayPlusBot Admin", layout="wide")
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
