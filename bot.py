import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from mailtd import MailTD
import requests
import time
import threading
import re
import random
import string
import html
import json
import socket
from concurrent.futures import ThreadPoolExecutor
import os

# --- Global Configurations ---
socket.setdefaulttimeout(15)
TOKEN = '8789592665:AAFX1Nlx6ArxpR3kgbTNWIerVN9V6GyeCMc'
bot = telebot.TeleBot(TOKEN, parse_mode='HTML', num_threads=30)

DEVELOPER_ID = "6670461311"
CHANNEL_USERNAME = "@temp_mail_news"
SUPPORT_ADMIN = "@promotion_contact"

HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# --- Local Database System (Super Fast, No Firebase) ---
DB_FILE = "database.json"

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            try: return json.load(f)
            except: pass
    return {"users": {}, "mailtd_tokens": []}

def save_data():
    with open(DB_FILE, "w") as f:
        json.dump(db, f)

db = load_data()

# --- Force Join Check ---
def check_joined(user_id):
    if str(user_id) == DEVELOPER_ID: return True
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ['member', 'administrator', 'creator']
    except Exception:
        return False # If bot is not admin in channel, returns False

def send_force_join(chat_id):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"))
    markup.add(InlineKeyboardButton("✅ Verify", callback_data="verify_join"))
    bot.send_message(chat_id, "⚠️ <b>বটটি ব্যবহার করতে হলে আমাদের অফিশিয়াল চ্যানেলে জয়েন করুন!</b>\n\nজয়েন করার পর নিচের 'Verify' বাটনে ক্লিক করুন।", reply_markup=markup)

# --- Keyboard Menus ---
def get_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("✨ Generate Mail"), KeyboardButton("📥 Inbox"))
    markup.add(KeyboardButton("🌐 Server Change"), KeyboardButton("🎧 Support"))
    return markup

# --- Mail Generation Engine (Auto Fallback) ---
def create_mail_with_server(chat_id):
    pref = db["users"][chat_id].get("server_pref", "mail.tm")
    
    # Priority Queue: Try preferred first, then others
    servers_to_try = [pref]
    for s in ['mail.tm', 'mail.gw', 'mail.td']:
        if s != pref: servers_to_try.append(s)
        
    last_error = ""
    for srv in servers_to_try:
        try:
            if srv in ['mail.tm', 'mail.gw']:
                base_url = f"https://api.{srv}"
                domains_resp = requests.get(f"{base_url}/domains", headers=HTTP_HEADERS, timeout=10).json()
                domain = domains_resp['hydra:member'][0]['domain']
                username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
                email_address = f"{username}@{domain}"
                password = "ProPassword123!"
                
                acc_resp = requests.post(f"{base_url}/accounts", json={"address": email_address, "password": password}, headers=HTTP_HEADERS, timeout=10)
                if acc_resp.status_code not in [200, 201]: raise Exception(f"Server Error {acc_resp.status_code}")
                
                tok_resp = requests.post(f"{base_url}/token", json={"address": email_address, "password": password}, headers=HTTP_HEADERS, timeout=10).json()
                return acc_resp.json()['id'], email_address, tok_resp['token'], srv

            elif srv == 'mail.td':
                if not db.get("mailtd_tokens"): raise Exception("No Mail.td API tokens found.")
                token = random.choice(db["mailtd_tokens"])
                client = MailTD(token)
                domains = client.accounts.list_domains()
                domain_name = domains[0].domain if hasattr(domains[0], 'domain') else domains[0]
                username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
                email_address = f"{username}@{domain_name}"
                account = client.accounts.create(email_address, password="propassword123")
                return account.id, account.address, token, 'mail.td'
                
        except Exception as e:
            last_error = str(e)
            continue
            
    raise Exception(f"সবগুলো সার্ভার বর্তমানে ব্যস্ত! দয়া করে কিছুক্ষণ পর চেষ্টা করুন।")

# --- UI Formatting ---
def extract_and_format(subject, text_body):
    search_text = f"{subject}\n{text_body}"
    otp_match = re.search(r'(?<!\d)(\d{4,8})(?!\d)', search_text)
    if not otp_match: otp_match = re.search(r'\b([A-Z0-9]{5,8})\b', search_text)
    
    extracted_otp = otp_match.group(1) if otp_match else None
    display_body = html.escape(str(text_body)[:500])
    return extracted_otp, display_body

def format_mail_alert(msg_data, email_addr):
    extracted_otp, smart_body = extract_and_format(msg_data['subject'], msg_data['text'])
    short_email = email_addr.split('@')[0]
    
    mail_alert = (
        f"📩 <b>New Mail Received!</b>\n"
        f"📧 To: {short_email}\n"
        f"👤 From: {html.escape(msg_data['sender'])}\n"
        f"📌 Sub: {html.escape(msg_data['subject'][:30])}\n\n"
    )
    if extracted_otp:
        mail_alert += f"🔑 <b>OTP Code:</b> <code>{extracted_otp}</code>\n<i>(ক্লিক করলেই কপি হবে)</i>\n\n"
        
    mail_alert += f"<blockquote>💬 {smart_body}...</blockquote>"
    return mail_alert

# --- Inbox Checking Engine ---
def check_mail_for_account(chat_id, account, manual=False):
    acc_token = account.get('api_token', '')
    account_id = account.get('account_id', '')
    email_addr = account['email']
    srv_type = account.get('server_type')
    needs_sync = False
    new_msgs_found = 0
    
    try:
        if srv_type in ['mail.tm', 'mail.gw']:
            base_url = f"https://api.{srv_type}"
            headers = {"Authorization": f"Bearer {acc_token}", "User-Agent": HTTP_HEADERS["User-Agent"]}
            resp = requests.get(f"{base_url}/messages", headers=headers, timeout=10)
            if resp.status_code == 200:
                msgs = resp.json().get('hydra:member', [])
                for msg in msgs:
                    msg_id = msg['id']
                    if msg_id not in account['seen_msgs']:
                        account['seen_msgs'].append(msg_id)
                        needs_sync = True
                        new_msgs_found += 1
                        
                        full_resp = requests.get(f"{base_url}/messages/{msg_id}", headers=headers, timeout=10)
                        if full_resp.status_code == 200:
                            fm = full_resp.json()
                            sender_addr = fm.get('from', {}).get('address', 'Unknown')
                            alert_text = format_mail_alert({'subject': fm.get('subject', 'No Subject'), 'sender': sender_addr, 'text': fm.get('text', '')}, email_addr)
                            bot.send_message(chat_id, alert_text, parse_mode='HTML')
                            
        elif srv_type == 'mail.td':
            client = MailTD(acc_token)
            messages, _ = client.messages.list(account_id)
            for msg_preview in messages:
                msg_id = msg_preview.id
                if msg_id not in account['seen_msgs']:
                    account['seen_msgs'].append(msg_id)
                    needs_sync = True
                    new_msgs_found += 1
                    
                    full_msg = client.messages.get(account_id, msg_id)
                    alert_text = format_mail_alert({'subject': getattr(full_msg, 'subject', 'No Subject'), 'sender': getattr(full_msg, 'from_address', 'Unknown'), 'text': getattr(full_msg, 'text_body', '')}, email_addr)
                    bot.send_message(chat_id, alert_text, parse_mode='HTML')

        if needs_sync: save_data()
        
        if manual and new_msgs_found == 0:
            bot.send_message(chat_id, "⏳ <b>এখনো কোনো নতুন মেইল আসেনি!</b>\nমেইল আসলে অটোমেটিক শো করবে।")
            
    except Exception as e:
        if manual: bot.send_message(chat_id, "⚠️ ইনবক্স রিফ্রেশ করতে সমস্যা হচ্ছে। কিছুক্ষণ পর ট্রাই করুন।")

# Auto Checker Thread
check_executor = ThreadPoolExecutor(max_workers=10)

def auto_check_loop():
    while True:
        try:
            for chat_id, data in list(db["users"].items()):
                if data.get('account'):
                    check_executor.submit(check_mail_for_account, chat_id, data['account'])
        except: pass
        time.sleep(5) # Super Fast 5 seconds sync

# --- Handlers ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = str(message.chat.id)
    if chat_id not in db["users"]:
        db["users"][chat_id] = {"account": None, "server_pref": "mail.tm"}
        save_data()
        
    if not check_joined(message.from_user.id):
        send_force_join(chat_id)
        return
        
    bot.send_message(chat_id, f"🌟 <b>স্বাগতম {message.from_user.first_name}!</b> 🌟\n\nসুপার ফাস্ট প্রিমিয়াম মেইল বট-এ আপনাকে স্বাগতম। নিচে থাকা মেনু থেকে আপনার পছন্দমতো অপশন বেছে নিন।", reply_markup=get_main_menu())

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = str(message.chat.id)
    text = message.text
    
    if chat_id not in db["users"]:
        db["users"][chat_id] = {"account": None, "server_pref": "mail.tm"}
        save_data()

    if not check_joined(message.from_user.id):
        send_force_join(chat_id)
        return

    if text == "✨ Generate Mail":
        anim_msg = bot.send_message(chat_id, "<i>⚡ নতুন মেইল তৈরি করা হচ্ছে...</i>")
        try:
            # Delete old mail from memory to save space
            if db["users"][chat_id].get("account"):
                db["users"][chat_id]["account"] = None 
                
            acc_id, email_addr, used_token, srv_type = create_mail_with_server(chat_id)
            db["users"][chat_id]["account"] = {'account_id': acc_id, 'email': email_addr, 'seen_msgs': [], 'api_token': used_token, 'server_type': srv_type}
            save_data()
            
            layout = (
                f"🎉 <b>নতুন মেইল জেনারেট হয়েছে!</b>\n\n"
                f"📧 <b>Your Mail:</b>\n"
                f"<code>{email_addr}</code>\n"
                f"<i>(ক্লিক করলেই কপি হবে)</i>\n\n"
                f"📡 <b>Server:</b> {srv_type}\n"
                f"🟢 <b>Status:</b> Live\n"
            )
            bot.edit_message_text(layout, chat_id, anim_msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {str(e)}", chat_id, anim_msg.message_id)

    elif text == "📥 Inbox":
        acc = db["users"][chat_id].get("account")
        if not acc:
            bot.send_message(chat_id, "⚠️ আপনার কোনো অ্যাক্টিভ মেইল নেই। আগে 'Generate Mail' এ ক্লিক করুন।")
        else:
            bot.send_message(chat_id, "<i>🔄 ইনবক্স চেক করা হচ্ছে...</i>")
            check_mail_for_account(chat_id, acc, manual=True)

    elif text == "🌐 Server Change":
        curr_srv = db["users"][chat_id].get("server_pref", "mail.tm")
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton(f"{'✅' if curr_srv == 'mail.tm' else '⬜'} Mail.tm (Super Fast)", callback_data="set_srv_mail.tm"),
            InlineKeyboardButton(f"{'✅' if curr_srv == 'mail.gw' else '⬜'} Mail.gw (Anonymous)", callback_data="set_srv_mail.gw"),
            InlineKeyboardButton(f"{'✅' if curr_srv == 'mail.td' else '⬜'} Mail.td (Premium)", callback_data="set_srv_mail.td")
        )
        bot.send_message(chat_id, "🌐 <b>আপনার পছন্দের সার্ভার বেছে নিন:</b>\n(যেকোনো একটি সিলেক্ট করুন)", reply_markup=markup)

    elif text == "🎧 Support":
        bot.send_message(chat_id, f"👨‍💻 <b>যেকোনো প্রয়োজনে যোগাযোগ করুন:</b>\n\nঅ্যাডমিন: {SUPPORT_ADMIN}")

    # Admin Command to add Mail.td Token manually since Firebase is gone
    elif text.startswith("/addapi ") and str(chat_id) == DEVELOPER_ID:
        token = text.split(" ")[1]
        db["mailtd_tokens"].append(token)
        save_data()
        bot.send_message(chat_id, f"✅ API Added! Total: {len(db['mailtd_tokens'])}")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = str(call.message.chat.id)

    if call.data == "verify_join":
        if check_joined(call.from_user.id):
            bot.delete_message(chat_id, call.message.message_id)
            bot.send_message(chat_id, "✅ <b>ভেরিফাই সফল হয়েছে!</b>\nমেনু থেকে অপশন বেছে নিন।", reply_markup=get_main_menu())
        else:
            bot.answer_callback_query(call.id, "❌ আপনি এখনো চ্যানেলে জয়েন করেননি!", show_alert=True)

    elif call.data.startswith("set_srv_"):
        new_srv = call.data.split('_')[2]
        db["users"][chat_id]["server_pref"] = new_srv
        save_data()
        
        bot.answer_callback_query(call.id, f"✅ Server Updated to {new_srv}!", show_alert=True)
        
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton(f"{'✅' if new_srv == 'mail.tm' else '⬜'} Mail.tm (Super Fast)", callback_data="set_srv_mail.tm"),
            InlineKeyboardButton(f"{'✅' if new_srv == 'mail.gw' else '⬜'} Mail.gw (Anonymous)", callback_data="set_srv_mail.gw"),
            InlineKeyboardButton(f"{'✅' if new_srv == 'mail.td' else '⬜'} Mail.td (Premium)", callback_data="set_srv_mail.td")
        )
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)

if __name__ == "__main__":
    threading.Thread(target=auto_check_loop, daemon=True).start()
    print("🚀 Pro Mail Bot (Termux Optimized) is Live...")
    while True:
        try: bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception: time.sleep(5)

