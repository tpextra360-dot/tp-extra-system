import pymysql
import os

def get_db_connection():
    # ดึงค่าจาก Railway Environment Variables ถ้ามี
    host = os.getenv("MYSQLHOST", "127.0.0.1")
    port = int(os.getenv("MYSQLPORT", 3306))
    user = os.getenv("MYSQLUSER", "tpextra")
    password = os.getenv("MYSQLPASSWORD", "tp_password")
    database = os.getenv("MYSQLDATABASE", "tp_extra_db")

    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            cursorclass=pymysql.cursors.DictCursor
        )
        return connection
    except pymysql.MySQLError as e:
        print(f"Database connection failed: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        reference_no VARCHAR(50) NOT NULL,
                        expected_amount DECIMAL(10,2) NOT NULL,
                        extracted_amount DECIMAL(10,2) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            conn.commit()
            print("Database initialized successfully.")
        finally:
            conn.close()
