#!/usr/bin/env python3
"""
HESERA PRO - Единый сервер (API + Telegram бот)
Работает на Render Web Service или Koyeb
"""

import json
import os
import random
import string
import threading
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
        [InlineKeyboardButton("📱 Как активировать", callback_data='howto')],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data='help')]
    ]
    
    await update.message.reply_text(
        f"👑 *HESERA PRO - Магазин лицензий*\n\n"
        f"Добро пожаловать, {user['first_name']}!\n"
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
        await query.edit_message_text("🚫 Ваш аккаунт заблокирован")
        return
    
    # ========== МАГАЗИН ==========
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
            f"🛒 *Выберите тариф:*\n\n"
            f"💰 Ваш баланс: *{user['balance']} ₽*\n\n"
            f"• 7 дней — {prices[7]} ₽ (~{prices[7]//7} ₽/день)\n"
            f"• 30 дней — {prices[30]} ₽ (~{prices[30]//30} ₽/день)\n"
            f"• 90 дней — {prices[90]} ₽ (~{prices[90]//90} ₽/день)\n"
            f"• 365 дней — {prices[365]} ₽ (~{prices[365]//365} ₽/день)",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    # ========== ПОКУПКА ==========
    elif query.data.startswith('buy_'):
        days = int(query.data.split('_')[1])
        prices = {7: 149, 30: 449, 90: 999, 365: 2499}
        price = prices[days]
        
        if user["balance"] < price:
            keyboard = [[InlineKeyboardButton("💰 Пополнить", callback_data='balance')],
                       [InlineKeyboardButton("◀️ Назад", callback_data='buy')]]
            await query.edit_message_text(
                f"❌ *Недостаточно средств!*\n\n"
                f"Нужно: {price} ₽\n"
                f"Баланс: {user['balance']} ₽\n"
                f"Не хватает: {price - user['balance']} ₽",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return
        
        # Списываем средства
        user["balance"] -= price
        db["stats"]["total_sales"] += price
        
        # Генерируем ключ
        email = f"{user_id}@t.me"
        key = gen_license_key(days)
        
        # Сохраняем лицензию
        db["licenses"][key.replace('-', '')] = {
            "key": key,
            "email": email,
            "user_id": user_id,
            "username": user["username"],
            "days": days,
            "price": price,
            "created": datetime.now().isoformat(),
            "expires": (datetime.now() + timedelta(days=days)).isoformat(),
            "activated": False,
            "devices": [],
            "activation_count": 0
        }
        
        # Привязываем ключ к email
        db["keys"][email] = key.replace('-', '')
        
        # Сохраняем покупку
        db["payments"].append({
            "user_id": user_id,
            "type": "purchase",
            "amount": price,
            "days": days,
            "key": key,
            "date": datetime.now().isoformat()
        })
        
        save_db(db)
        
        # Уведомление админу
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"💰 *Продажа!*\n👤 {user['username']}\n🔑 `{key}`\n⏱ {days} дн.\n💵 {price} ₽",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        await query.edit_message_text(
            f"✅ *Покупка успешна!*\n\n"
            f"🔑 Ключ: `{key}`\n"
            f"📧 Привязан к: `{email}`\n"
            f"⏱ Срок: {days} дней\n"
            f"💰 Списано: {price} ₽\n\n"
            f"📱 *Как активировать в приложении:*\n"
            f"1. Откройте HESERA PRO\n"
            f"2. Введите email: `{email}`\n"
            f"3. Нажмите «Войти»\n\n"
            f"Или введите ключ вручную",
            parse_mode='Markdown'
        )
    
    # ========== МОИ КЛЮЧИ ==========
    elif query.data == 'my_keys':
        user_licenses = [l for l in db["licenses"].values() if l["user_id"] == user_id]
        
        if not user_licenses:
            await query.edit_message_text("🔑 У вас пока нет ключей.\nКупите в магазине!")
            return
        
        text = "🔑 *Ваши ключи:*\n\n"
        for lic in sorted(user_licenses, key=lambda x: x["created"], reverse=True)[:10]:
            days_left = (datetime.fromisoformat(lic["expires"]) - datetime.now()).days
            status = "✅" if days_left > 0 else "❌"
            devices = len(lic.get("devices", []))
            text += f"{status} `{lic['key']}`\n"
            text += f"   📅 {lic['days']} дн. | 📱 {devices}/3 устр.\n"
            if days_left > 0:
                text += f"   ⏳ Осталось: {days_left} дн.\n"
            text += "\n"
        
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    # ========== БАЛАНС ==========
    elif query.data == 'balance':
        await query.edit_message_text(
            f"💰 *Баланс: {user['balance']} ₽*\n\n"
            f"💳 Карта: `2202 2067 1487 9132`\n"
            f"🏦 Сбербанк\n\n"
            f"📌 После оплаты отправьте:\n"
            f"`/paid СУММА`\n\n"
            f"Например: `/paid 500`",
            parse_mode='Markdown'
        )
    
    # ========== КАК АКТИВИРОВАТЬ ==========
    elif query.data == 'howto':
        await query.edit_message_text(
            f"📱 *Как активировать HESERA PRO*\n\n"
            f"1️⃣ Купите ключ в боте\n"
            f"2️⃣ Откройте приложение\n"
            f"3️⃣ Введите email: `{user_id}@t.me`\n"
            f"4️⃣ Нажмите «Войти»\n\n"
            f"🔑 Ключ на 3 устройствах\n"
            f"💬 Поддержка: @heseracfg",
            parse_mode='Markdown'
        )
    
    # ========== ПОМОЩЬ ==========
    elif query.data == 'help':
        await query.edit_message_text(
            "ℹ️ *Помощь*\n\n"
            "• Купите ключ в магазине\n"
            "• Пополните баланс через СБП\n"
            "• Активируйте в приложении\n"
            "• Один ключ = 3 устройства\n\n"
            "💬 @heseracfg",
            parse_mode='Markdown'
        )
    
    # ========== НАЗАД ==========
    elif query.data == 'back':
        await start(update, context)

async def paid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    try:
        amount = int(context.args[0])
        if amount <= 0 or amount > 10000:
            await update.message.reply_text("❌ Сумма от 1 до 10000 ₽")
            return
        
        db = load_db()
        if user_id in db["users"]:
            db["users"][user_id]["balance"] += amount
            db["payments"].append({
                "user_id": user_id,
                "type": "topup",
                "amount": amount,
                "date": datetime.now().isoformat()
            })
            save_db(db)
            await update.message.reply_text(f"✅ +{amount} ₽\n💰 Баланс: {db['users'][user_id]['balance']} ₽")
            
            # Уведомление админу
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(admin_id, f"💰 Пополнение!\n👤 {user_id}\n💵 +{amount} ₽")
                except:
                    pass
    except:
        await update.message.reply_text("❌ Используйте: `/paid СУММА`\nНапример: `/paid 500`")

# ============================================
# FLASK API
# ============================================
flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route('/')
def index():
    return jsonify({"service": "HESERA PRO API", "version": "1.0", "status": "running"})

@flask_app.route('/api/ping')
def api_ping():
    db = load_db()
    return jsonify({
        "status": "ok",
        "users": len(db["users"]),
        "keys": len(db["licenses"]),
        "active": db["stats"]["active_keys"],
        "timestamp": datetime.now().isoformat()
    })

@flask_app.route('/api/check_license', methods=['POST'])
def api_check_license():
    try:
        data = request.json
        email = data.get('email', '').lower().strip()
        device_id = data.get('device_id', '')
        
        if not email:
            return jsonify({"valid": False, "error": "Email не указан"}), 400
        
        db = load_db()
        key_hash = db["keys"].get(email)
        
        if not key_hash:
            return jsonify({"valid": False, "error": "Лицензия не найдена для этого email"}), 404
        
        license_data = db["licenses"].get(key_hash)
        if not license_data:
            return jsonify({"valid": False, "error": "Ключ не найден"}), 404
        
        days_left = (datetime.fromisoformat(license_data["expires"]) - datetime.now()).days
        
        if days_left <= 0:
            return jsonify({"valid": False, "error": "Лицензия истекла", "days_left": days_left}), 403
        
        # Регистрируем устройство
        if device_id and device_id not in license_data.get("devices", []):
            if len(license_data.get("devices", [])) >= 3:
                return jsonify({"valid": False, "error": "Достигнут лимит устройств (3)"}), 403
            license_data["devices"] = license_data.get("devices", []) + [device_id]
            license_data["activation_count"] = license_data.get("activation_count", 0) + 1
            save_db(db)
        
        return jsonify({
            "valid": True,
            "email": email,
            "days": license_data["days"],
            "days_left": days_left,
            "expires": license_data["expires"],
            "devices": len(license_data.get("devices", [])),
            "max_devices": 3
        })
    
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)}), 500

@flask_app.route('/api/activate_key', methods=['POST'])
def api_activate_key():
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
            return jsonify({"valid": False, "error": "Ключ не найден в базе"}), 404
        
        days_left = (datetime.fromisoformat(license_data["expires"]) - datetime.now()).days
        
        if days_left <= 0:
            return jsonify({"valid": False, "error": "Ключ истёк"}), 403
        
        if email:
            license_data["email"] = email
            db["keys"][email] = key
        
        if device_id and device_id not in license_data.get("devices", []):
            if len(license_data.get("devices", [])) >= 3:
                return jsonify({"valid": False, "error": "Достигнут лимит устройств (3)"}), 403
            license_data["devices"] = license_data.get("devices", []) + [device_id]
        
        license_data["activated"] = True
        license_data["activation_count"] = license_data.get("activation_count", 0) + 1
        save_db(db)
        
        return jsonify({
            "valid": True,
            "key": license_data["key"],
            "email": license_data.get("email", ""),
            "days": license_data["days"],
            "days_left": days_left,
            "expires": license_data["expires"],
            "devices": len(license_data.get("devices", [])),
            "activated": True
        })
    
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)}), 500

@flask_app.route('/api/validate_key', methods=['POST'])
def api_validate_key():
    try:
        data = request.json
        key = data.get('key', '')
        is_valid = validate_key_format(key)
        return jsonify({"valid_format": is_valid, "key": key})
    except:
        return jsonify({"valid_format": False})

# ============================================
# ЗАПУСК
# ============================================
def run_bot():
    """Запуск Telegram бота"""
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("paid", paid_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("🤖 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    print("=" * 50)
    print("👑 HESERA PRO Server")
    print("=" * 50)
    
    # Запускаем Flask API в отдельном потоке
    port = int(os.environ.get('PORT', 5000))
    flask_thread = threading.Thread(
        target=lambda: flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()
    print(f"🌐 API: http://0.0.0.0:{port}")
    
    # Запускаем бота
    run_bot()