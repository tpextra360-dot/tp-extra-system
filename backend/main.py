from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from services.ai_engine import SmartSlipEngine
from database import init_db, get_db_connection

app = FastAPI(title="TP EXTRA SYSTEM Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

slip_engine = SmartSlipEngine()

# สั่งให้สร้างตารางในฐานข้อมูลตอนที่เซิร์ฟเวอร์เริ่มทำงาน
@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/")
def health_check():
    return {"status": "ok", "message": "API is running."}

@app.post("/api/upload-slip")
async def process_slip(
    file: UploadFile = File(...),
    expected_amount: float = Form(0.0)
):
    try:
        image_bytes = await file.read()
        ai_result = slip_engine.process_image(image_bytes, expected_amount)
        
        # บันทึกข้อมูลลง MySQL หาก AI อ่านสำเร็จ
        if ai_result["status"] == "success":
            conn = get_db_connection()
            if conn:
                with conn.cursor() as cursor:
                    sql = """INSERT INTO transactions 
                             (reference_no, expected_amount, extracted_amount, status) 
                             VALUES (%s, %s, %s, %s)"""
                    data = ai_result["data"]
                    cursor.execute(sql, (
                        data["reference_no"], 
                        data["pos_expected_amount"], 
                        data["extracted_amount"], 
                        ai_result["status"]
                    ))
                conn.commit()
                conn.close()

        return {
            "filename": file.filename,
            "ai_result": ai_result,
            "saved_to_db": ai_result["status"] == "success"
        }
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)}"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)