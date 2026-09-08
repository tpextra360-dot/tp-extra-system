import cv2
import numpy as np
from pyzbar.pyzbar import decode
import re
import datetime

class SmartSlipEngine:
    def __init__(self):
        # ในระบบจริง สามารถเสียบ Google Cloud Vision หรือ EasyOCR ตรงนี้ได้
        self.ocr_enabled = True 

    def process_image(self, image_bytes: bytes, pos_amount: float):
        """
        กระบวนการหลัก: รับภาพสลิป และยอดเงินที่ต้องชำระจาก POS
        """
        # 1. แปลง Bytes เป็นภาพ OpenCV
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return {"status": "error", "message": "ไม่สามารถอ่านไฟล์ภาพได้"}

        # 2. Phase 1: พยายามอ่าน QR Code ก่อน (เร็วและแม่นยำที่สุด)
        qr_data = self._extract_qr(img)
        
        extracted_amount = 0.0
        reference_no = ""
        method_used = "None"

        if qr_data:
            # สมมติฐาน: ถอดรหัส QR ออกมาได้ (ต้องใช้ไลบรารีถอดรหัส PromptPay มาตรฐาน)
            # ในที่นี้เป็นการจำลองการดึงข้อมูลจาก payload
            extracted_amount = self._parse_amount_from_qr(qr_data)
            reference_no = "REF-" + datetime.datetime.now().strftime("%Y%md%H%M%S")
            method_used = "QR_Code_Extraction"
        else:
            # 3. Phase 2: ถ้าไม่มี QR ให้ใช้ OCR + Regex (Fallback)
            ocr_text = self._fallback_ocr(img)
            extracted_amount = self._extract_amount_regex(ocr_text)
            reference_no = "OCR-" + datetime.datetime.now().strftime("%Y%md%H%M%S")
            method_used = "OCR_Regex_Extraction"

        # 4. Phase 3: ตรวจสอบยอดเงิน (Cross-Validation)
        is_matched = (extracted_amount == pos_amount) and (extracted_amount > 0)

        # 5. Phase 4: สร้างบันทึกบัญชี (Debit/Credit)
        accounting_entry = self._generate_accounting(extracted_amount, is_matched)

        return {
            "status": "success" if is_matched else "warning",
            "message": "ตรวจสอบสลิปสำเร็จ" if is_matched else "ยอดเงินไม่ตรงกับระบบ POS",
            "extraction_method": method_used,
            "data": {
                "extracted_amount": extracted_amount,
                "pos_expected_amount": pos_amount,
                "reference_no": reference_no,
                "is_valid": is_matched
            },
            "accounting_entry": accounting_entry
        }

    def _extract_qr(self, img):
        """ ฟังก์ชันสแกน QR Code จากภาพ """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        decoded_objects = decode(gray)
        for obj in decoded_objects:
            return obj.data.decode("utf-8")
        return None

    def _parse_amount_from_qr(self, qr_text):
        """ 
        ถอดรหัส Tag 54 จาก PromptPay QR Payload (แบบจำลอง)
        ระบบจริงต้องเขียน Parser อ่านโครงสร้าง TLV (Tag-Length-Value)
        """
        # สมมติว่าดึงยอดเงินมาได้จากการถอดรหัส
        return 500.00 

    def _fallback_ocr(self, img):
        """ ฟังก์ชัน OCR จำลอง (สามารถใช้ pytesseract, easyocr, หรือ Google Vision) """
        # แปลงภาพเพื่อเตรียมทำ OCR (Preprocessing)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        
        # คืนค่าข้อความจำลอง
        return "โอนเงินสำเร็จ\nจำนวนเงิน 500.00 บาท\nวันที่ 06 ก.ย. 2026"

    def _extract_amount_regex(self, text):
        """ ใช้ Regex ค้นหาตัวเลขที่อยู่หลังคำว่า จำนวนเงิน หรือ Amount """
        pattern = r"(?:จำนวนเงิน|Amount|ยอดเงิน)[\s:]*([0-9,]+(?:\.[0-9]{2})?)"
        match = re.search(pattern, text)
        if match:
            amount_str = match.group(1).replace(",", "")
            return float(amount_str)
        return 0.0

    def _generate_accounting(self, amount, is_valid):
        """ สร้าง Data Structure สำหรับลงบัญชีระบบ Multi-Tenant """
        if not is_valid or amount <= 0:
            return None
            
        return {
            "transaction_date": datetime.datetime.now().isoformat(),
            "ledger": [
                {
                    "account_type": "Asset",
                    "account_name": "Cash in Bank (เงินฝากธนาคาร)",
                    "type": "Debit",
                    "amount": amount
                },
                {
                    "account_type": "Revenue",
                    "account_name": "Sales Revenue (รายได้จากการขาย)",
                    "type": "Credit",
                    "amount": amount
                }
            ]
        }