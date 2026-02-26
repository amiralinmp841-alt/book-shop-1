#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
fin_fixed.py
نسخهٔ نهایی اصلاح‌شده ربات مدیریت جزوات دانشگاه
...
"""

import json
from pathlib import Path
from typing import Dict, List
import logging
import uuid
import datetime
import os                          # ✅ اضافه شد
from dotenv import load_dotenv      # ✅ اضافه شد

# بارگذاری متغیرهای محیطی از .env یا تنظیمات Render
load_dotenv()                       # ✅ اضافه شد

import pandas as pd
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------------- CONFIG ----------------
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # پیش‌فرض ۰ اگه ست نشده باشه
DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"
PRODUCTS_FILE = DATA_DIR / "products.json"
ORDERS_FILE = DATA_DIR / "orders.json"            # finalized but unpaid
PENDING_PAYMENTS_FILE = DATA_DIR / "pending_payments.json"
PURCHASES_FILE = DATA_DIR / "purchases.json"      # approved purchases
BLOCKED_FILE = DATA_DIR / "blocked.json"
BACKUP_GROUP_ID = int(os.getenv("BACKUP_GROUP_ID", "0"))

# ---------------- LOG ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- STATE ENUM ----------------
(
    S_MAIN,
    S_REGISTER_NAME,
    S_REGISTER_DORM,
    S_REGISTER_OTHER_DORM,
    S_BUY_SELECT_PRODUCT,
    S_BUY_SELECT_TYPE,
    S_BUY_ENTER_QTY,
    S_AWAITING_RECEIPT,
    S_ADMIN_ADD_NAME,
    S_ADMIN_ADD_CHOOSE,
    S_ADMIN_ADD_COLOR_PRICE,
    S_ADMIN_ADD_BW_PRICE,
    S_ADMIN_LIST,
    S_ADMIN_DELETE_SELECT,
    S_ADMIN_BLOCK_ID,
    S_ADMIN_UNBLOCK_ID,
) = range(16)

# ---------------- STORAGE HELPERS ----------------
def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# --- 🔽 کد جدید برای ذخیره‌سازی ادمین‌ها ---
ADMINS_FILE = DATA_DIR / "admins.json"
admins = load_json(ADMINS_FILE, [])
# --- 🔽 اضافه کردن OTHER_ADMINS از متغیر محیطی ---
OTHER_ADMINS_ENV = os.getenv("OTHER_ADMINS_ID", "")

if OTHER_ADMINS_ENV:
    other_admins = [
        int(uid.strip())
        for uid in OTHER_ADMINS_ENV.split(",")
        if uid.strip().isdigit()
    ]

    for uid in other_admins:
        if uid not in admins:
            admins.append(uid)
# --- 🔼 پایان ---
# --- 🔼 پایان کد جدید ---


users: Dict[str, dict] = load_json(USERS_FILE, {})
products: Dict[str, dict] = load_json(PRODUCTS_FILE, {})
orders: Dict[str, list] = load_json(ORDERS_FILE, {})  # orders per user (finalized, unpaid)
pending_payments: Dict[str, dict] = load_json(PENDING_PAYMENTS_FILE, {})
purchases: Dict[str, list] = load_json(PURCHASES_FILE, {})
blocked: List[int] = load_json(BLOCKED_FILE, [])

def persist_all():
    save_json(USERS_FILE, users)
    save_json(PRODUCTS_FILE, products)
    save_json(ORDERS_FILE, orders)
    save_json(PENDING_PAYMENTS_FILE, pending_payments)
    save_json(PURCHASES_FILE, purchases)
    save_json(BLOCKED_FILE, blocked)
    # --- 🔽 ذخیره ادمین‌ها ---
    save_json(ADMINS_FILE, admins)
    # --- 🔼 پایان تغییر ---



# --- 🔽 تابع کمکی برای تشخیص ادمین ---
def is_admin(uid: int) -> bool:
    """بررسی می‌کند که آیا کاربر، ادمین اصلی یا یکی از ادمین‌های اضافه‌شده است یا نه"""
    return uid == ADMIN_ID or uid in admins
# --- 🔼 پایان تابع ---


# ---------------- HELPERS ----------------
DORMS = [
    "خوابگاه امام علی",
    "خوابگاه الزهرا",
    "خوابگاه رستاک",
    "خوابگاه سمیه",
    "خوابگاه دانش",
    "سایر خوابگاه ها",
]

def back_kb():
    return ReplyKeyboardMarkup([[KeyboardButton("🔙 بازگشت")]], resize_keyboard=True)

def user_main_keyboard(has_identity: bool):
    if not has_identity:
        kb = [[KeyboardButton("📝 ثبت اطلاعات هویتی")]]
        kb.append([KeyboardButton("🔙 بازگشت")])
        return ReplyKeyboardMarkup(kb, resize_keyboard=True)
    kb = [
        [KeyboardButton("🛒 انتخاب جزوه"), KeyboardButton("📦 سبد خرید")],
        [KeyboardButton("🗑 ویرایش سبد خرید"), KeyboardButton("✅ ثبت نهایی سبد خرید")],
        [KeyboardButton("📄 جزوات نهایی شده"), KeyboardButton("💳 خرید جزوات نهایی شده")],
        [KeyboardButton("📦 جزوات خریداری شده"), KeyboardButton("💬 چت با ادمین")],
        [KeyboardButton("✏️ ویرایش اطلاعات هویتی")]
    ]
    kb.append([KeyboardButton("🔙 بازگشت")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)
    kb = [
        [KeyboardButton("🛒 انتخاب جزوه"), KeyboardButton("📦 سبد خرید")],
        [KeyboardButton("🗑 ویرایش سبد خرید"), KeyboardButton("✅ ثبت نهایی سبد خرید")],
        [KeyboardButton("📄 جزوات نهایی شده"), KeyboardButton("💳 خرید جزوات نهایی شده")],
        [KeyboardButton("📦 جزوات خریداری شده"), KeyboardButton("💬 چت با ادمین")],
    ]
    kb.append([KeyboardButton("🔙 بازگشت")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def admin_main_keyboard():
    kb = [
        [KeyboardButton("➕ اضافه کردن جزوه"), KeyboardButton("📚 لیست جزوات")],
        [KeyboardButton("👥 اسامی ثبت نام نهایی کنندگان"), KeyboardButton("👤 اسامی خریداران")],
        [KeyboardButton("📚 جزوات خریداری شده"), KeyboardButton("📄 جزوات ثبت نهایی شده")],
        [KeyboardButton("🕓 فیش‌های در انتظار تایید"), KeyboardButton("📊 دریافت فایل اکسل خرید جزوات")],
        [KeyboardButton("⛔ مسدود کردن کاربر"), KeyboardButton("✅ رفع مسدودیت")],
    ]
    kb.append([KeyboardButton("📤 دریافت بکاپ"), KeyboardButton("📥 وارد کردن بکاپ")])

    kb.append([KeyboardButton("🔙 بازگشت")])
         # --- 🔽 دکمه جدید برای مدیریت ادمین‌ها ---
    kb.append([KeyboardButton("⚙️ مدیریت ادمین‌ها")])
    # --- 🔼 پایان کد جدید ---

    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def ensure_user(uid: int):
    key = str(uid)
    if key not in users:
        users[key] = {
            "first_name": None,
            "last_name": None,
            "is_dorm": False,
            "dorm_name": None,
            "cart": [],
            # orders stored in global 'orders' keyed by user id (string)
        }

def make_disp_name(u: dict) -> str:
    name = (u.get("first_name") or "").strip()
    lastname = (u.get("last_name") or "").strip()
    full = (name + " " + lastname).strip()
    if not full:
        full = "نام‌ثبت‌نشده"
    if u.get("is_dorm"):
        dorm = u.get("dorm_name") or "نام‌خوابگاه"
        return f"{full} ({dorm})"
    else:
        return f"{full} (تهرانی)"

def next_product_id() -> str:
    if not products:
        return "1"
    nums = [int(pid) for pid in products.keys() if pid.isdigit()]
    return str(max(nums) + 1 if nums else len(products) + 1)

def find_product_by_title(title: str):
    for pid, p in products.items():
        if p.get("title") == title:
            return pid, p
    return None, None

def update_user_name_everywhere(uid: int):
    key = str(uid)
    u = users.get(key)
    if not u:
        return
    # update in orders
    for uid_k, order_list in orders.items():
        for ord_entry in order_list:
            if ord_entry.get("user_id") == uid:
                ord_entry["first_name"] = u.get("first_name")
                ord_entry["last_name"] = u.get("last_name")
    # update pending payments
    for pay in pending_payments.values():
        if pay.get("user_id") == uid:
            pay["first_name"] = u.get("first_name")
            pay["last_name"] = u.get("last_name")
    # update purchases
    for pur_list in purchases.values():
        for pur in pur_list:
            if pur.get("user_id") == uid:
                pur["first_name"] = u.get("first_name")
                pur["last_name"] = u.get("last_name")
    persist_all()

# ---------------- HANDLERS ----------------

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in blocked:
        await update.message.reply_text("🚫 شما توسط ادمین مسدود شده‌اید.")
        return S_MAIN
    ensure_user(uid)
    has_identity = bool(users[str(uid)].get("first_name") and users[str(uid)].get("last_name"))
    if is_admin(uid):
        await update.message.reply_text("خوش آمدی ادمین V-1-0-3 ", reply_markup=admin_main_keyboard())
    else:
        await update.message.reply_text("سلام! به ربات سفارش جزوه خوش آمدید.", reply_markup=user_main_keyboard(has_identity))
    persist_all()
    return S_MAIN

# main text
async def handle_text_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id

    if uid in blocked:
        await update.message.reply_text("🚫 شما مسدود شده‌اید.")
        return S_MAIN

    ensure_user(uid)
    has_identity = bool(users[str(uid)].get("first_name") and users[str(uid)].get("last_name"))

    # If user is in "chat with admin" mode, forward messages to admin (except back)
    if uid != ADMIN_ID and context.user_data.get('chat_with_admin'):
        if text == "🔙 بازگشت":
            context.user_data.pop('chat_with_admin', None)
            await update.message.reply_text("چت با ادمین لغو شد.", reply_markup=user_main_keyboard(has_identity))
            return S_MAIN
        # forward text to admin with reply button
        caption = f"پیام از {make_disp_name(users[str(uid)])} — id:{uid}\n\n{text}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ پاسخ دادن", callback_data=f"reply_user:{uid}")]])
        await context.bot.send_message(chat_id=ADMIN_ID, text=caption, reply_markup=kb)
        await update.message.reply_text("پیام شما به ادمین ارسال شد.", reply_markup=user_main_keyboard(has_identity))
        return S_MAIN

    # require registration
    if uid != ADMIN_ID and not has_identity and text not in ("📝 ثبت اطلاعات هویتی", "🔙 بازگشت"):
        await update.message.reply_text("لطفا ابتدا اطلاعات هویتی خود را ثبت کنید.", reply_markup=user_main_keyboard(False))
        return S_MAIN

    # User flows
    if text == "✏️ ویرایش اطلاعات هویتی":
        key = str(uid)
        old = users.get(key, {}).copy()
        context.user_data['old_identity'] = old
        users[key].update({"first_name": None, "last_name": None, "is_dorm": False, "dorm_name": None})
        persist_all()
        await update.message.reply_text("اطلاعات قبلی پاک شد. لطفا نام و نام خانوادگی جدید را وارد کنید:", reply_markup=back_kb())
        return S_REGISTER_NAME


    if text == "📝 ثبت اطلاعات هویتی":
        await update.message.reply_text("لطفا نام و نام خانوادگی را (مثال: علی رضایی) وارد کنید:", reply_markup=back_kb())
        return S_REGISTER_NAME

    if text == "✏️ ویرایش اطلاعات هویتی":
        key = str(uid)
        old = users.get(key, {}).copy()
        context.user_data['old_identity'] = old
        users[key].update({"first_name": None, "last_name": None, "is_dorm": False, "dorm_name": None})
        persist_all()
        await update.message.reply_text("اطلاعات قبلی پاک شد. لطفا نام و نام خانوادگی جدید را وارد کنید:", reply_markup=back_kb())
        return S_REGISTER_NAME

    if text == "🛒 انتخاب جزوه":
        if not products:
            await update.message.reply_text("فعلا هیچ جزوه‌ای موجود نیست.", reply_markup=user_main_keyboard(has_identity))
            return S_MAIN
        kb = [[p['title']] for p in products.values()]
        kb.append(["🔙 بازگشت"])
        await update.message.reply_text("لطفا جزوه مورد نظر را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return S_BUY_SELECT_PRODUCT

    if text == "📦 سبد خرید":
        key = str(uid)
        cart = users[key]['cart']
        if not cart:
            await update.message.reply_text("سبد خرید شما خالی است.", reply_markup=user_main_keyboard(has_identity))
            return S_MAIN
        lines = []
        total = 0
        for i, item in enumerate(cart, 1):
            line = f"{i}. {item['title']} - {item['type']} - تعداد: {item['qty']} - قیمت واحد: {item['unit_price']}"
            lines.append(line)
            total += item['qty'] * item['unit_price']
        lines.append(f"\nجمع کل: {total}")
        await update.message.reply_text("\n".join(lines), reply_markup=user_main_keyboard(has_identity))
        return S_MAIN

    if text == "🗑 ویرایش سبد خرید":
        key = str(uid)
        cart = users[key]['cart']
        if not cart:
            await update.message.reply_text("سبد خرید خالی است", reply_markup=user_main_keyboard(has_identity))
            return S_MAIN
        kb = [[f"حذف: {i+1}. {c['title']} - {c['type']}"] for i, c in enumerate(cart)]
        kb.append(["🔙 بازگشت"])
        await update.message.reply_text("کدام مورد را حذف می‌کنید؟", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return S_BUY_SELECT_PRODUCT

    if text == "✅ ثبت نهایی سبد خرید":
        key = str(uid)
        cart = users[key]['cart']
        if not cart:
            await update.message.reply_text("سبد خرید شما خالی است.", reply_markup=user_main_keyboard(has_identity))
            return S_MAIN
        total = sum(item['qty'] * item['unit_price'] for item in cart)
        order = {
            "order_id": str(uuid.uuid4()),
            "user_id": uid,
            "first_name": users[key].get("first_name"),
            "last_name": users[key].get("last_name"),
            "items": cart.copy(),
            "total": total,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "paid": False,
        }
        orders.setdefault(str(uid), []).append(order)
        users[key]['cart'] = []
        persist_all()
        await update.message.reply_text(f"سبد شما ثبت نهایی شد. جمع کل: {total} تومان.\nبرای پرداخت به منوی «💳 خرید جزوات نهایی شده» بروید.", reply_markup=user_main_keyboard(has_identity))
        return S_MAIN

    if text == "📄 جزوات نهایی شده":
        key = str(uid)
        finalized = orders.get(key, [])
        if not finalized:
            await update.message.reply_text("شما تا کنون ثبت نهایی نداشته‌اید.", reply_markup=user_main_keyboard(has_identity))
            return S_MAIN
        lines = []
        for i, ord_entry in enumerate(finalized, 1):
            items_lines = "\n".join([f"- {it['title']} ({it['type']}) x {it['qty']}" for it in ord_entry.get('items', [])])
            lines.append(f"سفارش {i} — مجموع: {ord_entry.get('total',0)}\n{items_lines}")
        kb = [[KeyboardButton("🗑 پاک کردن لیست")], ["🔙 بازگشت"]]
        context.user_data['viewing_finalized'] = True
        await update.message.reply_text("\n\n".join(lines), reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return S_MAIN

    if text == "🗑 پاک کردن لیست":
        key = str(uid)
        if context.user_data.get('viewing_finalized'):
            orders.pop(key, None)
            context.user_data.pop('viewing_finalized', None)
            persist_all()
            await update.message.reply_text("لیست جزوات نهایی شده شما پاک شد.", reply_markup=user_main_keyboard(has_identity))
            return S_MAIN
        else:
            await update.message.reply_text("هیچ لیستی برای پاک کردن مشاهده نمی‌شود.", reply_markup=user_main_keyboard(has_identity))
            return S_MAIN

    if text == "💳 خرید جزوات نهایی شده":
        key = str(uid)
        finalized = orders.get(key, [])
        if not finalized:
            await update.message.reply_text("سفارشی برای پرداخت وجود ندارد.", reply_markup=user_main_keyboard(has_identity))
            return S_MAIN
        kb = [[f"سفارش: {i+1} - {o.get('total')} تومان"] for i,o in enumerate(finalized)]
        kb.append(["🔙 بازگشت"])
        context.user_data['finalized_list'] = finalized
        await update.message.reply_text("کدام سفارش را می‌خواهید پرداخت کنید؟", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return S_MAIN

    if text.startswith("سفارش:"):
        uid_key = str(uid)
        flist = context.user_data.get('finalized_list', [])
        # parse index
        try:
            idx = int(text.split()[1].split(":")[0]) - 1
        except Exception:
            idx = 0
        if idx < 0 or idx >= len(flist):
            idx = 0
        sel = flist[idx]
        context.user_data['pay_order_id'] = sel.get('order_id')
        await update.message.reply_text(f"شما سفارش با جمع {sel.get('total')} تومان را انتخاب کردید.\nلطفا فیش پرداخت را به صورت عکس ارسال کنید یا '🔙 بازگشت' را بزنید.", reply_markup=back_kb())
        return S_AWAITING_RECEIPT

    if text == "📦 جزوات خریداری شده":
        key = str(uid)
        pur = purchases.get(key, [])
        if not pur:
            await update.message.reply_text("شما هنوز خرید تایید شده‌ای ندارید.", reply_markup=user_main_keyboard(has_identity))
            return S_MAIN
        lines = []
        # Show per-purchase detail and aggregated totals with color/bw counts
        agg = {}
        for pch in pur:
            items = "\n".join([f"- {it['title']} ({it['type']}) x {it['qty']}" for it in pch.get('items',[])] )
            lines.append(f"{pch.get('purchase_id')} — مجموع: {pch.get('total')} تومان\n{items}")
            for it in pch.get('items', []):
                keyt = (it['title'], it['type'])
                agg[keyt] = agg.get(keyt, 0) + it.get('qty', 0)
        # show aggregated grouped by title with color/bw counts
        summary = {}
        for (title, typ), qty in agg.items():
            if title not in summary:
                summary[title] = {"رنگی": 0, "سیاه و سفید": 0}
            summary[title][typ] = summary[title].get(typ, 0) + qty
        lines2 = [f"{t} : رنگی {v['رنگی']} - سیاه و سفید {v['سیاه و سفید']}" for t,v in summary.items()]
        await update.message.reply_text("جزوات خریداری شده:\n\n" + "\n".join(lines2) + "\n\nجزئیات خریدها:\n\n" + "\n\n".join(lines), reply_markup=user_main_keyboard(has_identity))
        return S_MAIN

    if text == "💬 چت با ادمین":
        context.user_data['chat_with_admin'] = True
        await update.message.reply_text("حالا پیام خود را بنویسید؛ پیام شما به ادمین ارسال می‌شود. برای خروج '🔙 بازگشت' را بزنید.", reply_markup=back_kb())
        return S_MAIN

    # Admin area
    if is_admin(uid):
        return await handle_admin_main(update, context)

    # Back
    if text == "🔙 بازگشت":
        await update.message.reply_text("بازگشت به منوی اصلی", reply_markup=user_main_keyboard(has_identity))
        return S_MAIN

    await update.message.reply_text("گزینه نامشخص — از دکمه‌ها استفاده کنید.", reply_markup=user_main_keyboard(has_identity))
    return S_MAIN

# Registration
async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    if text == "🔙 بازگشت":
        await update.message.reply_text("لغو ثبت اطلاعات.", reply_markup=user_main_keyboard(bool(users.get(str(uid),{}).get("first_name"))))
        return S_MAIN
    parts = text.split()
    if len(parts) < 2:
        await update.message.reply_text("لطفا نام و نام‌خانوادگی را با فاصله وارد کنید (مثال: علی رضایی)", reply_markup=back_kb())
        return S_REGISTER_NAME
    first = parts[0]
    last = " ".join(parts[1:])
    key = str(uid)
    ensure_user(uid)
    users[key]['first_name'] = first
    users[key]['last_name'] = last
    persist_all()
    await update.message.reply_text("شما خوابگاهی هستید یا تهرانی؟", reply_markup=ReplyKeyboardMarkup([["تهرانی", "خوابگاهی"], ["🔙 بازگشت"]], resize_keyboard=True))
    return S_REGISTER_DORM

async def register_dorm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    key = str(uid)
    if text == "🔙 بازگشت":
        await update.message.reply_text("بازگشت", reply_markup=user_main_keyboard(bool(users[key].get("first_name"))))
        return S_MAIN
    if text == "تهرانی":
        users[key]['is_dorm'] = False
        users[key]['dorm_name'] = None
        await update.message.reply_text("اطلاعات هویتی تکمیل شد ✅️", reply_markup=user_main_keyboard(True))
        msg = f"کاربری ثبت نام کرد: {make_disp_name(users[key])} — آیدی: {uid}"
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg)
        persist_all()
        if 'old_identity' in context.user_data:
            old = context.user_data.pop('old_identity')
            await notify_admin_edit(uid, old, users[key], context)
            update_user_name_everywhere(uid)
        return S_MAIN
    elif text == "خوابگاهی":
        users[key]['is_dorm'] = True
        await update.message.reply_text("لطفا خوابگاه خود را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup([[d] for d in DORMS] + [["🔙 بازگشت"]], resize_keyboard=True))
        persist_all()
        return S_REGISTER_OTHER_DORM
    else:
        await update.message.reply_text("لطفا یکی از گزینه‌ها را انتخاب کنید: تهرانی یا خوابگاهی", reply_markup=back_kb())
        return S_REGISTER_DORM

async def register_other_dorm_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    key = str(uid)
    if text == "🔙 بازگشت":
        await update.message.reply_text("بازگشت", reply_markup=user_main_keyboard(True))
        return S_MAIN
    if text == "سایر خوابگاه ها":
        await update.message.reply_text("لطفا نام خوابگاه خود را تایپ کنید:", reply_markup=back_kb())
        return S_REGISTER_OTHER_DORM
    users[key]['dorm_name'] = text
    await update.message.reply_text("اطلاعات هویتی تکمیل شد ✅️", reply_markup=user_main_keyboard(True))
    msg = f"کاربری ثبت نام کرد: {make_disp_name(users[key])} — آیدی: {uid}"
    await context.bot.send_message(chat_id=ADMIN_ID, text=msg)
    persist_all()
    if 'old_identity' in context.user_data:
        old = context.user_data.pop('old_identity')
        await notify_admin_edit(uid, old, users[key], context)
        update_user_name_everywhere(uid)
    return S_MAIN

async def notify_admin_edit(uid: int, old: dict, new: dict, context: ContextTypes.DEFAULT_TYPE):
    old_name = f"{old.get('first_name') or 'نامثبت'} {old.get('last_name') or ''}".strip()
    new_name = f"{new.get('first_name') or 'نامثبت'} {new.get('last_name') or ''}".strip()
    old_dorm = (old.get('dorm_name') or "تهرانی") if not old.get('is_dorm') else (old.get('dorm_name') or "نامثبت")
    new_dorm = (new.get('dorm_name') or "تهرانی") if not new.get('is_dorm') else (new.get('dorm_name') or "نامثبت")
    text = (
        f"✏️ کاربر با آیدی {uid}\n"
        f"اسم خود را از \"{old_name}\" ➝ \"{new_name}\" تغییر داد\n"
        f"خوابگاه خود را از \"{old_dorm}\" ➝ \"{new_dorm}\""
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=text)

# Buying flow
async def buy_select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    key = str(uid)
    if text == "🔙 بازگشت":
        await update.message.reply_text("بازگشت به منوی اصلی", reply_markup=user_main_keyboard(True))
        return S_MAIN
    if text.startswith("حذف:"):
        try:
            parts = text.split()
            idx = int(parts[1].replace('.', '')) - 1
            if 0 <= idx < len(users[key]['cart']):
                removed = users[key]['cart'].pop(idx)
                persist_all()
                await update.message.reply_text(f"آیتم {removed['title']} حذف شد.", reply_markup=user_main_keyboard(True))
                return S_MAIN
        except Exception:
            await update.message.reply_text("خطا در حذف.")
            return S_MAIN

    pid, p = find_product_by_title(text)
    if not pid:
        await update.message.reply_text("جزوه‌ای با این نام یافت نشد.")
        return S_MAIN

    # show options without price in button text to make matching robust; show price in prompt
    price_info = f"قیمت رنگی: {p.get('color_price','-')} — سیاه و سفید: {p.get('bw_price','-')}"
    kb = ReplyKeyboardMarkup([[f"🎨 رنگی", f"⬛ سیاه سفید"], ["🔙 بازگشت"]], resize_keyboard=True)
    context.user_data['selected_product'] = pid
    await update.message.reply_text(f"({price_info})\nلطفا نوع چاپ را انتخاب کنید:", reply_markup=kb)
    return S_BUY_SELECT_TYPE

async def buy_select_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    key = str(uid)
    if text == "🔙 بازگشت":
        await update.message.reply_text("بازگشت", reply_markup=user_main_keyboard(True))
        return S_MAIN
    pid = context.user_data.get('selected_product')
    if not pid:
        await update.message.reply_text("ابتدا جزوه را انتخاب کنید.")
        return S_MAIN
    p = products.get(pid, {})
    # robust matching: check if 'رنگ' in text or 'سیاه' in text
    if "رنگ" in text:
        context.user_data['buy_type'] = 'رنگی'
        context.user_data['unit_price'] = int(p.get('color_price', 0) or 0)
    elif "سیاه" in text:
        context.user_data['buy_type'] = 'سیاه و سفید'
        context.user_data['unit_price'] = int(p.get('bw_price', 0) or 0)
    else:
        await update.message.reply_text("لطفا رنگی یا سیاه‌وسفید را انتخاب کنید.")
        return S_BUY_SELECT_TYPE
    await update.message.reply_text("لطفا تعداد را وارد کنید (عدد صحیح):", reply_markup=back_kb())
    return S_BUY_ENTER_QTY

async def buy_enter_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    key = str(uid)
    if text == "🔙 بازگشت":
        await update.message.reply_text("بازگشت", reply_markup=user_main_keyboard(True))
        return S_MAIN
    try:
        qty = int(text)
        if qty <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text("لطفا یک عدد صحیح بزرگتر از صفر وارد کنید.")
        return S_BUY_ENTER_QTY
    pid = context.user_data.get('selected_product')
    if not pid:
        await update.message.reply_text("ابتدا جزوه را انتخاب کنید.")
        return S_MAIN
    p = products.get(pid, {})
    it = {
        'product_id': pid,
        'title': p.get('title'),
        'type': context.user_data.get('buy_type', 'نامشخص'),
        'qty': qty,
        'unit_price': int(context.user_data.get('unit_price', 0)),
    }
    ensure_user(uid)
    users[str(uid)]['cart'].append(it)
    persist_all()
    await update.message.reply_text("ثبت شد ✅", reply_markup=user_main_keyboard(True))
    return S_MAIN

# Handle receipt photo upload (or forwarding photo messages to admin when not paying)
import os

async def handle_photo_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)

    order_id = context.user_data.get('pay_order_id')
    if not order_id:
        return S_MAIN

    file_id = update.message.photo[-1].file_id
    pay_id = str(uuid.uuid4())

    user_orders = orders.get(str(uid), [])
    sel_order = next((o for o in user_orders if o.get("order_id") == order_id), None)

    if not sel_order:
        await update.message.reply_text(
            "سفارش یافت نشد یا قبلاً پردازش شده است.",
            reply_markup=user_main_keyboard(True)
        )
        context.user_data.pop('pay_order_id', None)
        return S_MAIN

    pending_payments[pay_id] = {
        "payment_id": pay_id,
        "user_id": uid,
        "first_name": users[str(uid)].get("first_name"),
        "last_name": users[str(uid)].get("last_name"),
        "is_dorm": users[str(uid)].get("is_dorm"),
        "dorm_name": users[str(uid)].get("dorm_name"),
        "order_id": order_id,
        "items": sel_order.get("items", []),
        "total": sel_order.get("total", 0),
        "file_id": file_id,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "status": "pending",
    }

    persist_all()

    caption = (
        f"📌 فیش پرداختی از {make_disp_name(users[str(uid)])}\n"
        f"آیدی: {uid}\n"
        f"جمع: {sel_order.get('total', 0)} تومان\n"
        f"payment_id: {pay_id}"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید", callback_data=f"pay_approve:{pay_id}"),
            InlineKeyboardButton("❌ عدم تایید", callback_data=f"pay_reject:{pay_id}")
        ],
        [InlineKeyboardButton("↩️ پاسخ دادن", callback_data=f"reply_user:{uid}")]
    ])

    # گرفتن آیدی گروه از ENV
    PHOTO_GROUP_ID = os.getenv("PHOTO_GROUP_ID")

    sent = False

    if PHOTO_GROUP_ID:
        try:
            await context.bot.send_photo(
                chat_id=int(PHOTO_GROUP_ID),
                photo=file_id,
                caption=caption,
                reply_markup=kb
            )
            sent = True
        except Exception as e:
            print(f"⚠️ ارسال به گروه ناموفق بود: {e}")

    # fallback اگر گروه ست نبود یا ارسال شکست خورد
    if not sent:
        all_admins = [ADMIN_ID] + admins
        for admin_id in all_admins:
            try:
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=file_id,
                    caption=caption,
                    reply_markup=kb
                )
            except Exception as e:
                print(f"⚠️ ارسال فیش به ادمین {admin_id} ناموفق بود: {e}")

    await update.message.reply_text(
        "✅ فیش شما ارسال شد و در انتظار تایید می‌باشد.",
        reply_markup=user_main_keyboard(True)
    )

    context.user_data.pop('pay_order_id', None)
    return S_MAIN


# Generic text/photo forward from user to admin (chat)
async def user_message_forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This handler is a fallback that forwards messages when user is in chat mode.
    # However, main handler already forwards messages when chat_with_admin flag is set.
    return

# ---------------- Admin handlers ----------------
async def handle_admin_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # If admin is in reply mode (context.user_data['reply_to']), any text here should be sent to that user
    if 'reply_to' in context.user_data:
        target = context.user_data.pop('reply_to')
        # send message as admin_to_user
        await context.bot.send_message(chat_id=target, text=f"[پاسخ ادمین]:\n{text}")
        await update.message.reply_text("پیام به کاربر ارسال شد.", reply_markup=admin_main_keyboard())
        return S_MAIN

    # Also, if admin previously chose inspect_product, handle color selection
    inspect = context.user_data.get('inspect_product')
    if inspect and text in ("🎨 رنگی", "⬛ سیاه سفید", "رنگی", "سیاه و سفید"):
        pid = inspect.get('pid')
        source = inspect.get('source')
        typ = 'رنگی' if "رنگ" in text else 'سیاه و سفید'

        user_qty = {}

        if source == 'purchased':
            for uid_k, pur_list in purchases.items():
                for pur in pur_list:
                    for it in pur.get('items', []):
                        if it.get('product_id') == pid and it.get('type') == typ:
                            user_qty[str(uid_k)] = user_qty.get(str(uid_k), 0) + it.get('qty', 0)
        elif source == 'finalized':
            for uid_k, order_list in orders.items():
                for ord_entry in order_list:
                    for it in ord_entry.get('items', []):
                        if it.get('product_id') == pid and it.get('type') == typ:
                            user_qty[str(uid_k)] = user_qty.get(str(uid_k), 0) + it.get('qty', 0)

        context.user_data.pop('inspect_product', None)
        if not user_qty:
            await update.message.reply_text("هیچ رکوردی یافت نشد.", reply_markup=admin_main_keyboard())
            return S_MAIN
        lines = []
        for uid_k, qty in user_qty.items():
            name = make_disp_name(users.get(str(uid_k), {}))
            lines.append(f"{name} — {qty} عدد")
        await update.message.reply_text("\n".join(lines), reply_markup=admin_main_keyboard())
        return S_MAIN
        lines = []
        for uid_k, qty in user_qty.items():
            name = make_disp_name(users.get(str(uid_k), {}))
            lines.append(f"{name} — {qty} عدد")
        await update.message.reply_text("\n".join(lines), reply_markup=admin_main_keyboard())
        return S_MAIN

    # Admin main menu options
    if text == "🔙 بازگشت":
        await update.message.reply_text("منوی ادمین", reply_markup=admin_main_keyboard())
        return S_MAIN

    if text == "➕ اضافه کردن جزوه":
        await update.message.reply_text("لطفا نام جزوه را وارد کنید:", reply_markup=back_kb())
        return S_ADMIN_ADD_NAME

    if text == "📚 لیست جزوات":
        if not products:
            await update.message.reply_text("هیچ جزوه‌ای ثبت نشده است.", reply_markup=admin_main_keyboard())
            return S_MAIN
        lines = []
        for p in products.values():
            lines.append(f"📘 {p['title']}\n🎨 رنگی: {p.get('color_price','-')} تومان — ⬛ سیاه و سفید: {p.get('bw_price','-')} تومان\n")
        kb = [[p['title']] for p in products.values()]
        kb.append(["🗑 حذف جزوه"])
        kb.append(["🔙 بازگشت"])
        await update.message.reply_text("\n".join(lines), reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return S_ADMIN_LIST

    if text == "👥 اسامی ثبت نام نهایی کنندگان":
        names = []
        for uid_k, u in users.items():
            if orders.get(uid_k):
                names.append((uid_k, make_disp_name(u)))
        if not names:
            await update.message.reply_text("فعلا کسی ثبت نهایی نکرده است.", reply_markup=admin_main_keyboard())
            return S_MAIN
        # provide top "delete list" button + per-user buttons
        kb = [["🗑 حذف لیست"]]
        kb += [[f"{n[1]} — id:{n[0]}"] for n in names]
        kb.append(["🔙 بازگشت"])
        await update.message.reply_text("اسامی ثبت نهایی‌کنندگان:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        context.user_data['reg_names_map'] = {f"{n[1]} — id:{n[0]}": n[0] for n in names}
        context.user_data.pop('buyers_map', None)
        return S_MAIN

    if text == "👤 اسامی خریداران":
        names = []
        for uid_k, p_list in purchases.items():
            if p_list:
                u = users.get(uid_k, {})
                names.append((uid_k, make_disp_name(u)))
        if not names:
            await update.message.reply_text("فعلا خریدار تایید شده‌ای وجود ندارد.", reply_markup=admin_main_keyboard())
            return S_MAIN
        kb = [["🗑 حذف لیست"]]
        kb += [[f"{n[1]} — id:{n[0]}"] for n in names]
        kb.append(["🔙 بازگشت"])
        await update.message.reply_text("اسامی خریداران تاییدشده:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        context.user_data['buyers_map'] = {f"{n[1]} — id:{n[0]}": n[0] for n in names}
        context.user_data.pop('reg_names_map', None)
        return S_MAIN

    if text == "📚 جزوات خریداری شده":
        # aggregate purchases with color/bw counts
        agg = {}
        for uid_k, p_list in purchases.items():
            for pur in p_list:
                for it in pur.get("items", []):
                    title = it['title']
                    typ = it['type']
                    if title not in agg:
                        agg[title] = {"رنگی": 0, "سیاه و سفید": 0}
                    agg[title][typ] = agg[title].get(typ, 0) + it.get('qty', 0)
        if not agg:
            await update.message.reply_text("فعلا جزوه خریداری شده‌ای وجود ندارد.", reply_markup=admin_main_keyboard())
            return S_MAIN
        kb = [[title] for title in agg.keys()]
        kb.append(["🔙 بازگشت"])
        context.user_data['purchased_agg'] = agg
        context.user_data.pop('finalized_agg', None)
        lines = [f"{t} : رنگی {v['رنگی']} - سیاه و سفید {v['سیاه و سفید']}" for t,v in agg.items()]
        await update.message.reply_text("\n".join(lines), reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return S_MAIN

    if text == "📄 جزوات ثبت نهایی شده":
        agg = {}
        for uid_k, order_list in orders.items():
            for ord_entry in order_list:
                for it in ord_entry.get("items", []):
                    title = it['title']
                    typ = it['type']
                    if title not in agg:
                        agg[title] = {"رنگی": 0, "سیاه و سفید": 0}
                    agg[title][typ] = agg[title].get(typ, 0) + it.get('qty', 0)
        if not agg:
            await update.message.reply_text("فعلا جزوه‌ای در حالت ثبت نهایی وجود ندارد.", reply_markup=admin_main_keyboard())
            return S_MAIN
        kb = [[title] for title in agg.keys()]
        kb.append(["🔙 بازگشت"])
        context.user_data['finalized_agg'] = agg
        context.user_data.pop('purchased_agg', None)
        lines = [f"{t} : رنگی {v['رنگی']} - سیاه و سفید {v['سیاه و سفید']}" for t,v in agg.items()]
        await update.message.reply_text("\n".join(lines), reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return S_MAIN

    if text == "🕓 فیش‌های در انتظار تایید":
        if not pending_payments:
            await update.message.reply_text("فعلا فیشی در انتظار تایید نیست.", reply_markup=admin_main_keyboard())
            return S_MAIN

    # ✅ ارسال برای تمام ادمین‌ها (اصلی + فرعی)
        all_admins = [ADMIN_ID] + admins

        for pay_id, pay in pending_payments.items():
            if pay.get("status") != "pending":
                continue
            caption = f"📌 فیش از {make_disp_name({'first_name': pay.get('first_name'), 'last_name': pay.get('last_name'), 'is_dorm': pay.get('is_dorm'), 'dorm_name': pay.get('dorm_name')})}\nآیدی: {pay.get('user_id')}\nجمع: {pay.get('total')} تومان\npayment_id: {pay_id}"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ تایید", callback_data=f"pay_approve:{pay_id}"),
                 InlineKeyboardButton("❌ عدم تایید", callback_data=f"pay_reject:{pay_id}")],
                [InlineKeyboardButton("↩️ پاسخ دادن", callback_data=f"reply_user:{pay.get('user_id')}")]
            ])
            # ارسال فیش برای همه ادمین‌ها
            for admin_id in all_admins:
                try:
                    await context.bot.send_photo(chat_id=admin_id, photo=pay.get('file_id'), caption=caption, reply_markup=kb)
                except Exception as e:
                    print(f"⚠️ ارسال فیش به ادمین {admin_id} ناموفق بود: {e}")

        await update.message.reply_text("📨 تمام فیش‌های در انتظار برای همه ادمین‌ها ارسال شدند.", reply_markup=admin_main_keyboard())
        return S_MAIN


    if text == "📊 دریافت فایل اکسل خرید جزوات":
        all_products = list(products.values())
        rows = []
        for uid_k, u in users.items():
            disp_name = make_disp_name(u)
            row = {"نام": disp_name}
            for p in all_products:
                found_items = []
                for pur in purchases.get(str(uid_k), []):
                    for it in pur.get('items', []):
                        if it.get('title') == p['title']:
                            found_items.append(f"{it['type']} × {it['qty']}")
                row[p['title']] = " / ".join(found_items) if found_items else 0
            rows.append(row)

        # مرتب‌سازی: اول خوابگاهی‌ها، بعد تهرانی‌ها
        def sort_key(r):
            if "تهران" in r['نام'] or "تهرانی" in r['نام']:
                return (1, r['نام'])
            return (0, r['نام'])

        rows_sorted = sorted(rows, key=sort_key)

        import pandas as pd
        df = pd.DataFrame(rows_sorted)
        path = DATA_DIR / "purchases.xlsx"
        df.to_excel(path, index=False)

    # ✅ ارسال فایل برای همه ادمین‌ها
        all_admins = [ADMIN_ID] + admins
        for admin_id in all_admins:
            try:
                await context.bot.send_document(chat_id=admin_id, document=path.open('rb'))
            except Exception as e:
                print(f"⚠️ ارسال فایل اکسل به ادمین {admin_id} ناموفق بود: {e}")

        await update.message.reply_text("📊 فایل اکسل خرید جزوات برای تمام ادمین‌ها ارسال شد.", reply_markup=admin_main_keyboard())
        return S_MAIN


    if text == "⛔ مسدود کردن کاربر":
        await update.message.reply_text("لطفا آیدی عددی کاربر را ارسال کنید:", reply_markup=back_kb())
        return S_ADMIN_BLOCK_ID

    if text == "✅ رفع مسدودیت":
        await update.message.reply_text("لطفا آیدی عددی کاربر را ارسال کنید:", reply_markup=back_kb())
        return S_ADMIN_UNBLOCK_ID

    # clicked on aggregated product in purchased_agg or finalized_agg
    if 'purchased_agg' in context.user_data and text in context.user_data['purchased_agg']:
        # find product id by title
        pid, p = find_product_by_title(text)
        if not pid:
            await update.message.reply_text("جزوه یافت نشد.", reply_markup=admin_main_keyboard())
            return S_MAIN
        context.user_data['inspect_product'] = {'pid': pid, 'source': 'purchased'}
        kb = ReplyKeyboardMarkup([[f"🎨 رنگی", f"⬛ سیاه سفید"], ["🔙 بازگشت"]], resize_keyboard=True)
        await update.message.reply_text("نوع را انتخاب کنید:", reply_markup=kb)
        return S_MAIN

    if 'finalized_agg' in context.user_data and text in context.user_data['finalized_agg']:
        pid, p = find_product_by_title(text)
        if not pid:
            await update.message.reply_text("جزوه یافت نشد.", reply_markup=admin_main_keyboard())
            return S_MAIN
        context.user_data['inspect_product'] = {'pid': pid, 'source': 'finalized'}
        kb = ReplyKeyboardMarkup([[f"🎨 رنگی", f"⬛ سیاه سفید"], ["🔙 بازگشت"]], resize_keyboard=True)
        await update.message.reply_text("نوع را انتخاب کنید:", reply_markup=kb)
        return S_MAIN

    # clicked on a name under reg_names_map -> show finalized orders and allow delete all
    if 'reg_names_map' in context.user_data and text in context.user_data['reg_names_map']:
        the_uid = context.user_data['reg_names_map'][text]
        ords = orders.get(str(the_uid), [])
        if not ords:
            await update.message.reply_text("این کاربر ثبت نهایی‌ای ندارد.", reply_markup=admin_main_keyboard())
            return S_MAIN
        lines = []
        total_sum = 0
        for i, ord_entry in enumerate(ords, 1):
            items_lines = "\n".join([f"- {it['title']} ({it['type']}) x {it['qty']}" for it in ord_entry.get('items', [])])
            lines.append(f"سفارش {i} — جمع: {ord_entry.get('total',0)}\n{items_lines}")
            total_sum += ord_entry.get('total',0)
        kb = [[KeyboardButton("🗑 حذف همه جزوات کاربر")], [KeyboardButton("💬 چت با کاربر")], [KeyboardButton("🔙 بازگشت")]]
        context.user_data['selected_reg_user'] = the_uid
        await update.message.reply_text(f"جزوات نهایی {make_disp_name(users[str(the_uid)])}:\n\n" + "\n\n".join(lines) + f"\n\nجمع کل: {total_sum}", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return S_MAIN

    # clicked on buyer
    if 'buyers_map' in context.user_data and text in context.user_data['buyers_map']:
        the_uid = context.user_data['buyers_map'][text]
        pur_list = purchases.get(str(the_uid), [])
        if not pur_list:
            await update.message.reply_text("این کاربر خرید تاییدشده‌ای ندارد.", reply_markup=admin_main_keyboard())
            return S_MAIN
        lines = []
        total_sum = 0
        for i, pch in enumerate(pur_list,1):
            items_lines = "\n".join([f"- {it['title']} ({it['type']}) x {it['qty']}" for it in pch.get('items', [])])
            lines.append(f"خرید {i} — جمع: {pch.get('total')} تومان\n{items_lines}")
            total_sum += pch.get('total', 0)
        context.user_data['selected_buyer'] = the_uid
        kb = [
            [KeyboardButton("🗑 حذف همه خریدهای کاربر")],
            [KeyboardButton("💬 چت با کاربر")],
            [KeyboardButton("🔙 بازگشت")]
        ]
        await update.message.reply_text(
            f"خریدهای {make_disp_name(users.get(str(the_uid), {}))}:\n\n" +
            "\n\n".join(lines) +
            f"\n\nجمع کل: {total_sum}",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return S_MAIN

    # Handle admin "💬 چت با کاربر" from selected context
    if text == "💬 چت با کاربر":
        the_uid = context.user_data.get('selected_reg_user') or context.user_data.get('selected_buyer')
        if not the_uid:
            await update.message.reply_text("هیچ کاربری انتخاب نشده است.", reply_markup=admin_main_keyboard())
            return S_MAIN
        context.user_data['reply_to'] = int(the_uid)
        await update.message.reply_text(f"حالا پیام خود را تایپ کنید تا برای {make_disp_name(users.get(str(the_uid), {}))} ارسال شود.")
        return S_MAIN

    # delete all finalized for selected reg user
    if text == "🗑 حذف همه جزوات کاربر":
        the_uid = context.user_data.get('selected_reg_user')
        if not the_uid:
            await update.message.reply_text("هیچ کاربری انتخاب نشده.", reply_markup=admin_main_keyboard())
            return S_MAIN
        # ask for confirmation via inline buttons
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("بله حذف کن", callback_data=f"delete_reg_user:{the_uid}"), InlineKeyboardButton("لغو", callback_data="delete_reg_user:cancel")]
        ])
        await update.message.reply_text("آیا مطمئن هستید تمام جزوات نهایی این کاربر حذف شود؟", reply_markup=kb)
        return S_MAIN

    # delete all purchases for selected buyer (confirmation flow)
    if text == "🗑 حذف همه خریدهای کاربر":
        the_uid = context.user_data.get('selected_buyer')
        if not the_uid:
            await update.message.reply_text("هیچ کاربری انتخاب نشده.", reply_markup=admin_main_keyboard())
            return S_MAIN
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("بله حذف کن", callback_data=f"delete_buyer:{the_uid}"), InlineKeyboardButton("لغو", callback_data="delete_buyer:cancel")]
        ])
        await update.message.reply_text("آیا مطمئن هستید تمام خریدهای این کاربر حذف شود؟", reply_markup=kb)
        return S_MAIN

    # top-level delete-list actions (for buyers and reg_names)
    if text == "🗑 حذف لیست":
        # admin asked to delete current map list (buyers_map or reg_names_map)
        if 'buyers_map' in context.user_data:
            context.user_data['confirm_delete_list'] = 'buyers'
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("بله حذف کن", callback_data="confirm_delete_list:buyers"), InlineKeyboardButton("خیر", callback_data="confirm_delete_list:cancel")]])
            await update.message.reply_text("آیا مطمئن هستید تمام اسامی خریداران و جزواتشان حذف شود؟", reply_markup=kb)
            return S_MAIN
        if 'reg_names_map' in context.user_data:
            context.user_data['confirm_delete_list'] = 'reg_names'
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("بله حذف کن", callback_data="confirm_delete_list:reg_names"), InlineKeyboardButton("خیر", callback_data="confirm_delete_list:cancel")]])
            await update.message.reply_text("آیا مطمئن هستید تمام اسامی ثبت نهایی کنندگان و جزواتشان حذف شود؟", reply_markup=kb)
            return S_MAIN
        await update.message.reply_text("هیچ لیستی قابل حذف وجود ندارد.", reply_markup=admin_main_keyboard())
        return S_MAIN

    # delete user from buyers list (without confirmation; kept for backward compat)
    if text == "🗑 حذف کاربر از خریداران":
        the_uid = context.user_data.get('selected_buyer')
        if not the_uid:
            await update.message.reply_text("هیچ کاربری برای حذف انتخاب نشده.", reply_markup=admin_main_keyboard())
            return S_MAIN
        # remove purchases and entry
        purchases.pop(str(the_uid), None)
        persist_all()
        await update.message.reply_text("کاربر و خریدهایش حذف شد.", reply_markup=admin_main_keyboard())
        return S_MAIN

    # --- Backup system ---
    if text == "📤 دریافت بکاپ":
        # ایجاد فایل ZIP از دیتای موجود
        import zipfile, io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in [USERS_FILE, PRODUCTS_FILE, ORDERS_FILE, PENDING_PAYMENTS_FILE, PURCHASES_FILE, BLOCKED_FILE]:
                if f.exists():
                    z.write(f, arcname=f.name)
        buf.seek(0)
        await context.bot.send_document(chat_id=ADMIN_ID, document=buf, filename="backup.zip")
        await update.message.reply_text("📤 فایل بکاپ ارسال شد.", reply_markup=admin_main_keyboard())
        return S_MAIN

    if text == "📥 وارد کردن بکاپ":
        context.user_data['awaiting_backup_file'] = True
        await update.message.reply_text("لطفا فایل بکاپ (backup.zip) را ارسال کنید یا 🔙 بازگشت را بزنید.", reply_markup=back_kb())
        return S_MAIN


    # --- 🔽 بخش جدید: مدیریت ادمین‌ها ---
    if text == "⚙️ مدیریت ادمین‌ها":
        if update.effective_user.id != ADMIN_ID and update.effective_user.id not in admins:
            await update.message.reply_text("❌ فقط ادمین اصلی به این بخش دسترسی دارد.")
            return S_MAIN

        kb = [
            [KeyboardButton("➕ اضافه کردن ادمین جدید")],
            [KeyboardButton("➖ حذف ادمین‌های موجود")],
            [KeyboardButton("🔙 بازگشت")],
        ]
        await update.message.reply_text(
            "⚙️ بخش مدیریت ادمین‌ها:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        )
        return "S_MANAGE_ADMINS"
    # --- 🔼 پایان کد جدید ---



    

    await update.message.reply_text("دستور نامعتبر.", reply_markup=admin_main_keyboard())
    return S_MAIN


# Admin add product flows
async def admin_add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 بازگشت":
        await update.message.reply_text("بازگشت", reply_markup=admin_main_keyboard())
        return S_MAIN
    pid = next_product_id()
    products[pid] = {"title": text, "color_price": 0, "bw_price": 0}
    context.user_data['new_product_id'] = pid
    kb = ReplyKeyboardMarkup([["🎨 رنگی", "⬛ سیاه سفید"], ["✅ ثبت جزوه"], ["🔙 بازگشت"]], resize_keyboard=True)
    await update.message.reply_text("برای اضافه کردن قیمت، یکی از گزینه‌ها را انتخاب کنید یا ثبت جزوه را بزنید:", reply_markup=kb)
    persist_all()
    return S_ADMIN_ADD_CHOOSE

async def admin_add_product_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    pid = context.user_data.get('new_product_id')
    if not pid:
        await update.message.reply_text("ابتدا نام جزوه را وارد کنید.")
        return S_MAIN
    if text == "🎨 رنگی":
        await update.message.reply_text("قیمت رنگی را وارد کنید (عدد):", reply_markup=back_kb())
        return S_ADMIN_ADD_COLOR_PRICE
    if text == "⬛ سیاه سفید":
        await update.message.reply_text("قیمت سیاه سفید را وارد کنید (عدد):", reply_markup=back_kb())
        return S_ADMIN_ADD_BW_PRICE
    if text == "✅ ثبت جزوه":
        prod = products.get(pid)
        if not prod:
            await update.message.reply_text("خطا: جزوه یافت نشد.")
            return S_MAIN
        persist_all()
        await update.message.reply_text(f"جزوه '{prod['title']}' ثبت شد.", reply_markup=admin_main_keyboard())
        return S_MAIN
    if text == "🔙 بازگشت":
        await update.message.reply_text("بازگشت", reply_markup=admin_main_keyboard())
        return S_MAIN
    await update.message.reply_text("گزینه نامعتبر")
    return S_ADMIN_ADD_CHOOSE

async def admin_add_color_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 بازگشت":
        await update.message.reply_text("بازگشت", reply_markup=admin_main_keyboard())
        return S_MAIN
    pid = context.user_data.get('new_product_id')
    try:
        val = int(text)
    except Exception:
        await update.message.reply_text("لطفا عدد صحیح وارد کنید.")
        return S_ADMIN_ADD_COLOR_PRICE
    products[pid]['color_price'] = val
    persist_all()
    await update.message.reply_text("قیمت رنگی ثبت شد.", reply_markup=ReplyKeyboardMarkup([["⬛ سیاه سفید"], ["✅ ثبت جزوه"], ["🔙 بازگشت"]], resize_keyboard=True))
    return S_ADMIN_ADD_CHOOSE

async def admin_add_bw_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 بازگشت":
        await update.message.reply_text("بازگشت", reply_markup=admin_main_keyboard())
        return S_MAIN
    pid = context.user_data.get('new_product_id')
    try:
        val = int(text)
    except Exception:
        await update.message.reply_text("لطفا عدد صحیح وارد کنید.")
        return S_ADMIN_ADD_BW_PRICE
    products[pid]['bw_price'] = val
    persist_all()
    await update.message.reply_text("قیمت سیاه و سفید ثبت شد.", reply_markup=ReplyKeyboardMarkup([["🎨 رنگی"], ["✅ ثبت جزوه"], ["🔙 بازگشت"]], resize_keyboard=True))
    return S_ADMIN_ADD_CHOOSE

# Admin list and delete product
async def admin_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 بازگشت":
        await update.message.reply_text("منوی ادمین", reply_markup=admin_main_keyboard())
        return S_MAIN
    if text == "🗑 حذف جزوه":
        if not products:
            await update.message.reply_text("هیچ جزوه‌ای برای حذف وجود ندارد.")
            return S_MAIN
        kb = [[p['title']] for p in products.values()]
        kb.append(["🔙 بازگشت"])
        await update.message.reply_text("جزوه‌ای که می‌خواهید حذف کنید را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return S_ADMIN_DELETE_SELECT

    pid, p = find_product_by_title(text)
    if pid:
        total_color = 0
        total_bw = 0
        detail_lines = []
        for uid_k, user_orders in orders.items():
            for ord_entry in user_orders:
                for it in ord_entry.get('items', []):
                    if it.get('product_id') == pid:
                        if it.get('type') in ('رنگی', 'color', 'Color'):
                            total_color += it.get('qty', 0)
                        else:
                            total_bw += it.get('qty', 0)
                        detail_lines.append(f"{ord_entry.get('first_name','')} {ord_entry.get('last_name','')} — {it.get('qty')} — {it.get('type')}")
        lines = [f"جزوه: {p.get('title')}", f"تعداد رنگی نهایی شده: {total_color}", f"تعداد سیاه و سفید نهایی شده: {total_bw}"]
        if detail_lines:
            lines.append("\nجزئیات:")
            lines.extend(detail_lines)
        await update.message.reply_text("\n".join(lines), reply_markup=admin_main_keyboard())
        return S_MAIN

    await update.message.reply_text("گزینه نامعتبر.")
    return S_ADMIN_LIST

async def admin_delete_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 بازگشت":
        await update.message.reply_text("منوی ادمین", reply_markup=admin_main_keyboard())
        return S_MAIN
    pid, p = find_product_by_title(text)
    if not pid:
        await update.message.reply_text("جزوه‌ای با این نام یافت نشد.")
        return S_ADMIN_DELETE_SELECT
    del products[pid]
    # remove references from orders and purchases
    for uid_k in list(orders.keys()):
        new_orders = []
        for ord_entry in orders[uid_k]:
            new_items = [it for it in ord_entry.get('items', []) if it.get('product_id') != pid]
            if new_items:
                ord_entry['items'] = new_items
                ord_entry['total'] = sum(it['qty']*it['unit_price'] for it in new_items)
                new_orders.append(ord_entry)
        if new_orders:
            orders[uid_k] = new_orders
        else:
            orders.pop(uid_k, None)
    for uid_k in list(purchases.keys()):
        new_purs = []
        for pur in purchases[uid_k]:
            new_items = [it for it in pur.get('items', []) if it.get('product_id') != pid]
            if new_items:
                pur['items'] = new_items
                pur['total'] = sum(it['qty']*it['unit_price'] for it in new_items)
                new_purs.append(pur)
        if new_purs:
            purchases[uid_k] = new_purs
        else:
            purchases.pop(uid_k, None)
    persist_all()
    await update.message.reply_text(f"جزوه '{p.get('title')}' حذف شد و از سفارشات/خریدها نیز پاک شد.", reply_markup=admin_main_keyboard())
    return S_MAIN

# Admin block/unblock handlers
async def admin_block_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 بازگشت":
        await update.message.reply_text("بازگشت", reply_markup=admin_main_keyboard())
        return S_MAIN
    try:
        the_uid = int(text)
    except Exception:
        await update.message.reply_text("آیدی باید یک عدد باشد.")
        return S_ADMIN_BLOCK_ID
    if the_uid not in blocked:
        blocked.append(the_uid)
        persist_all()
    await update.message.reply_text(f"کاربر {the_uid} مسدود شد.", reply_markup=admin_main_keyboard())
    return S_MAIN

async def admin_unblock_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 بازگشت":
        await update.message.reply_text("بازگشت", reply_markup=admin_main_keyboard())
        return S_MAIN
    try:
        the_uid = int(text)
    except Exception:
        await update.message.reply_text("آیدی باید یک عدد باشد.")
        return S_ADMIN_UNBLOCK_ID
    if the_uid in blocked:
        blocked.remove(the_uid)
        persist_all()
    await update.message.reply_text(f"کاربر {the_uid} رفع مسدود شد.", reply_markup=admin_main_keyboard())
    return S_MAIN

# ---------------- CallbackQuery: approve/reject payments and reply-to-user and confirm delete-list and inspect buyers ----------------

async def handle_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_backup_file'):
        return
    if update.message.text == "🔙 بازگشت":
        context.user_data.pop('awaiting_backup_file', None)
        await update.message.reply_text("عملیات وارد کردن بکاپ لغو شد.", reply_markup=admin_main_keyboard())
        return S_MAIN
    if not update.message.document:
        await update.message.reply_text("لطفا فایل بکاپ را بفرستید.", reply_markup=back_kb())
        return S_MAIN
    import zipfile, io
    file = await update.message.document.get_file()
    buf = io.BytesIO()
    await file.download_to_memory(out=buf)
    buf.seek(0)
    with zipfile.ZipFile(buf, 'r') as z:
        for name in z.namelist():
            out_path = DATA_DIR / name
            with z.open(name) as src, open(out_path, 'wb') as dst:
                dst.write(src.read())
    # reload data
    global users, products, orders, pending_payments, purchases, blocked
    users = load_json(USERS_FILE, {})
    products = load_json(PRODUCTS_FILE, {})
    orders = load_json(ORDERS_FILE, {})
    pending_payments = load_json(PENDING_PAYMENTS_FILE, {})
    purchases = load_json(PURCHASES_FILE, {})
    blocked = load_json(BLOCKED_FILE, [])
    persist_all()
    context.user_data.pop('awaiting_backup_file', None)
    await update.message.reply_text("✅ بکاپ با موفقیت بازیابی شد.", reply_markup=admin_main_keyboard())
    return S_MAIN


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data.startswith("pay_approve:"):
        pay_id = data.split(":",1)[1]
        pay = pending_payments.get(pay_id)
        if not pay:
            try:
                await query.edit_message_caption(caption="این فیش دیگر موجود نیست یا قبلا پردازش شده.", reply_markup=None)
            except Exception:
                pass
            return
        uid = pay.get("user_id")
        # find and remove order
        user_orders = orders.get(str(uid), [])
        ord_to_remove = None
        for ord_entry in list(user_orders):
            if ord_entry.get("order_id") == pay.get("order_id"):
                ord_to_remove = ord_entry
                break
        if not ord_to_remove:
            try:
                await query.edit_message_caption(caption="سفارش مربوطه یافت نشد.", reply_markup=None)
            except Exception:
                pass
            return
        purchase = {
            "purchase_id": str(uuid.uuid4()),
            "user_id": uid,
            "first_name": users.get(str(uid), {}).get("first_name"),
            "last_name": users.get(str(uid), {}).get("last_name"),
            "items": ord_to_remove.get("items", []),
            "total": ord_to_remove.get("total",0),
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }
        purchases.setdefault(str(uid), []).append(purchase)
        # remove order
        orders[str(uid)].remove(ord_to_remove)
        # update payment
        pay['status'] = 'approved'
        pay['processed_by'] = update.effective_user.id
        pay['processed_at'] = datetime.datetime.utcnow().isoformat()
        persist_all()
        try:
            await query.edit_message_caption(caption=(query.message.caption or "") + "\n\n✅ این فیش تأیید شد.", reply_markup=None)
        except Exception:
            try:
                await query.edit_message_text(text="این فیش تأیید شد.", reply_markup=None)
            except Exception:
                pass
        await context.bot.send_message(chat_id=uid, text="پرداخت شما تایید شد ✅️")
        return

    if data.startswith("pay_reject:"):
        pay_id = data.split(":",1)[1]
        pay = pending_payments.get(pay_id)
        if not pay:
            try:
                await query.edit_message_caption(caption="این فیش دیگر موجود نیست یا قبلا پردازش شده.", reply_markup=None)
            except Exception:
                pass
            return
        pay['status'] = 'rejected'
        pay['processed_by'] = update.effective_user.id
        pay['processed_at'] = datetime.datetime.utcnow().isoformat()
        persist_all()
        try:
            await query.edit_message_caption(caption=(query.message.caption or "") + "\n\n❌ این فیش رد شد.", reply_markup=None)
        except Exception:
            try:
                await query.edit_message_text(text="این فیش رد شد.", reply_markup=None)
            except Exception:
                pass
        uid = pay.get("user_id")
        await context.bot.send_message(chat_id=uid, text="متاسفانه پرداخت شما توسط ادمین تایید نشد ❌")
        return

    if data.startswith("reply_user:"):
        target_uid = int(data.split(":",1)[1])
        context.user_data['reply_to'] = target_uid
        await query.message.reply_text(f"حالا پیام خود را تایپ کنید تا برای {make_disp_name(users.get(str(target_uid),{}))} ارسال شود.")
        return

    if data.startswith("confirm_delete_list:"):
        action = data.split(":",1)[1]
        if action == "buyers":
            # delete purchases for all
            purchases.clear()
            persist_all()
            try:
                await query.edit_message_text("همهٔ اسامی خریداران و خریدهایشان حذف شد.", reply_markup=None)
            except Exception:
                try:
                    await query.message.reply_text("همهٔ اسامی خریداران و خریدهایشان حذف شد.", reply_markup=admin_main_keyboard())
                except Exception:
                    pass
            context.user_data.pop('buyers_map', None)
            context.user_data.pop('confirm_delete_list', None)
            return
        if action == "reg_names":
            # delete all orders (finalized) for everyone
            orders.clear()
            persist_all()
            try:
                await query.edit_message_text("همهٔ اسامی ثبت نهایی کنندگان و سفارشاتشان حذف شد.", reply_markup=None)
            except Exception:
                try:
                    await query.message.reply_text("همهٔ اسامی ثبت نهایی کنندگان و سفارشاتشان حذف شد.", reply_markup=admin_main_keyboard())
                except Exception:
                    pass
            context.user_data.pop('reg_names_map', None)
            context.user_data.pop('confirm_delete_list', None)
            return
        # cancel
        try:
            await query.edit_message_text("عملیات حذف لغو شد.", reply_markup=None)
        except Exception:
            try:
                await query.message.reply_text("عملیات حذف لغو شد.", reply_markup=admin_main_keyboard())
            except Exception:
                pass
        context.user_data.pop('confirm_delete_list', None)
        return

    # delete all purchases for a specific buyer (confirmation)
    if data.startswith("delete_buyer:"):
        action = data.split(":",1)[1]
        if action == "cancel":
            try:
                await query.edit_message_text("عملیات حذف لغو شد.", reply_markup=None)
            except Exception:
                try:
                    await query.message.reply_text("عملیات حذف لغو شد.", reply_markup=admin_main_keyboard())
                except Exception:
                    pass
            return
        the_uid = action
        purchases.pop(str(the_uid), None)
        persist_all()
        try:
            await query.edit_message_text("تمام خریدهای این کاربر حذف شد.", reply_markup=None)
        except Exception:
            try:
                await query.message.reply_text("تمام خریدهای این کاربر حذف شد.", reply_markup=admin_main_keyboard())
            except Exception:
                pass
        context.user_data.pop('selected_buyer', None)
        return

    # delete all finalized orders for a specific user (confirmation)
    if data.startswith("delete_reg_user:"):
        action = data.split(":",1)[1]
        if action == "cancel":
            try:
                await query.edit_message_text("عملیات حذف لغو شد.", reply_markup=None)
            except Exception:
                try:
                    await query.message.reply_text("عملیات حذف لغو شد.", reply_markup=admin_main_keyboard())
                except Exception:
                    pass
            return
        the_uid = action
        orders.pop(str(the_uid), None)
        persist_all()
        try:
            await query.edit_message_text("تمام جزوات نهایی این کاربر حذف شد.", reply_markup=None)
        except Exception:
            try:
                await query.message.reply_text("تمام جزوات نهایی این کاربر حذف شد.", reply_markup=admin_main_keyboard())
            except Exception:
                pass
        context.user_data.pop('selected_reg_user', None)
        return

# admin reply text/photo handled in admin message handler (we added reply_to state)

# --- 🔽 توابع جدید برای مدیریت ادمین‌ها ---
async def handle_manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🔙 بازگشت":
        await update.message.reply_text("بازگشت به منوی اصلی ادمین.", reply_markup=admin_main_keyboard())
        return S_MAIN

    if text == "➕ اضافه کردن ادمین جدید":
        await update.message.reply_text("لطفاً آیدی عددی کاربر را بفرستید:", reply_markup=back_kb())
        return "S_ADD_ADMIN"

    if text == "➖ حذف ادمین‌های موجود":
        if not admins:
            await update.message.reply_text("هیچ ادمینی وجود ندارد.", reply_markup=back_kb())
            return "S_MANAGE_ADMINS"

        kb = [[KeyboardButton(str(a))] for a in admins]
        kb.append([KeyboardButton("🔙 بازگشت")])
        await update.message.reply_text(
            "ادمین مورد نظر برای حذف را انتخاب کنید:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        )
        return "S_REMOVE_ADMIN"


async def handle_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 بازگشت":
        await update.message.reply_text("عملیات لغو شد.", reply_markup=admin_main_keyboard())
        return S_MAIN

    try:
        new_admin = int(text)
    except ValueError:
        await update.message.reply_text("❌ آیدی نامعتبر است.", reply_markup=back_kb())
        return "S_ADD_ADMIN"

    if new_admin in admins:
        await update.message.reply_text("⚠️ این کاربر از قبل ادمین است.", reply_markup=admin_main_keyboard())
        return S_MAIN

    if str(new_admin) in users:
        del users[str(new_admin)]

    admins.append(new_admin)
    persist_all()
    await update.message.reply_text(f"✅ کاربر {new_admin} به عنوان ادمین اضافه شد.", reply_markup=admin_main_keyboard())
    return S_MAIN


async def handle_remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 بازگشت":
        await update.message.reply_text("عملیات لغو شد.", reply_markup=admin_main_keyboard())
        return S_MAIN

    try:
        admin_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ مقدار وارد شده معتبر نیست.", reply_markup=back_kb())
        return "S_REMOVE_ADMIN"

    if admin_id not in admins:
        await update.message.reply_text("⚠️ چنین ادمینی وجود ندارد.", reply_markup=admin_main_keyboard())
        return S_MAIN

    admins.remove(admin_id)
    persist_all()
    await update.message.reply_text(f"🚫 ادمین {admin_id} حذف شد و به کاربر عادی تبدیل گردید.", reply_markup=admin_main_keyboard())
    return S_MAIN
# --- 🔼 پایان کد جدید ---


# ---------------- setup & run for Render (FastAPI + Webhook) ----------------
from fastapi import FastAPI, Request, HTTPException
import os
from telegram import Update
from telegram.ext import ApplicationBuilder

# Allow overriding token via environment variable for secure deployments
TOKEN = os.getenv("BOT_TOKEN", os.getenv("TOKEN", TOKEN))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://<your-service>.onrender.com/webhook

# Create FastAPI app
fastapi_app = FastAPI()

# Recreate Application with possibly updated TOKEN
application = ApplicationBuilder().token(TOKEN).build()

# Register the same handlers into this 'application' instance.
# We'll reuse the ConversationHandler and CallbackQueryHandler setup from original main.
async def ignore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # هیچ کاری نکن، فقط برای جلوگیری از خطاهای دستورات ناشناخته
    return


def setup_handlers_for_web(application):
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            S_MAIN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_main),
                MessageHandler(filters.Document.ALL & filters.User(ADMIN_ID), handle_backup_file),
            ],
            S_REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            S_REGISTER_DORM: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_dorm)],
            S_REGISTER_OTHER_DORM: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_other_dorm_name)],
            S_BUY_SELECT_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_select_product)],
            S_BUY_SELECT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_select_type)],
            S_BUY_ENTER_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_enter_qty)],
            S_AWAITING_RECEIPT: [
                MessageHandler(filters.PHOTO, handle_photo_receipt),
                MessageHandler(filters.ALL, handle_photo_receipt),
            ],
            S_ADMIN_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_product_name)],
            S_ADMIN_ADD_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_product_choice)],
            S_ADMIN_ADD_COLOR_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_color_price)],
            S_ADMIN_ADD_BW_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_bw_price)],
            S_ADMIN_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_list_handler)],
            S_ADMIN_DELETE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_delete_select_handler)],
            S_ADMIN_BLOCK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_block_id)],
            S_ADMIN_UNBLOCK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_unblock_id)],

            # --- 🔽 Stateهای جدید برای مدیریت ادمین‌ها ---
            "S_MANAGE_ADMINS": [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manage_admins)],
            "S_ADD_ADMIN": [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_admin)],
            "S_REMOVE_ADMIN": [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_remove_admin)],
            # --- 🔼 پایان stateهای جدید ---
        },
        fallbacks=[MessageHandler(filters.COMMAND, ignore_command)],
        allow_reentry=True,
    )


    application.add_handler(conv)
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    # Admin reply handling & other message handlers as in original
    async def admin_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not is_admin(uid):
            return
        return
    application.add_handler(MessageHandler(filters.TEXT & filters.User(ADMIN_ID), admin_text_router))
    application.add_handler(MessageHandler(filters.PHOTO & filters.User(ADMIN_ID), admin_text_router))
    application.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.User(ADMIN_ID), lambda u,c: None))
    return application

# Register handlers
application = setup_handlers_for_web(application)

# FastAPI lifecycle events

import asyncio

async def auto_backup():
    while True:
        import zipfile, io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in [
                USERS_FILE,
                PRODUCTS_FILE,
                ORDERS_FILE,
                PENDING_PAYMENTS_FILE,
                PURCHASES_FILE,
                BLOCKED_FILE,
            ]:
                if f.exists():
                    z.write(f, arcname=f.name)

        buf.seek(0)

        try:
            if BACKUP_GROUP_ID != 0:
                await application.bot.send_document(
                    chat_id=BACKUP_GROUP_ID,   # 🔥 اینجا تغییر کرد
                    document=buf,
                    filename="auto_backup.zip",
                    caption="📦 بکاپ خودکار هر 1 دقیقه",
                )
        except Exception as e:
            logger.warning(f"Auto backup failed: {e}")

        await asyncio.sleep(60)  # ۱ دقیقه


@fastapi_app.on_event("startup")
async def on_startup():
    try:
        await application.initialize()
        # If webhook URL provided, set webhook and start application
        if WEBHOOK_URL:
            await application.bot.set_webhook(WEBHOOK_URL)
            await application.start()
            application.create_task(auto_backup())
            logger.info("✅ Webhook set to %s and bot started", WEBHOOK_URL)
        else:
            # No webhook configured: we'll initialize but not set webhook (useful for local dev)
            await application.start()
            application.create_task(auto_backup())
            logger.info("No WEBHOOK_URL set. Bot started without webhook (use polling locally if desired).")
    except Exception as e:
        logger.exception("Failed to start bot on startup: %s", e)
        raise

@fastapi_app.on_event("shutdown")
async def on_shutdown():
    try:
        await application.stop()
        await application.shutdown()
        logger.info("Bot stopped on shutdown")
    except Exception as e:
        logger.exception("Error during shutdown: %s", e)

# ----------------------------- Telegram Webhook -----------------------------
# ----------------------------- Telegram Webhook -----------------------------
@fastapi_app.post("/webhook")
async def telegram_webhook(request: Request):
    if not WEBHOOK_URL:
        logger.warning("Received webhook call but WEBHOOK_URL not configured - processing anyway")
    body = await request.json()
    update = Update.de_json(body, application.bot)
    await application.process_update(update)
    return {"ok": True}


# ----------------------------- Health Check -----------------------------
@fastapi_app.get("/health")
@fastapi_app.head("/health")
async def health_check():
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()}


# ----------------------------- Run Modes -----------------------------
if __name__ == "__main__":
    import os
    import asyncio
    import uvicorn

    WEBHOOK = os.getenv("WEBHOOK_URL")

    # اگر روی لوکال هستی و WEBHOOK_URL تنظیم نشده → polling اجرا شود
    if not WEBHOOK:
        async def run_polling_local():
            await application.initialize()
            await application.start()
            await application.run_polling()

        asyncio.run(run_polling_local())

    # در غیر این صورت (Render) FastAPI با uvicorn اجرا شود
    else:
        port = int(os.environ.get("PORT", 10000))
        uvicorn.run(fastapi_app, host="0.0.0.0", port=port)


# ----------------------------- Expose App for Render -----------------------------
app = fastapi_app
