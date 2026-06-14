#!/usr/bin/env python3
"""
HESERA PRO - Сервер с автопингом
"""

import json
import os
import random
import string
import threading
import time
import sys
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS

# Проверка и установка библиотек
try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-telegram-bot==20.7"])
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ============================================
# НАСТРОЙКИ
# ============================================
BOT_TOKEN = "8786847551:AAH6oMxtKrna7rv9RERbrkE9iFRi_vxWubA"
ADMIN_IDS = [314148464]
LICENSE_SECRET = "KLAMSI_PRO_2024_SECRET"
DB_FILE = "/opt/render/project/src/hesera_database.json"

# ============================================
# БАЗА ДАННЫХ
# ============================================
def load_db():
    try:
        if os.path.exists(DB_FILE):
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
    try:
        db["stats"]["total_keys"] = len(db["licenses"])
        db["stats"]["active_keys"] = sum(
            1 for l in db["licenses"].values()
            if datetime.fromisoformat(l["expires"]) > datetime.now()
        )
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"DB save error: {e}")

def gen_license_key(days=30):
    chars = string.ascii_uppercase + string.digits
    k = ''.join(random.choice(chars) for _ in range(16))
    hash_input = k[:8] + LICENSE_SECRET
    hash_val = abs(hash(hash_input))
    hash_str = hex(hash_val)[2:].upper().zfill(8)
    reversed_str = hash_str[::-1]
    return f"{hash_str[:4]}-{hash_str[4:8]}-{reversed_str[:4]}-{reversed_str[4:8]}"

# ============================================
# АВТОПИНГ
# ============================================
def auto_ping():
    time.sleep(30)
    while True:
        time.sleep(240)
        try:
            requests.get("http://localhost:10000/api/ping", timeout=10)
            print("🔄 Пинг OK")
        except:
            pass

# ============================================
# БОТ
# ============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = str(update.effective_user.id)
        db = load_db()
        if user_id not in db["users"]:
            db["users"][user_id] = {
                "username": update.effective_user.username or f"user_{user_id}",
                "balance": 100, "banned": False
            }
            save_db(db)
        user = db["users"][user_id]
        kb = [[InlineKeyboardButton("🛒 Купить", callback_data='buy')],
              [InlineKeyboardButton("🔑 Ключи", callback_data='keys')],
              [InlineKeyboardButton("💰 Баланс", callback_data='bal')]]
        await update.message.reply_text(
            f"👑 HESERA PRO\n💰 {user['balance']} ₽",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    except Exception as e:
        print(f"Start error: {e}")

async def btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        q = update.callback_query
        await q.answer()
        uid = str(q.from_user.id)
        db = load_db()
        u = db["users"].get(uid)
        if not u: return
        
        prices = {7:149, 30:449, 90:999, 365:2499}
        
        if q.data == 'buy':
            kb = [[InlineKeyboardButton(f"{d}дн - {p}₽", callback_data=f'b_{d}')] for d,p in prices.items()]
            kb.append([InlineKeyboardButton("◀️ Назад", callback_data='back')])
            await q.edit_message_text(f"🛒 Магазин\n💰 {u['balance']} ₽", reply_markup=InlineKeyboardMarkup(kb))
        
        elif q.data.startswith('b_'):
            d = int(q.data.split('_')[1]); p = prices[d]
            if u["balance"] < p:
                await q.edit_message_text("❌ Нет средств")
                return
            u["balance"] -= p
            key = gen_license_key(d)
            email = f"{uid}@t.me"
            db["licenses"][key.replace('-','')] = {
                "key":key, "email":email, "user_id":uid, "days":d, "price":p,
                "created":datetime.now().isoformat(),
                "expires":(datetime.now()+timedelta(days=d)).isoformat(),
                "devices":[]
            }
            db["keys"][email] = key.replace('-','')
            save_db(db)
            await q.edit_message_text(f"✅ Ключ: `{key}`\n📧 `{email}`\n⏱ {d} дн.", parse_mode='Markdown')
        
        elif q.data == 'keys':
            ls = [l for l in db["licenses"].values() if l["user_id"]==uid]
            t = "🔑 Ключи:\n" + "\n".join([f"• `{l['key']}` — {max(0,(datetime.fromisoformat(l['expires'])-datetime.now()).days)} дн." for l in ls[-5:]]) if ls else "Нет ключей"
            await q.edit_message_text(t, parse_mode='Markdown')
        
        elif q.data == 'bal':
            await q.edit_message_text(f"💰 {u['balance']} ₽\nПополнение: /paid СУММА")
        
        elif q.data == 'back':
            await start(update, context)
    except Exception as e:
        print(f"Button error: {e}")

async def paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = int(context.args[0])
        uid = str(update.effective_user.id)
        db = load_db()
        if uid in db["users"]:
            db["users"][uid]["balance"] += amt
            save_db(db)
            await update.message.reply_text(f"✅ +{amt} ₽")
    except:
        pass

# ============================================
# FLASK
# ============================================
flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route('/')
def index():
    return jsonify({"status":"running"})

@flask_app.route('/api/ping')
def ping():
    return jsonify({"status":"ok"})

@flask_app.route('/api/check_license', methods=['POST'])
def check_license():
    try:
        data = request.json
        email = data.get('email','').lower().strip()
        if not email:
            return jsonify({"valid":False,"error":"Email required"})
        db = load_db()
        kh = db["keys"].get(email)
        if not kh:
            return jsonify({"valid":False,"error":"Not found"})
        l = db["licenses"].get(kh)
        if not l:
            return jsonify({"valid":False,"error":"Not found"})
        days = (datetime.fromisoformat(l["expires"]) - datetime.now()).days
        if days <= 0:
            return jsonify({"valid":False,"error":"Expired"})
        return jsonify({"valid":True,"email":email,"days":l["days"],"days_left":days})
    except Exception as e:
        return jsonify({"valid":False,"error":str(e)})

# ============================================
# ЗАПУСК
# ============================================
if __name__ == '__main__':
    print("Starting HESERA PRO...")
    
    # Автопинг
    threading.Thread(target=auto_ping, daemon=True).start()
    
    # Flask
    port = int(os.environ.get('PORT', 10000))
    threading.Thread(
        target=lambda: flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False),
        daemon=True
    ).start()
    print(f"API: port {port}")
    
    # Telegram бот
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("paid", paid))
    app.add_handler(CallbackQueryHandler(btn))
    print("Bot starting...")
    app.run_polling()
