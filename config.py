import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "internal_mobility_db"),
    "port":     int(os.getenv("DB_PORT", 3306)),
}

APP_NAME = "InternalMobility Hub"
VERSION  = "1.0.0"
