#!/usr/bin/env python3
"""
HESERA PRO - Сервер с автопингом (не засыпает на Render)
"""

import json
import os
import random
import string
import threading
import time
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ============================================
# НАСТРОЙКИ
# ============================================
BOT_TOKEN = "8786847551:AAH6oMxtKrna7rv9RERbrkE9iFRi_vxWubA"
ADMIN_IDS = [314148464]
LICENSE_SECRET = "KLAMSI_PRO_2024_SECRET"
DB_FILE = "hesera_database.json"

# URL для автопинга (Render сам выдаст после деплоя)
SELF_URL = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')

# ============================================
# БАЗА ДАННЫХ
# ============================================
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "users": {},
        "licenses": {},
        "keys": {},
        "payments": [],
        "stats": {"total_sales": 0, "total_keys": 0, "active_keys": 0}
    }

def save_db(db):
    db["stats"]["total_keys"] = len(db["licenses"])
    db["stats"]["active_keys"] = sum(
        1 for l in db["licenses"].values()
        if datetime.fromisoformat(l["expires"]) > datetime.now()
    )
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

# ============================================
# ГЕНЕРАЦИЯ КЛЮЧА
# ============================================
def gen_license_key(days=30):
    chars = string.ascii_uppercase + string.digits
    k = ''.join(random.choice(chars) for _ in range(16))
    hash_input = k[:8] + LICENSE_SECRET
    hash_val = abs(hash(hash_input))
    hash_str = hex(hash_val)[2:].upper().zfill(8)
    reversed_str = hash_str[::-1]
    return f"{hash_str[:4]}-{hash_str[4:8]}-{reversed_str[:4]}-{reversed_str[4:8]}"

def validate_key_format(key):
    clean = key.replace('-', '').upper()
    if len(clean) != 16:
        return False
    part1 = clean[:8]
    part2 = clean[8:]
    hash_input = part1 + LICENSE_SECRET
    hash_val = abs(hash(hash_input))
    expected = hex(hash_val)[2:].upper().zfill(8)
    return part1 == expected and part2 == expected[::-1]

# ============================================
# АВТОПИНГ (чтобы Render не засыпал)
# ============================================
def auto_ping():
    """Пингует сам себя каждые 5 минут"""
    while True:
        time.sleep(300)  # 5 минут = 300 секунд
        try:
            response = requests.get(f"{SELF_URL}/api/ping", timeout=10)
            print(f"🔄 Автопинг: {response.status_code}")
        except Exception as e:
            print(f"⚠️ Ошибка автопинга: {e}")

# ============================================
# TELEGRAM БОТ
# ============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    db = load_db()
    
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "username": update.effective_user.username or f"user_{user_id}",
            "first_name": update.effective_user.first_name or "User",
            "balance": 100,
            "purchases": [],
            "registered": datetime.now().isoformat(),
            "banned": False
        }
        save_db(db)
    
    user = db["users"][user_id]
    
    keyboard = [
        [InlineKeyboardButton("🛒 Купить ключ", callback_data='buy')],
        [InlineKeyboardButton("🔑 Мои ключи", callback_data='my_keys')],
        [InlineKeyboardButton("💰 Баланс", callback_data='balance')],
        [InlineKeyboardButton("📱 Как активировать", callback_data='howto')]
    ]
    
    await update.message.reply_text(
        f"👑 *HESERA PRO*\n\n"
        f"💰 Баланс: *{user['balance']} ₽*\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    db = load_db()
    
    if user_id not in db["users"]:
        await start(update, context)
        return
    
    user = db["users"][user_id]
    
    if user.get("banned"):
        await query.edit_message_text("🚫 Заблокирован")
        return
    
    if query.data == 'buy':
        prices = {7: 149, 30: 449, 90: 999, 365: 2499}
        keyboard = [
            [InlineKeyboardButton(f"⏱ 7 дней — {prices[7]} ₽", callback_data='buy_7')],
            [InlineKeyboardButton(f"⭐ 30 дней — {prices[30]} ₽", callback_data='buy_30')],
            [InlineKeyboardButton(f"💎 90 дней — {prices[90]} ₽", callback_data='buy_90')],
            [InlineKeyboardButton(f"👑 365 дней — {prices[365]} ₽", callback_data='buy_365')],
            [InlineKeyboardButton("◀️ Назад", callback_data='back')]
        ]
        await query.edit_message_text(
            f"🛒 *Магазин*\n💰 Баланс: *{user['balance']} ₽*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif query.data.startswith('buy_'):
        days = int(query.data.split('_')[1])
        prices = {7: 149, 30: 449, 90: 999, 365: 2499}
        price = prices[days]
        
        if user["balance"] < price:
            await query.edit_message_text(f"❌ Недостаточно средств!\nНужно: {price} ₽\nБаланс: {user['balance']} ₽")
            return
        
        user["balance"] -= price
        db["stats"]["total_sales"] += price
        
        email = f"{user_id}@t.me"
        key = gen_license_key(days)
        
        db["licenses"][key.replace('-', '')] = {
            "key": key, "email": email, "user_id": user_id,
            "username": user["username"], "days": days, "price": price,
            "created": datetime.now().isoformat(),
            "expires": (datetime.now() + timedelta(days=days)).isoformat(),
            "activated": False, "devices": []
        }
        db["keys"][email] = key.replace('-', '')
        save_db(db)
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(admin_id, f"💰 Продажа!\n👤 {user['username']}\n🔑 `{key}`\n⏱ {days} дн.\n💵 {price} ₽", parse_mode='Markdown')
            except: pass
        
        await query.edit_message_text(
            f"✅ *Куплено!*\n\n🔑 `{key}`\n📧 `{email}`\n⏱ {days} дн.\n💰 -{price} ₽\n\n📱 Введите email в приложении",
            parse_mode='Markdown'
        )
    
    elif query.data == 'my_keys':
        ls = [l for l in db["licenses"].values() if l["user_id"] == user_id]
        if not ls:
            await query.edit_message_text("🔑 Нет ключей")
            return
        text = "🔑 *Ключи:*\n\n"
        for l in sorted(ls, key=lambda x: x["created"], reverse=True)[:10]:
            days = (datetime.fromisoformat(l["expires"]) - datetime.now()).days
            text += f"• `{l['key']}` — {max(0,days)} дн.\n"
        await query.edit_message_text(text, parse_mode='Markdown')
    
    elif query.data == 'balance':
        await query.edit_message_text(
            f"💰 *Баланс: {user['balance']} ₽*\n\n💳 `2202 2067 1487 9132` (Сбер)\n\n📌 `/paid СУММА`",
            parse_mode='Markdown'
        )
    
    elif query.data == 'howto':
        await query.edit_message_text(
            f"📱 *Активация:*\n\n1. Откройте HESERA PRO\n2. Введите: `{user_id}@t.me`\n3. Нажмите Войти\n\n💬 @heseracfg",
            parse_mode='Markdown'
        )
    
    elif query.data == 'back':
        await start(update, context)

async def paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    try:
        amount = int(context.args[0])
        if amount <= 0 or amount > 10000:
            await update.message.reply_text("❌ Сумма от 1 до 10000 ₽")
            return
        db = load_db()
        if user_id in db["users"]:
            db["users"][user_id]["balance"] += amount
            save_db(db)
            await update.message.reply_text(f"✅ +{amount} ₽\n💰 Баланс: {db['users'][user_id]['balance']} ₽")
    except:
        await update.message.reply_text("❌ `/paid СУММА`\nНапример: `/paid 500`")

# ============================================
# FLASK API
# ============================================
flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route('/')
def index():
    return jsonify({"service": "HESERA PRO API", "status": "running"})

@flask_app.route('/api/ping')
def ping():
    db = load_db()
    return jsonify({
        "status": "ok",
        "users": len(db["users"]),
        "keys": len(db["licenses"]),
        "active": db["stats"]["active_keys"],
        "timestamp": datetime.now().isoformat()
    })

@flask_app.route('/api/check_license', methods=['POST'])
def check_license():
    try:
        data = request.json
        email = data.get('email', '').lower().strip()
        device_id = data.get('device_id', '')
        
        if not email:
            return jsonify({"valid": False, "error": "Email не указан"}), 400
        
        db = load_db()
        key_hash = db["keys"].get(email)
        
        if not key_hash:
            return jsonify({"valid": False, "error": "Лицензия не найдена"}), 404
        
        license_data = db["licenses"].get(key_hash)
        if not license_data:
            return jsonify({"valid": False, "error": "Ключ не найден"}), 404
        
        days_left = (datetime.fromisoformat(license_data["expires"]) - datetime.now()).days
        
        if days_left <= 0:
            return jsonify({"valid": False, "error": "Лицензия истекла"}), 403
        
        if device_id and device_id not in license_data.get("devices", []):
            if len(license_data.get("devices", [])) >= 3:
                return jsonify({"valid": False, "error": "Лимит устройств (3)"}), 403
            license_data["devices"] = license_data.get("devices", []) + [device_id]
            save_db(db)
        
        return jsonify({
            "valid": True,
            "email": email,
            "days": license_data["days"],
            "days_left": days_left,
            "expires": license_data["expires"],
            "devices": len(license_data.get("devices", []))
        })
    
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)}), 500

@flask_app.route('/api/activate_key', methods=['POST'])
def activate_key():
    try:
        data = request.json
        key = data.get('key', '').replace('-', '').upper().strip()
        email = data.get('email', '').lower().strip()
        device_id = data.get('device_id', '')
        
        if not key:
            return jsonify({"valid": False, "error": "Ключ не указан"}), 400
        
        if not validate_key_format(key):
            return jsonify({"valid": False, "error": "Неверный формат ключа"}), 400
        
        db = load_db()
        license_data = db["licenses"].get(key)
        
        if not license_data:
            return jsonify({"valid": False, "error": "Ключ не найден"}), 404
        
        days_left = (datetime.fromisoformat(license_data["expires"]) - datetime.now()).days
        
        if days_left <= 0:
            return jsonify({"valid": False, "error": "Ключ истёк"}), 403
        
        if email:
            license_data["email"] = email
            db["keys"][email] = key
        
        if device_id and device_id not in license_data.get("devices", []):
            if len(license_data.get("devices", [])) >= 3:
                return jsonify({"valid": False, "error": "Лимит устройств (3)"}), 403
            license_data["devices"] = license_data.get("devices", []) + [device_id]
        
        license_data["activated"] = True
        save_db(db)
        
        return jsonify({
            "valid": True,
            "days": license_data["days"],
            "days_left": days_left,
            "expires": license_data["expires"],
            "devices": len(license_data.get("devices", []))
        })
    
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)}), 500

# ============================================
# ЗАПУСК
# ============================================
def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("paid", paid))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("🤖 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    print("=" * 50)
    print("👑 HESERA PRO Server")
    print("=" * 50)
    
    # Запускаем автопинг (чтобы не засыпал)
    ping_thread = threading.Thread(target=auto_ping, daemon=True)
    ping_thread.start()
    print("🔄 Автопинг запущен (каждые 5 мин)")
    
    # Запускаем Flask API
    port = int(os.environ.get('PORT', 5000))
    flask_thread = threading.Thread(
        target=lambda: flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()
    print(f"🌐 API: http://0.0.0.0:{port}")
    
    # Запускаем бота
    run_bot()
