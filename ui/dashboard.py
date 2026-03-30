import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


def universal_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def render_sidebar_login(authenticate_user, conn):
    with st.sidebar:
        st.title("🔐 同步中心")
        username = st.text_input("用户名", value="admin")
        password = st.text_input("密码", type="password", value="123456")
        if st.button("进入系统/更新数据"):
            if authenticate_user(conn, username, password):
                st.session_state.logged_in = True
                st.session_state.user = username
                universal_rerun()
            else:
                st.error("密码错误")


def render_hero(now=None):
    st.title("📊 实盘看板")


def render_holdings_editor(parse_holdings, replace_holdings, conn, username):
    with st.expander("📝 编辑持仓"):
        raw_text = st.text_area(
            "格式：名称,代码,份额,买入总金额",
            height=150,
            placeholder="可以直接粘贴你的持仓列表...\n华夏沪深300ETF联接A,000051,288.15,320.00",
        )
        if st.button("保存更新"):
            valid_data, invalid_lines = parse_holdings(raw_text, username)
            if valid_data:
                replace_holdings(conn, username, valid_data)
                if invalid_lines:
                    st.warning(f"已忽略格式错误的行：{', '.join(map(str, invalid_lines))}")
                universal_rerun()
            else:
                st.warning("没有识别到有效持仓，请检查输入格式。")


def render_sync_messages(failed_funds, missing_cost_funds):
    if failed_funds:
        st.warning(
            "以下基金本次同步失败，已从汇总中排除：\n" + "\n".join(failed_funds[:5])
            + ("\n..." if len(failed_funds) > 5 else "")
        )
    if missing_cost_funds:
        st.info(
            "以下基金未录入买入总金额，累计盈亏未参与汇总：\n" + "\n".join(missing_cost_funds[:5])
            + ("\n..." if len(missing_cost_funds) > 5 else "")
        )


def render_metrics(summary):
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("当前总市值", f"¥{summary['total_cur']:,.2f}")
    c2.metric("昨日持有规模", f"¥{summary['total_yest']:,.2f}")
    c3.metric("今日盈亏", f"¥{summary['profit_sum']:,.2f}", f"{'+' if summary['pct'] > 0 else ''}{summary['pct']}%")
    c4.metric(
        "累计盈亏",
        f"¥{summary['cumulative_profit_sum']:,.2f}" if summary['total_cost'] != 0 else "未录入成本",
        f"{'+' if summary['cumulative_pct_sum'] > 0 else ''}{summary['cumulative_pct_sum']}%"
        if summary['total_cost'] != 0 else None,
    )
    c5.metric("同步时间", summary["now"].strftime("%H:%M:%S"))


def render_positions_table(positions):
    st.markdown("### 📋 资产明细 (已按盈亏排序)")
    display_df = pd.DataFrame(positions)

    if display_df.empty:
        return

    display_df = display_df.sort_values(by="当日盈亏", ascending=False, na_position="last")
    display_df = display_df[
        [
            "基金名称",
            "代码",
            "持有份额",
            "今日涨幅(%)",
            "当日盈亏",
            "买入总金额",
            "今日市值",
            "累计盈亏",
            "累计收益率(%)",
            "状态",
        ]
    ]

    def style_profit(val):
        color = '#ff4b4b' if val > 0 else '#00873c' if val < 0 else '#666'
        return f'color: {color}; font-weight: bold'

    styled_df = display_df.style.map(
        style_profit,
        subset=['今日涨幅(%)', '当日盈亏', '累计盈亏', '累计收益率(%)'],
    ).format({
        '持有份额': '{:,.2f}',
        '买入总金额': lambda x: f"¥{x:,.2f}" if pd.notna(x) else "未录入",
        '今日市值': '¥{:,.2f}',
        '今日涨幅(%)': '{:+.2f}%',
        '当日盈亏': '¥{:,.2f}',
        '累计盈亏': lambda x: f"¥{x:,.2f}" if pd.notna(x) else "未录入",
        '累计收益率(%)': lambda x: f"{x:+.2f}%" if pd.notna(x) else "未录入",
    })

    st.dataframe(styled_df)


def render_history(history_df):
    st.markdown("---")
    st.markdown("### 📅 历史收益明细")

    if history_df.empty:
        return

    h_rows = ""
    for _, row in history_df.iterrows():
        amount = row['total_value'] - row['base_value']
        ratio = round(((row['total_value'] / row['base_value'] - 1) * 100), 2) if row['base_value'] != 0 else 0
        color = "#ff4b4b" if ratio > 0 else "#00873c" if ratio < 0 else "#666"
        h_rows += (
            f"<tr><td>{row['record_date']}</td>"
            f"<td style='color:{color}; font-weight:bold;'>¥{amount:,.2f}</td>"
            f"<td style='color:{color}; font-weight:600;'>{ratio:+.2f}%</td></tr>"
        )

    history_html = f"""
    <style>
    .h-wrap {{
        border: 1px solid #eee;
        border-radius: 0;
        overflow: hidden;
        background: white;
        font-family: sans-serif;
    }}
    .h-table {{
        width: 100%;
        border-collapse: collapse;
        text-align: center;
        color: #222;
    }}
    .h-table th {{
        padding: 12px;
        background: #f8f9fa;
        color: #666;
        font-size: 13px;
        border-bottom: 2px solid #eee;
    }}
    .h-table td {{
        padding: 12px;
        border-bottom: 1px solid #eee;
        font-size: 14px;
    }}
    .h-table tr:last-child td {{
        border-bottom: none;
    }}
    </style>
    <div class='h-wrap'>
        <table class='h-table'>
            <tr><th>日期</th><th>盈亏金额</th><th>收益率</th></tr>
            {h_rows}
        </table>
    </div>
    """
    components.html(history_html, height=(len(history_df) * 50) + 60)
