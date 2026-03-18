import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

def _get(key: str, default=None):
    """Read from Streamlit secrets first, then env vars, then default."""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)

DB_CONFIG = {

    DB_HOST = "mysql.railway.internal"
    DB_USER = "root"
    DB_PASSWORD = "KxUqYodTNQJIjIsSegUemjINzpqQriMT"
    DB_NAME = "railway"
    DB_PORT = 33602
    "host": st.secrets["DB_HOST"],
    "user": st.secrets["DB_USER"],
    "password": st.secrets["DB_PASSWORD"],
    "database": st.secrets["DB_NAME"],
    "port": st.secrets["DB_PORT"]
    "auth_plugin": "mysql_native_password"
}
APP_NAME = "InternalMobility Hub"
VERSION  = "1.0.0"
