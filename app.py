import streamlit as st

from repositories.holding_repo import (
    authenticate_user,
    get_daily_history_df,
    get_holdings_df,
    init_db,
    replace_holdings,
    save_daily_history,
)
from services.fund_service import build_dashboard_data, parse_holdings
from ui.dashboard import (
    render_hero,
    render_history,
    render_holdings_editor,
    render_metrics,
    render_positions_table,
    render_sidebar_login,
    render_sync_messages,
)
from ui.theme import apply_theme


def ensure_streamlit_context():
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except ImportError:
        try:
            from streamlit.scriptrunner.script_run_context import get_script_run_ctx
        except ImportError:
            get_script_run_ctx = None

    if get_script_run_ctx is not None and get_script_run_ctx() is None:
        raise SystemExit(
            "请使用 Streamlit 启动此应用：\n"
            "streamlit run /Users/zhangyong/Desktop/fund/app.py"
        )


def main():
    ensure_streamlit_context()
    conn = init_db()

    st.set_page_config(page_title="资产管家", layout="wide")
    apply_theme()

    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    render_sidebar_login(authenticate_user, conn)

    if not st.session_state.logged_in:
        st.info("👋 请在左侧登录")
        st.stop()

    holdings_df = get_holdings_df(conn, st.session_state.user)
    if not holdings_df.empty:
        with st.spinner('正在同步行情与市值...'):
            summary = build_dashboard_data(holdings_df)
    else:
        summary = None

    render_hero(summary["now"] if summary else None)
    render_holdings_editor(parse_holdings, replace_holdings, conn, st.session_state.user)

    if holdings_df.empty:
        st.info("💡 请先录入持仓数据")
        return

    render_sync_messages(summary["failed_funds"], summary["missing_cost_funds"])
    render_metrics(summary)
    render_positions_table(summary["positions"])

    save_daily_history(
        conn,
        st.session_state.user,
        summary["today_s"],
        summary["total_cur"],
        summary["total_yest"],
    )
    history_df = get_daily_history_df(conn, st.session_state.user)
    render_history(history_df)


if __name__ == "__main__":
    main()
