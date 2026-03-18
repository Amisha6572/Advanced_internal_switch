import sys
import os
# Ensure the app's own directory is on the path (needed when Streamlit Cloud
# runs from a parent directory, e.g. repo root → internal_mobility subfolder)
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from config import APP_NAME, VERSION
from utils.auth import clear_session

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st.title(f"🚀 {APP_NAME}")
    st.caption(f"v{VERSION}")
    st.divider()

    logged_in = st.session_state.get("logged_in", False)
    role = st.session_state.get("role", "")

    if logged_in:
        st.markdown(f"👤 **{st.session_state.get('full_name', '')}**")
        st.caption(st.session_state.get("department", ""))
        st.divider()

        if role == "employee":
            st.page_link("pages/employee_dashboard.py", label="My Dashboard", icon="🏠")
            st.page_link("pages/job_listings.py", label="Job Listings", icon="💼")
            st.page_link("pages/my_applications.py", label="My Applications", icon="📋")

        elif role == "hr":
            st.page_link("pages/hr_dashboard.py", label="HR Dashboard", icon="🏢")
            st.page_link("pages/job_management.py", label="Job Management", icon="⚙️")
            st.page_link("pages/ml_insights.py", label="ML Insights", icon="🤖")
            st.page_link("pages/job_listings.py", label="Job Listings", icon="💼")

        st.divider()
        if st.button("Logout", use_container_width=True):
            clear_session()
            st.rerun()
    else:
        st.page_link("pages/login.py", label="Login", icon="🔐")
        # Only show Register when not logged in
        st.page_link("pages/register.py", label="Register", icon="📝")

# ── Home page ─────────────────────────────────────────────────────────────────
st.title(f"🚀 {APP_NAME}")
st.markdown("Internal talent mobility platform — connecting employees with internal opportunities.")

if not logged_in:
    st.info("Please log in or register to get started.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login", use_container_width=True, type="primary"):
            st.switch_page("pages/login.py")
    with col2:
        if st.button("Register", use_container_width=True):
            st.switch_page("pages/register.py")
else:
    st.success(f"Welcome back, {st.session_state['full_name']}!")
    # Grey out register — show disabled button instead
    col1, col2 = st.columns(2)
    with col1:
        if role == "hr":
            if st.button("Go to HR Dashboard", type="primary", use_container_width=True):
                st.switch_page("pages/hr_dashboard.py")
        else:
            if st.button("Go to My Dashboard", type="primary", use_container_width=True):
                st.switch_page("pages/employee_dashboard.py")
    with col2:
        st.button("Register", use_container_width=True, disabled=True, help="You are already logged in")
