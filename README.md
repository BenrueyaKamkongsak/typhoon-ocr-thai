# Typhoon OCR ภาษาไทย

เว็บแปลงเอกสารสแกนภาษาไทย (รูปหรือ PDF) เป็นข้อความ Markdown และตาราง ด้วยโมเดล
[Typhoon OCR](https://huggingface.co/scb10x/typhoon-ocr1.5-2b) ผ่าน API ของ opentyphoon.ai

- ใส่ API key ของตัวเอง (สมัครฟรีที่ https://playground.opentyphoon.ai) key เก็บไว้ในเบราว์เซอร์เท่านั้น
- รองรับ JPG, PNG, WebP และ PDF สูงสุด 20 หน้าต่อครั้ง
- ส่งออกเป็น Markdown และ CSV (เซลล์ผสานถูกกระจายให้ครบทุกช่อง)
- ไม่มีเซิร์ฟเวอร์ของตัวเอง ไฟล์ถูกส่งจากเบราว์เซอร์ไปที่ Typhoon API โดยตรง

`site/sample-th.jpg` เป็นเอกสารที่สร้างขึ้นเพื่อทดสอบ ชื่อหน่วยงานและบริษัทในเอกสารเป็นชื่อสมมติ

Libraries bundled in `site/vendor/`: pdf.js 3.11.174 (Apache-2.0), marked 12.0.2 (MIT), DOMPurify 3.0.8 (Apache-2.0 / MPL-2.0).
Deploys to GitHub Pages from `.github/workflows/pages.yml` on every push to `main`.
