FROM python:3.10-slim

# ตั้งค่าพื้นที่ทำงานภายใน Container
WORKDIR /app

# คัดลอกไฟล์ requirements.txt และติดตั้งไลบรารี
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# คัดลอกโค้ดทั้งหมดในโฟลเดอร์ backend เข้าไป
COPY . .

# คำสั่งเปิดรันเซิร์ฟเวอร์ FastAPI (ใช้ 0.0.0.0 เพื่อให้ภายนอก Container เข้าถึงได้)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]