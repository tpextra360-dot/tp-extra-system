import os
import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    # รองรับทั้งแบบขึ้นต้นด้วย MYSQL และ DB
    host = os.getenv("DB_HOST") or os.getenv("MYSQLHOST") or "localhost"
    user = os.getenv("DB_USER") or os.getenv("MYSQLUSER") or "root"
    password = os.getenv("DB_PASSWORD") or os.getenv("MYSQLPASSWORD") or ""
    database = os.getenv("DB_NAME") or os.getenv("MYSQLDATABASE") or "railway"
    port = int(os.getenv("DB_PORT") or os.getenv("MYSQLPORT") or 3306)

    return pymysql.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        port=port,
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=10
    )