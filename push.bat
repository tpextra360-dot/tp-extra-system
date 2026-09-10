@echo off
echo กำลังอัปเดตระบบขึ้น GitHub...
git add .
git commit -m "Quick update via automation script"
git push origin main
echo อัปเดตสำเร็จเรียบร้อย!
pause