import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "lang_observatory"),
        user=os.getenv("DB_USER", "observatory"),
        password=os.getenv("POSTGRES_PASSWORD")
    )
