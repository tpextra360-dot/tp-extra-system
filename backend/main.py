import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import pymysql
import os
from dotenv import load_dotenv

load_dotenv() 

app = FastAPI(title="TP Extra Full Backend Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    db_port = int(os.getenv("DB_PORT", 3306))
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=db_port,
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASS", ""),
        database=os.getenv("DB_NAME", "tp_extra_db"),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10
    )

# --- Pydantic Model (รับข้อมูลแบบสั้นจาก LINE) ---
class MinimalRegisterRequest(BaseModel):
    sponsor_code: str
    phone: str
    line_id: Optional[str] = None
    first_name: Optional[str] = None
    line_picture: Optional[str] = None
    consent_accepted: bool = True

# --- สร้างฐานข้อมูลอัตโนมัติ (เพิ่มช่อง LINE แล้ว) ---
def init_db():
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS member_wallets")
            cursor.execute("DROP TABLE IF EXISTS hq_sales")
            cursor.execute("DROP TABLE IF EXISTS members")
            
            cursor.execute("""
                CREATE TABLE members (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    member_code VARCHAR(20) UNIQUE NOT NULL,
                    sponsor_code VARCHAR(20),
                    phone VARCHAR(15) UNIQUE NOT NULL,
                    line_id VARCHAR(100) UNIQUE NULL,
                    first_name VARCHAR(100),
                    line_picture VARCHAR(255) NULL,
                    consent_accepted BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE member_wallets (
                    member_code VARCHAR(20) PRIMARY KEY,
                    cash_point DECIMAL(10, 2) DEFAULT 0.00,
                    shopping_point DECIMAL(10, 2) DEFAULT 0.00,
                    FOREIGN KEY (member_code) REFERENCES members(member_code)
                )
            """)
        conn.commit()
        conn.close()
        print("✅ ฐานข้อมูลพร้อมใช้งาน (รองรับระบบ LINE แล้ว)")
    except Exception as e:
        print(f"❌ สร้างฐานข้อมูลล้มเหลว: {str(e)}")

@app.on_event("startup")
def startup_event():
    init_db()

# --- API สมัครสมาชิกแบบสั้น ---
@app.post("/api/member/register")
def register_member(data: MinimalRegisterRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        conn.begin()
        
        # เช็กว่าเบอร์โทรนี้หรือ LINE นี้สมัครไปหรือยัง
        cursor.execute("SELECT id FROM members WHERE phone = %s OR line_id = %s FOR UPDATE", (data.phone, data.line_id))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="เบอร์โทรศัพท์ หรือบัญชี LINE นี้เป็นสมาชิกอยู่แล้ว")
            
        new_member_code = f"TP{data.phone[-6:]}"
        
        sql = """
            INSERT INTO members (
                member_code, sponsor_code, phone, line_id, first_name, line_picture, consent_accepted
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, (
            new_member_code, data.sponsor_code, data.phone, 
            data.line_id, data.first_name, data.line_picture, data.consent_accepted
        ))
        
        cursor.execute("INSERT INTO member_wallets (member_code) VALUES (%s)", (new_member_code,))
        
        conn.commit()
        return {"status": "success", "member_code": new_member_code, "message": "สมัครสมาชิกสำเร็จ"}
    except HTTPException as http_e:
        conn.rollback()
        raise http_e
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    