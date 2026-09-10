import traceback
from dotenv import load_dotenv

load_dotenv()
from database import get_db_connection

def add_pin_column():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # เพิ่มคอลัมน์ pin_hash ลงในตาราง wallets
            cursor.execute("""
                ALTER TABLE wallets 
                ADD COLUMN pin_hash VARCHAR(255) NULL AFTER copay_quota_balance
            """)
            conn.commit()
            print("✅ เพิ่มคอลัมน์ pin_hash สำหรับเก็บรหัสลับเรียบร้อยแล้ว!")
    except Exception as e:
        print("⚠️ หมายเหตุ: ถ้าขึ้นเออเร่อ Duplicate column แปลว่าคอลัมน์นี้ถูกสร้างไปแล้ว ใช้งานต่อได้เลยครับ")
        print(e)
    finally:
        conn.close()

if __name__ == "__main__":
    add_pin_column()