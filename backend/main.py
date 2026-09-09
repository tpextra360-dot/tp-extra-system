import io
import os
import random
import string
import traceback
from datetime import date
from decimal import Decimal
from typing import List, Optional

import firebase_admin
from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import credentials, storage
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

# รองรับการ Import ฐานข้อมูลทั้งแบบรันในโฟลเดอร์นอกและใน
try:
    from backend.database import get_db_connection
except ImportError:
    from database import get_db_connection

app = FastAPI(
    title="TP EXTRA SYSTEM API",
    version="1.0.0",
    description="ระบบนิเวศเศรษฐกิจชุมชนแบบปิดลูปและบริหารจัดการสายงาน"
)

# 1. ตั้งค่าความปลอดภัย CORS
origins = [
    "https://frontend-seven-gray-82.vercel.app",
    "https://liff.line.me",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. ป้องกันระบบแครชและตั้งค่า Firebase ครั้งเดียวตอนเริ่มรันแอป
firebase_initialized = False
if not firebase_admin._apps:
    # เช็คหาไฟล์คีย์ทั้งในโฟลเดอร์ backend/ และ root/
    firebase_key_path = os.getenv("FIREBASE_KEY_PATH", "backend/firebase-key.json")
    if not os.path.exists(firebase_key_path):
        firebase_key_path = "firebase-key.json"

    if os.path.exists(firebase_key_path):
        try:
            cred = credentials.Certificate(firebase_key_path)
            firebase_admin.initialize_app(cred, {
                "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", "your-project-id.appspot.com")
            })
            firebase_initialized = True
            print("✅ Firebase initialized successfully.")
        except Exception as e:
            print(f"❌ Firebase Init Error: {e}")
    else:
        print("⚠️ Warning: Firebase key not found. Skipping Firebase initialization.")

# 3. Pydantic Schemas
class UserRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    phone_number: str = Field(..., pattern=r"^[0-9]{9,10}$")
    upline_member_code: Optional[str] = None
    line_user_id: Optional[str] = None
    birth_date: Optional[date] = None
    is_consent_age: bool = False

class PaperMemberItem(BaseModel):
    full_name: str
    phone_number: str = Field(..., pattern=r"^[0-9]{9,10}$")
    upline_member_code: Optional[str] = None
    birth_date: Optional[date] = None
    is_consent_age: bool = False

class BulkImportRequest(BaseModel):
    members: List[PaperMemberItem]

# --- Helper Functions ---

def generate_member_code():
    random_str = ''.join(random.choices(string.digits, k=5))
    return f"TPX-{random_str}"

def process_and_upload(image_bytes: bytes, size: int) -> str:
    if not firebase_admin._apps:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Firebase Storage ยังไม่พร้อมใช้งานบนเซิร์ฟเวอร์ ขาดไฟล์ firebase-key.json"
        )
    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGBA")
        icon = ImageOps.pad(img, (size, size), method=Image.Resampling.LANCZOS, color=(255, 255, 255, 0))
        output_buffer = io.BytesIO()
        icon.save(output_buffer, format="PNG", optimize=True)
        output_buffer.seek(0)

    bucket = storage.bucket()
    blob = bucket.blob(f"app_assets/icon-{size}x{size}.png")
    blob.upload_from_file(output_buffer, content_type="image/png")
    blob.make_public()
    return blob.public_url

# --- Endpoints ---

@app.get("/")
def read_root():
    return {"message": "TP EXTRA Backend is running optimally on Railway!"}

@app.post("/api/upload-slip")
async def upload_slip(file: UploadFile = File(...)):
    # จำลองส่งต่อผลการตรวจสลิป
    return {
        "status": "success",
        "ai_result": {
            "status": "success",
            "message": "ตรวจสอบสลิปผ่านเรียบร้อย",
            "data": {
                "extracted_amount": "500.00",
                "reference_no": "TX" + ''.join(random.choices(string.digits, k=10))
            }
        }
    }

@app.post("/api/v1/users/register", status_code=status.HTTP_201_CREATED)
def register_member(req: UserRegisterRequest):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # เช็คเบอร์ซ้ำ
            cursor.execute("SELECT id FROM users WHERE phone_number = %s", (req.phone_number,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="เบอร์โทรศัพท์นี้ลงทะเบียนแล้ว")

            # เช็คผู้แนะนำ
            upline_id = None
            if req.upline_member_code:
                cursor.execute("SELECT id FROM users WHERE member_code = %s", (req.upline_member_code,))
                upline = cursor.fetchone()
                if not upline:
                    raise HTTPException(status_code=404, detail="ไม่พบรหัสผู้แนะนำนี้ในระบบ")
                upline_id = upline["id"]

            member_code = generate_member_code()

            insert_user_sql = """
                INSERT INTO users (member_code, phone_number, full_name, line_user_id, upline_id, birth_date, is_consent_age)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_user_sql, (
                member_code, req.phone_number, req.full_name, req.line_user_id, upline_id, req.birth_date, req.is_consent_age
            ))
            new_user_id = cursor.lastrowid

            insert_wallet_sql = """
                INSERT INTO wallets (user_id, point_balance, copay_quota_balance, ytd_purchase_amount)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(insert_wallet_sql, (new_user_id, Decimal("0.00000"), Decimal("0.00000"), Decimal("0.00")))

            conn.commit()
            return {"status": "success", "message": "สมัครสมาชิกเรียบร้อย", "member_code": member_code}
            
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        print("DATABASE ERROR TRACEBACK:", traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database/Server Error: {str(e)}"
        )
    finally:
        conn.close()

@app.post("/api/v1/admin/bulk-import-paper", status_code=status.HTTP_201_CREATED)
def bulk_import_paper_members(req: BulkImportRequest):
    conn = get_db_connection()
    results = []
    try:
        with conn.cursor() as cursor:
            for item in req.members:
                cursor.execute("SELECT member_code FROM users WHERE phone_number = %s", (item.phone_number,))
                if cursor.fetchone():
                    continue

                upline_id = None
                if item.upline_member_code:
                    cursor.execute("SELECT id FROM users WHERE member_code = %s", (item.upline_member_code,))
                    upline = cursor.fetchone()
                    if upline:
                        upline_id = upline["id"]

                new_member_code = generate_member_code()
                cursor.execute("""
                    INSERT INTO users (member_code, phone_number, full_name, birth_date, is_consent_age, upline_id) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (new_member_code, item.phone_number, item.full_name, item.birth_date, item.is_consent_age, upline_id))
                new_user_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO wallets (user_id, point_balance, copay_quota_balance, ytd_purchase_amount) 
                    VALUES (%s, %s, %s, %s)
                """, (new_user_id, Decimal("0.00000"), Decimal("0.00000"), Decimal("0.00")))
                
                results.append({"phone": item.phone_number, "member_code": new_member_code})
            
            conn.commit()
            return {"status": "success", "imported_count": len(results), "details": results}
            
    except Exception as e:
        conn.rollback()
        print("DATABASE ERROR TRACEBACK:", traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database/Server Error: {str(e)}"
        )
    finally:
        conn.close()

@app.post("/api/v1/admin/upload-app-logo")
async def upload_app_logo(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="กรุณาอัปโหลดไฟล์รูปภาพเท่านั้น")

    image_bytes = await file.read()
    url_192 = process_and_upload(image_bytes, 192)
    url_512 = process_and_upload(image_bytes, 512)

    return {
        "status": "success",
        "icons": {
            "192": url_192,
            "512": url_512
        }
    }