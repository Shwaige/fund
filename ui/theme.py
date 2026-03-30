import streamlit as st


def apply_theme():
    st.markdown("""
        <style>
        [data-testid="stMetricDelta"] svg { fill: currentColor !important; }
        [data-testid="stMetricDelta"] > div:nth-child(2) { color: #ff4b4b !important; }
        [data-testid="stMetricDelta"] { color: #ff4b4b !important; }
        </style>
    """, unsafe_allow_html=True)
