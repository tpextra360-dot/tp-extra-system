import io
import os
import json
import random
import string
import traceback
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

import firebase_admin
import jwt
from fastapi import FastAPI, File, HTTPException, UploadFile, status, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from firebase_admin import credentials, storage
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from passlib.context import CryptContext

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

# ==========================================
# 1. ตั้งค่าความปลอดภัย CORS & Firebase
# ==========================================
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

if not firebase_admin._apps:
    try:
        firebase_cred_json = os.getenv("FIREBASE_CREDENTIALS")
        bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET", "your-project-id.appspot.com") 
        
        if firebase_cred_json:
            cred_dict = json.loads(firebase_cred_json)
            cred = credentials.Certificate(cred_dict)
            print("✅ โหลด Firebase Credentials จาก Railway Environment")
        else:
            firebase_key_path = "backend/firebase-key.json" if os.path.exists("backend/firebase-key.json") else "firebase-key.json"
            cred = credentials.Certificate(firebase_key_path)
            print("✅ โหลด Firebase Credentials จากไฟล์ Local")
        
        firebase_admin.initialize_app(cred, {"storageBucket": bucket_name})
    except Exception as e:
        print(f"❌ Firebase Init Error (ระบบอัปโหลดรูปอาจไม่ทำงาน): {e}")

# ==========================================
# 2. ระบบรักษาความปลอดภัย (JWT & RBAC)
# ==========================================
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "tp-extra-super-secret-key-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # บัตรผ่านมีอายุ 1 วัน

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/line-login")

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        role: str = payload.get("role")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token ไม่ถูกต้อง")
        return {"user_id": user_id, "role": role, "line_user_id": payload.get("line_user_id")}
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token หมดอายุ กรุณาล็อกอินใหม่")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token ไม่สามารถยืนยันตัวตนได้")

def require_role(allowed_roles: list):
    def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] == "SUPER_ADMIN":
            return current_user
        if current_user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์เข้าถึงข้อมูลส่วนนี้")
        return current_user
    return role_checker

# ==========================================
# 3. Pydantic Schemas (โมเดลข้อมูล)
# ==========================================
class LineLoginRequest(BaseModel):
    line_user_id: str
    display_name: str = ""

class UserRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    phone_number: str = Field(..., pattern=r"^[0-9]{9,10}$")
    upline_member_code: Optional[str] = None
    line_user_id: Optional[str] = None
    birth_date: Optional[date] = None
    is_consent_age: bool = False

class AddCustomFieldRequest(BaseModel):
    table_name: str = "users"
    field_name: str
    field_type: str
    field_label: str
    is_required: bool = False

class PaperMemberItem(BaseModel):
    full_name: str
    phone_number: str = Field(..., pattern=r"^[0-9]{9,10}$")
    upline_member_code: Optional[str] = None
    birth_date: Optional[date] = None
    is_consent_age: bool = False

class BulkImportRequest(BaseModel):
    members: List[PaperMemberItem]

class TransferRequest(BaseModel):
    receiver_member_code: str = Field(..., description="รหัสสมาชิกของผู้รับเงิน")
    amount: Decimal = Field(..., gt=0, description="จำนวนเงินต้องมากกว่า 0")
    description: Optional[str] = "โอนเงินระหว่างสมาชิก"
    pin: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$", description="รหัส PIN 6 หลักเพื่อยืนยัน")

class SetPinRequest(BaseModel):
    pin: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$", description="รหัส PIN 6 หลัก (ตัวเลขเท่านั้น)")

# ==========================================
# 4. Helper Functions (ฟังก์ชันตัวช่วย)
# ==========================================
# ตั้งค่าระบบเข้ารหัส PIN แบบ bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_pin(plain_pin, hashed_pin):
    return pwd_context.verify(plain_pin, hashed_pin)

def get_pin_hash(pin):
    return pwd_context.hash(pin)

def generate_member_code():
    random_str = ''.join(random.choices(string.digits, k=5))
    return f"TPX-{random_str}"

def process_and_upload_to_firebase(file_bytes: bytes, target_width: int, target_height: int, folder_name: str) -> str:
    if not firebase_admin._apps:
        raise HTTPException(status_code=503, detail="Firebase Storage ยังไม่พร้อมใช้งาน")

    image = Image.open(io.BytesIO(file_bytes))
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    
    image.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
    
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='WEBP', quality=85, optimize=True)
    img_byte_arr.seek(0)
    
    import uuid
    filename = f"{folder_name}/{uuid.uuid4().hex}.webp"
    bucket = storage.bucket()
    blob = bucket.blob(filename)
    blob.upload_from_file(img_byte_arr, content_type='image/webp')
    blob.make_public()
    
    return blob.public_url

# ==========================================
# 5. API Endpoints
# ==========================================
@app.get("/")
def read_root():
    return {"message": "TP EXTRA Backend is running optimally on Railway!"}

# --- 5.1 Auth API (แลก Token) ---
@app.post("/api/v1/auth/line-login")
def login_via_line(req: LineLoginRequest):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    SELECT u.id, u.line_user_id, r.role_name 
                    FROM users u
                    LEFT JOIN roles r ON u.role_id = r.id
                    WHERE u.line_user_id = %s
                """, (req.line_user_id,))
            except Exception:
                cursor.execute("SELECT id, line_user_id, 'MEMBER' as role_name FROM users WHERE line_user_id = %s", (req.line_user_id,))
            
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="ยังไม่ได้ลงทะเบียนสมาชิก")

            user_role = user["role_name"] if user.get("role_name") else "MEMBER"
            access_token = create_access_token(
                data={"sub": user["id"], "line_user_id": user["line_user_id"], "role": user_role},
                expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            )
            return {"status": "success", "access_token": access_token, "token_type": "bearer", "role": user_role}
    finally:
        conn.close()

# --- 5.2 Member API (ล็อกด้วย Token) ---
@app.get("/api/v1/users/me")
def get_my_profile(current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT u.member_code, u.full_name, w.point_balance 
                FROM users u
                LEFT JOIN wallets w ON u.id = w.user_id
                WHERE u.id = %s
            """, (current_user["user_id"],))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="ไม่พบข้อมูลผู้ใช้")
            return {
                "status": "success", 
                "member_code": user["member_code"], 
                "full_name": user["full_name"],
                "balance": user["point_balance"] if user["point_balance"] else 0.00
            }
    finally:
        conn.close()

@app.post("/api/v1/users/register", status_code=status.HTTP_201_CREATED)
def register_member(req: UserRegisterRequest):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE phone_number = %s", (req.phone_number,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="เบอร์โทรศัพท์นี้ลงทะเบียนแล้ว")

            upline_id = None
            if req.upline_member_code == "COMPANY-ROOT":
                cursor.execute("SELECT id FROM users WHERE upline_id IS NULL")
                if cursor.fetchone():
                    raise HTTPException(status_code=400, detail="รหัสบริษัทต้นกำเนิดถูกสร้างไปแล้ว")
                member_code = "TPX-00001"
            else:
                if not req.upline_member_code:
                    raise HTTPException(status_code=400, detail="กรุณาระบุรหัสผู้แนะนำ")
                cursor.execute("SELECT id FROM users WHERE member_code = %s", (req.upline_member_code,))
                upline = cursor.fetchone()
                if not upline:
                    raise HTTPException(status_code=404, detail="ไม่พบรหัสผู้แนะนำนี้ในระบบ")
                upline_id = upline["id"]
                member_code = generate_member_code()

            cursor.execute("""
                INSERT INTO users (member_code, phone_number, full_name, line_user_id, upline_id, birth_date, is_consent_age)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (member_code, req.phone_number, req.full_name, req.line_user_id, upline_id, req.birth_date, req.is_consent_age))
            
            cursor.execute("INSERT INTO wallets (user_id, point_balance, copay_quota_balance, ytd_purchase_amount) VALUES (%s, %s, %s, %s)", 
                          (cursor.lastrowid, Decimal("0.00"), Decimal("0.00"), Decimal("0.00")))
            conn.commit()
            return {"status": "success", "message": "สมัครสมาชิกเรียบร้อย", "member_code": member_code}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# --- 5.3 Admin API (ล็อกด้วย Token + สิทธิ์ SUPER_ADMIN) ---
@app.get("/api/v1/admin/dashboard-stats")
def get_admin_stats(current_user: dict = Depends(require_role(["SUPER_ADMIN"]))):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as total FROM users")
            total_users = cursor.fetchone()["total"]
            cursor.execute("SELECT COUNT(*) as total FROM users WHERE member_type = 'JURISTIC'")
            total_juristic = cursor.fetchone()["total"]
            total_roles = 0 
            return {
                "total_users": total_users,
                "total_juristic": total_juristic,
                "total_individual": total_users - total_juristic,
                "total_roles": total_roles
            }
    finally:
        conn.close()

@app.post("/api/v1/admin/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    usage_type: str = Form("general"),
    current_user: dict = Depends(require_role(["SUPER_ADMIN"]))
):
    contents = await file.read()
    if usage_type == "icon":
        url = process_and_upload_to_firebase(contents, 192, 192, "logos")
    elif usage_type == "profile":
        url = process_and_upload_to_firebase(contents, 400, 400, "profiles")
    elif usage_type == "banner":
        url = process_and_upload_to_firebase(contents, 1200, 600, "banners")
    else:
        url = process_and_upload_to_firebase(contents, 800, 800, "products")
        
    return {"status": "success", "message": "อัปโหลดและบีบอัดภาพขึ้น Firebase สำเร็จ", "image_url": url}

@app.post("/api/v1/admin/add-field")
def admin_add_field(req: AddCustomFieldRequest, current_user: dict = Depends(require_role(["SUPER_ADMIN"]))):
    import re
    if not re.match(r'^[a-zA-Z0-9_]+$', req.field_name):
        raise HTTPException(status_code=400, detail="ชื่อฟิลด์ต้องเป็นภาษาอังกฤษ ตัวเลข หรือ _ เท่านั้น")

    type_mapping = {"TEXT": "VARCHAR(255) NULL", "NUMBER": "BIGINT NULL", "DECIMAL": "DECIMAL(15, 2) NULL", "DATE": "DATE NULL", "BOOLEAN": "BOOLEAN DEFAULT FALSE"}
    mysql_type = type_mapping.get(req.field_type.upper(), "VARCHAR(255) NULL")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            alter_sql = f"ALTER TABLE `{req.table_name}` ADD COLUMN `{req.field_name}` {mysql_type}"
            cursor.execute(alter_sql)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS form_field_configs (
                    id INT AUTO_INCREMENT PRIMARY KEY, table_name VARCHAR(50), field_name VARCHAR(100) UNIQUE,
                    field_label VARCHAR(255), field_type VARCHAR(50), is_required BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                INSERT INTO form_field_configs (table_name, field_name, field_label, field_type, is_required)
                VALUES (%s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE field_label = %s, is_required = %s
            """, (req.table_name, req.field_name, req.field_label, req.field_type, req.is_required, req.field_label, req.is_required))
            conn.commit()
            return {"status": "success", "message": f"เพิ่มฟิลด์ `{req.field_name}` สำเร็จ"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"ไม่สามารถเพิ่มฟิลด์ได้: {e}")
    finally:
        conn.close()

# ==========================================
# 6. API ระบบการเงินและกระเป๋าเงิน (Wallet)
# ==========================================
@app.post("/api/v1/wallets/set-pin")
def set_wallet_pin(req: SetPinRequest, current_user: dict = Depends(get_current_user)):
    """API สำหรับตั้งหรือเปลี่ยนรหัส PIN 6 หลัก"""
    conn = get_db_connection()
    try:
        hashed_pin = get_pin_hash(req.pin)
        with conn.cursor() as cursor:
            cursor.execute("UPDATE wallets SET pin_hash = %s WHERE user_id = %s", (hashed_pin, current_user["user_id"]))
            conn.commit()
            return {"status": "success", "message": "ตั้งรหัส PIN 6 หลักเรียบร้อยแล้ว"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/api/v1/wallets/transfer")
def transfer_points(req: TransferRequest, current_user: dict = Depends(get_current_user)):
    """API โอนเงิน พร้อมตรวจสอบรหัส PIN"""
    conn = get_db_connection()
    sender_id = current_user["user_id"]
    
    try:
        with conn.cursor() as cursor:
            # 1. ค้นหาผู้รับ
            cursor.execute("SELECT id, full_name FROM users WHERE member_code = %s", (req.receiver_member_code,))
            receiver = cursor.fetchone()
            if not receiver:
                raise HTTPException(status_code=404, detail="ไม่พบรหัสสมาชิกผู้รับในระบบ")
            receiver_id = receiver["id"]
            
            if sender_id == receiver_id:
                raise HTTPException(status_code=400, detail="ไม่สามารถโอนเงินให้ตัวเองได้")

            cursor.execute("START TRANSACTION")
            
            # 2. ล็อกกระเป๋าผู้โอน พร้อมดึง pin_hash มาตรวจสอบ
            cursor.execute("SELECT id, point_balance, pin_hash FROM wallets WHERE user_id = %s FOR UPDATE", (sender_id,))
            sender_wallet = cursor.fetchone()
            
            # --- ตรวจสอบความปลอดภัย ---
            if not sender_wallet or not sender_wallet.get("pin_hash"):
                raise HTTPException(status_code=400, detail="กรุณาตั้งรหัส PIN ก่อนทำธุรกรรม")
                
            if not verify_pin(req.pin, sender_wallet["pin_hash"]):
                raise HTTPException(status_code=401, detail="รหัส PIN ไม่ถูกต้อง")
            
            if sender_wallet["point_balance"] < req.amount:
                raise HTTPException(status_code=400, detail="ยอดเงินคงเหลือไม่เพียงพอ")
                
            # 3. ล็อกกระเป๋าผู้รับ
            cursor.execute("SELECT id, point_balance FROM wallets WHERE user_id = %s FOR UPDATE", (receiver_id,))
            receiver_wallet = cursor.fetchone()
            if not receiver_wallet:
                raise HTTPException(status_code=400, detail="ผู้รับยังไม่ได้เปิดใช้งานกระเป๋าเงิน")

            # 4. คำนวณและอัปเดตยอด
            new_sender_balance = sender_wallet["point_balance"] - req.amount
            new_receiver_balance = receiver_wallet["point_balance"] + req.amount

            cursor.execute("UPDATE wallets SET point_balance = %s WHERE id = %s", (new_sender_balance, sender_wallet["id"]))
            cursor.execute("UPDATE wallets SET point_balance = %s WHERE id = %s", (new_receiver_balance, receiver_wallet["id"]))

            # 5. บันทึก Transaction
            ref_no = f"TX-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"
            cursor.execute("""
                INSERT INTO transactions (reference_no, transaction_type, description, created_by)
                VALUES (%s, 'TRANSFER', %s, %s)
            """, (ref_no, req.description, sender_id))
            transaction_id = cursor.lastrowid

            # 6. ลงบัญชีแยกประเภท (GL)
            cursor.execute("""
                INSERT INTO ledger_entries (transaction_id, wallet_id, account_type, dr_amount, cr_amount, balance_snapshot)
                VALUES (%s, %s, 'USER_WALLET', %s, 0.00, %s)
            """, (transaction_id, sender_wallet["id"], req.amount, new_sender_balance))

            cursor.execute("""
                INSERT INTO ledger_entries (transaction_id, wallet_id, account_type, dr_amount, cr_amount, balance_snapshot)
                VALUES (%s, %s, 'USER_WALLET', 0.00, %s, %s)
            """, (transaction_id, receiver_wallet["id"], req.amount, new_receiver_balance))

            conn.commit()
            
            return {
                "status": "success",
                "message": f"โอนเงินให้ {receiver['full_name']} จำนวน {req.amount} เรียบร้อยแล้ว",
                "reference_no": ref_no,
                "remaining_balance": new_sender_balance
            }

    except HTTPException:
        conn.rollback() 
        raise
    except Exception as e:
        conn.rollback() 
        print("TRANSFER ERROR TRACEBACK:", traceback.format_exc())
        raise HTTPException(status_code=500, detail="ระบบขัดข้อง ไม่สามารถทำรายการได้ในขณะนี้")
    finally:
        conn.close()

@app.get("/api/v1/wallets/history")
def get_transaction_history(current_user: dict = Depends(get_current_user)):
    """API สำหรับดึงประวัติการทำรายการของตัวเอง (สูงสุด 50 รายการล่าสุด)"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    t.reference_no, 
                    t.transaction_type, 
                    t.description, 
                    t.created_at,
                    le.dr_amount, 
                    le.cr_amount, 
                    le.balance_snapshot
                FROM ledger_entries le
                JOIN transactions t ON le.transaction_id = t.id
                JOIN wallets w ON le.wallet_id = w.id
                WHERE w.user_id = %s
                ORDER BY t.created_at DESC
                LIMIT 50
            """, (current_user["user_id"],))
            records = cursor.fetchall()
            
            history = []
            for row in records:
                is_income = row["cr_amount"] > 0
                amount = row["cr_amount"] if is_income else row["dr_amount"]
                
                history.append({
                    "reference_no": row["reference_no"],
                    "type": row["transaction_type"],
                    "description": row["description"] or "ไม่มีบันทึกช่วยจำ",
                    "date": row["created_at"].strftime("%d/%m/%Y %H:%M"),
                    "is_income": bool(is_income),
                    "amount": float(amount),
                    "balance": float(row["balance_snapshot"])
                })
                
            return {"status": "success", "data": history}
    except Exception as e:
        import traceback
        print("HISTORY ERROR TRACEBACK:", traceback.format_exc())
        raise HTTPException(status_code=500, detail="ไม่สามารถดึงข้อมูลประวัติการทำรายการได้")
    finally:
        conn.close()

@app.post("/api/v1/wallets/topup-slip")
async def topup_via_slip(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """API สำหรับอัปโหลดสลิปโอนเงินเข้าบริษัท พร้อมจำลองระบบตรวจสอบ"""
    conn = get_db_connection()
    user_id = current_user["user_id"]
    
    try:
        contents = await file.read()
        slip_url = process_and_upload_to_firebase(contents, 800, 800, "slips")

        extracted_amount = Decimal("500.00") 
        bank_ref = f"BANK-REF-{''.join(random.choices(string.digits, k=8))}"

        with conn.cursor() as cursor:
            cursor.execute("START TRANSACTION")
            
            cursor.execute("SELECT id, point_balance FROM wallets WHERE user_id = %s FOR UPDATE", (user_id,))
            wallet = cursor.fetchone()
            
            if not wallet:
                raise HTTPException(status_code=400, detail="ไม่พบกระเป๋าเงินของคุณ")

            new_balance = wallet["point_balance"] + extracted_amount
            
            cursor.execute("UPDATE wallets SET point_balance = %s WHERE id = %s", (new_balance, wallet["id"]))
            
            tx_ref = f"TX-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"
            description = f"เติมเงินผ่านสลิป (อ้างอิง: {bank_ref})"
            cursor.execute("""
                INSERT INTO transactions (reference_no, transaction_type, description, created_by)
                VALUES (%s, 'TOPUP', %s, %s)
            """, (tx_ref, description, user_id))
            transaction_id = cursor.lastrowid
            
            cursor.execute("""
                INSERT INTO ledger_entries (transaction_id, wallet_id, account_type, dr_amount, cr_amount, balance_snapshot)
                VALUES (%s, NULL, 'SYSTEM_HOLDING', %s, 0.00, 0.00)
            """, (transaction_id, extracted_amount))
            
            cursor.execute("""
                INSERT INTO ledger_entries (transaction_id, wallet_id, account_type, dr_amount, cr_amount, balance_snapshot)
                VALUES (%s, %s, 'USER_WALLET', 0.00, %s, %s)
            """, (transaction_id, wallet["id"], extracted_amount, new_balance))
            
            conn.commit()
            
            return {
                "status": "success", 
                "message": "ตรวจสอบสลิปและเติมเงินสำเร็จ!", 
                "amount": float(extracted_amount),
                "new_balance": float(new_balance),
                "slip_url": slip_url
            }

    except Exception as e:
        conn.rollback()
        import traceback
        print("TOPUP ERROR:", traceback.format_exc())
        raise HTTPException(status_code=500, detail="เกิดข้อผิดพลาดในการตรวจสอบสลิป")
    finally:
        conn.close()