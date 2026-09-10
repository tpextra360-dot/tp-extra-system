// กำหนด URL ของ Backend
const API_BASE_URL = "https://tp-extra-system-production.up.railway.app";
const LIFF_ID = "2011278014-ykejPzwR"; // เปลี่ยนเป็น LIFF ID ของคุณ

async function initializeApp() {
    try {
        // 1. เริ่มต้น LIFF
        await liff.init({ liffId: LIFF_ID });
        
        // 2. ถ้ายังไม่ล็อกอิน ให้บังคับล็อกอินผ่าน LINE
        if (!liff.isLoggedIn()) {
            liff.login();
            return;
        }

        // 3. ดึงข้อมูลโปรไฟล์จาก LINE
        const profile = await liff.getProfile();
        console.log("LINE Profile:", profile);

        // 4. ส่ง LINE ID ไปแลก JWT Token จาก Backend
        await loginToBackend(profile);

    } catch (err) {
        console.error("LIFF Initialization failed", err);
        alert("เกิดข้อผิดพลาดในการเชื่อมต่อ LINE");
    }
}

async function loginToBackend(profile) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/v1/auth/line-login`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                line_user_id: profile.userId,
                display_name: profile.displayName
            })
        });

        if (response.ok) {
            const data = await response.json();
            
            // 5. บันทึก JWT Token และ Role ลงใน LocalStorage (กระเป๋าของบราวเซอร์)
            localStorage.setItem("tpx_access_token", data.access_token);
            localStorage.setItem("tpx_user_role", data.role);
            
            console.log("✅ ล็อกอินสำเร็จ! ได้รับ Token แล้ว");
            console.log("สิทธิ์ของคุณคือ:", data.role);

            // TODO: สามารถสั่งให้เปลี่ยนหน้าไป Dashboard ได้ที่นี่
            // window.location.href = "dashboard.html";
            
        } else if (response.status === 404) {
            // กรณีเป็นคนใหม่ ยังไม่เคยสมัครสมาชิก
            console.log("ผู้ใช้นี้ยังไม่ได้สมัครสมาชิก");
            // แสดงฟอร์มสมัครสมาชิก (ถ้าอยู่ในหน้า index.html)
            document.getElementById("register-form-section").classList.remove("hidden");
        } else {
            console.error("Login failed:", await response.text());
        }
    } catch (err) {
        console.error("Network error:", err);
    }
}