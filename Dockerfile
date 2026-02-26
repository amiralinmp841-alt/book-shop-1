# استفاده از نسخه پایدار پایتون
FROM python:3.11-slim

# جلوگیری از ساخت فایل pyc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ساخت پوشه کاری
WORKDIR /app

# کپی کردن requirements
COPY requirements.txt .

# نصب وابستگی‌ها
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# کپی کردن فایل‌های پروژه
COPY . .

# اجرای برنامه
CMD ["python", "main.py"]
