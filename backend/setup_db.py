import traceback
import os
from dotenv import load_dotenv

# 1. โหลดตัวแปรสภาพแวดล้อมจากไฟล์ .env ก่อนทำอย่างอื่น
load_dotenv()

# 2. ดึงฟังก์ชันเชื่อมต่อฐานข้อมูล
try:
    from database import get_db_connection
except ImportError:
    from backend.database import get_db_connection

def create_financial_tables():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            print("⏳ กำลังสร้างตารางกระเป๋าเงิน (wallets)...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wallets (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL UNIQUE,
                    point_balance DECIMAL(15, 5) DEFAULT 0.00000,
                    copay_quota_balance DECIMAL(15, 5) DEFAULT 0.00000,
                    status ENUM('ACTIVE', 'FROZEN') DEFAULT 'ACTIVE',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)

            print("⏳ กำลังสร้างตารางประวัติธุรกรรม (transactions)...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    reference_no VARCHAR(50) NOT NULL UNIQUE,
                    transaction_type ENUM('TOPUP', 'TRANSFER', 'PURCHASE', 'COMMISSION', 'WITHDRAW') NOT NULL,
                    description TEXT,
                    created_by INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            print("⏳ กำลังสร้างตารางสมุดบัญชีรายวัน (ledger_entries)...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ledger_entries (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    transaction_id INT NOT NULL,
                    wallet_id INT,
                    account_type ENUM('USER_WALLET', 'SYSTEM_REVENUE', 'SYSTEM_EXPENSE', 'SYSTEM_HOLDING') NOT NULL,
                    dr_amount DECIMAL(15, 5) DEFAULT 0.00000,
                    cr_amount DECIMAL(15, 5) DEFAULT 0.00000,
                    balance_snapshot DECIMAL(15, 5) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            print("✅ สร้างตารางบัญชีและการเงินเสร็จสมบูรณ์ พร้อมใช้งาน!")

    except Exception as e:
        print("❌ เกิดข้อผิดพลาดในการสร้างตาราง:")
        print(traceback.format_exc())
    finally:
        if 'conn' in locals() and conn.open:
            conn.close()

if __name__ == "__main__":
    create_financial_tables()