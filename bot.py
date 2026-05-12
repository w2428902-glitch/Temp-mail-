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
import gc

# --- Global Configurations ---
socket.setdefaulttimeout(15)
TOKEN = '8789592665:AAFX1Nlx6ArxpR3kgbTNWIerVN9V6GyeCMc'
bot = telebot.TeleBot(TOKEN, parse_mode='HTML', num_threads=30)

DEVELOPER_ID = "6670461311"
CO_ADMINS = ["7434118198"]

# --- Custom Settings ---
CHANNEL_USERNAME = "@temp_mail_news"
SUPPORT_ADMIN = "@promotion_contact"

HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# --- Local JSON Database System (Super Fast) ---
DB_FILE = "database.json"
db_lock = threading.Lock()

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            try: return json.load(f)
            except: pass
    return {
        "users": {}, 
        "banned": [], 
        "stats": {"total_generated": 0}, 
        "settings": {"bot_active": True, "channels": [CHANNEL_USERNAME]}, 
        "apis": {"mailtd": [], "usage": {}}
    }

def save_data():
    with db_lock:
        with open(DB_FILE, "w") as f:
            json.dump(db, f)

db = load_data()

def is_admin(chat_id):
    return str(chat_id) == DEVELOPER_ID or str(chat_id) in CO_ADMINS

# --- Force Join Check ---
def get_unjoined_channels(user_id):
    if is_admin(user_id): return []
    unjoined = []
    for ch in db["settings"].get("channels", []):
        try:
            status = bot.get_chat_member(ch, user_id).status
            if status in ['left', 'kicked']: 
                unjoined.append(ch)
        except Exception:
            pass 
    return unjoined

def send_force_join(chat_id, unjoined_channels):
    markup = InlineKeyboardMarkup(row_width=1)
    for ch in unjoined_channels:
        markup.add(InlineKeyboardButton(f"📢 Join {ch}", url=f"https://t.me/{ch.replace('@', '')}"))
    markup.add(InlineKeyboardButton("✅ Verify", callback_data="verify_join"))
    bot.send_message(chat_id, "⚠️ <b>বটটি ব্যবহার করতে হলে আমাদের অফিশিয়াল চ্যানেলে জয়েন করুন!</b>\n\nজয়েন করার পর নিচের 'Verify' বাটনে ক্লিক করুন।", reply_markup=markup)

# --- Beautiful Keyboard Menus ---
def get_main_menu(chat_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # উপরের লাইনে ২টা বাটন
    markup.row(KeyboardButton("✨ Generate Mail"), KeyboardButton("📥 Inbox"))
    # নিচের লাইনে ২টা বাটন
    markup.row(KeyboardButton("🌐 Server Change"), KeyboardButton("🎧 Support"))
    if is_admin(chat_id):
        markup.row(KeyboardButton("⚙️ Admin Panel"))
    return markup

def get_admin_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    bot_state = "🟢 Bot is ON" if db["settings"].get('bot_active', True) else "🔴 Bot is OFF"
    markup.add(InlineKeyboardButton(bot_state, callback_data="admin_toggle_bot"))
    markup.add(InlineKeyboardButton("👥 User List", callback_data="admin_users"),
               InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"))
    markup.add(InlineKeyboardButton("🔑 Manage APIs", callback_data="admin_apis_select"),
               InlineKeyboardButton("📢 Send Notice", callback_data="admin_send_promo"))
    markup.add(InlineKeyboardButton("🚫 Suspend User", callback_data="admin_ban"),
               InlineKeyboardButton("✅ Activate User", callback_data="admin_unban"))
    return markup

def get_back_button():
    return InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back to Panel", callback_data="admin_back"))

# --- Mail Generation Engine (Auto Fallback) ---
def create_mail_with_server(chat_id):
    pref = db["users"][chat_id].get("server_pref", "mail.tm")
    
    servers_to_try = [pref]
    for s in ['mail.tm', 'mail.gw', '1secmail', 'mail.td']:
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

            elif srv == '1secmail':
                domains = requests.get("https://www.1secmail.com/api/v1/?action=getDomainList", timeout=10).json()
                domain = random.choice(domains)
                username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
                email_address = f"{username}@{domain}"
                return f"{username}:{domain}", email_address, "none", '1secmail'

            elif srv == 'mail.td':
                tokens = db["apis"].get("mailtd", [])
                if not tokens: raise Exception("No Mail.td tokens.")
                token = random.choice(tokens)
                client = MailTD(token)
                domains = client.accounts.list_domains()
                domain_name = domains[0].domain if hasattr(domains[0], 'domain') else domains[0]
                username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
                email_address = f"{username}@{domain_name}"
                account = client.accounts.create(email_address, password="propassword123")
                
                db["apis"]["usage"][token] = db["apis"]["usage"].get(token, 0) + 1
                return account.id, account.address, token, 'mail.td'
                
        except Exception as e:
            last_error = str(e)
            continue
            
    raise Exception(f"সবগুলো সার্ভার বর্তমানে ডাউন! Last Error: {last_error}")

# --- UI Formatting & Link Cleaner ---
def extract_and_format(subject, text_body):
    # স্মার্ট লিংক ক্লিনার: [https://...] বা http://... টাইপের সব আজেবাজে লিংক রিমুভ করবে
    clean_text = re.sub(r'\[?https?://\S+\]?', '', str(text_body))
    clean_text = re.sub(r'<[^>]*>', '', clean_text) # Remove HTML tags if any
    clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text).strip() # Clean extra empty lines
    
    search_text = f"{subject}\n{clean_text}"
    otp_match = re.search(r'(?<!\d)(\d{4,8})(?!\d)', search_text)
    if not otp_match: otp_match = re.search(r'\b([A-Z0-9]{5,8})\b', search_text)
    
    extracted_otp = otp_match.group(1) if otp_match else None
    display_body = html.escape(clean_text[:350]) # Clean output
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
        mail_alert += (
            f"🔑 <b>OTP Code:</b>\n"
            f"╔════════════════════════╗\n"
            f"  <code>{extracted_otp}</code>\n"
            f"╚════════════════════════╝\n"
            f"<i>(ক্লিক করলেই কপি হবে)</i>\n\n"
        )
        
    mail_alert += f"<blockquote>💬 {smart_body}...</blockquote>"
    return mail_alert

# --- Inbox Checking Engine ---
def check_mail_for_account(chat_id, account):
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
                            
        elif srv_type == '1secmail':
            login, domain = account_id.split(':')
            resp = requests.get(f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}", timeout=10)
            if resp.status_code == 200:
                msgs = resp.json()
                for msg in msgs:
                    msg_id = str(msg['id'])
                    if msg_id not in account['seen_msgs']:
                        account['seen_msgs'].append(msg_id)
                        needs_sync = True
                        new_msgs_found += 1
                        
                        full_resp = requests.get(f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={msg_id}", timeout=10)
                        if full_resp.status_code == 200:
                            fm = full_resp.json()
                            alert_text = format_mail_alert({'subject': fm.get('subject', 'No Subject'), 'sender': fm.get('from', 'Unknown'), 'text': fm.get('textBody', '')}, email_addr)
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
        return new_msgs_found
            
    except Exception as e:
        return 0

# Auto Checker Thread
check_executor = ThreadPoolExecutor(max_workers=20)

def auto_check_loop():
    while True:
        try:
            for chat_id, data in list(db["users"].items()):
                if str(chat_id) in db.get("banned", []) and not is_admin(chat_id): continue
                if data.get('account'):
                    check_executor.submit(check_mail_for_account, chat_id, data['account'])
        except: pass
        gc.collect()
        time.sleep(4) 

# --- Handlers ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = str(message.chat.id)
    if chat_id not in db["users"]:
        db["users"][chat_id] = {"account": None, "server_pref": "mail.tm", "name": message.from_user.first_name, "total": 0}
        save_data()
        
    if str(chat_id) in db.get("banned", []): return
    if not db["settings"].get('bot_active', True) and not is_admin(chat_id): return

    unjoined = get_unjoined_channels(message.from_user.id)
    if unjoined:
        send_force_join(chat_id, unjoined)
        return
        
    bot.send_message(chat_id, f"🌟 <b>স্বাগতম {message.from_user.first_name}!</b> 🌟\n\nসুপার ফাস্ট প্রিমিয়াম মেইল বট-এ আপনাকে স্বাগতম। নিচে থাকা মেনু থেকে আপনার পছন্দমতো অপশন বেছে নিন।", reply_markup=get_main_menu(chat_id))

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = str(message.chat.id)
    text = message.text
    
    if chat_id not in db["users"]:
        db["users"][chat_id] = {"account": None, "server_pref": "mail.tm", "name": message.from_user.first_name, "total": 0}
        save_data()

    if str(chat_id) in db.get("banned", []): return
    if not db["settings"].get('bot_active', True) and not is_admin(chat_id): return

    unjoined = get_unjoined_channels(message.from_user.id)
    if unjoined:
        send_force_join(chat_id, unjoined)
        return

    if text == "✨ Generate Mail":
        anim_msg = bot.send_message(chat_id, "<i>⚡ নতুন মেইল তৈরি করা হচ্ছে...</i>")
        try:
            if db["users"][chat_id].get("account"):
                db["users"][chat_id]["account"] = None 
                
            acc_id, email_addr, used_token, srv_type = create_mail_with_server(chat_id)
            db["users"][chat_id]["account"] = {'account_id': acc_id, 'email': email_addr, 'seen_msgs': [], 'api_token': used_token, 'server_type': srv_type}
            db["users"][chat_id]["total"] = db["users"][chat_id].get("total", 0) + 1
            db["stats"]["total_generated"] += 1
            save_data()
            
            layout = (
                f"🎉 <b>নতুন মেইল জেনারেট হয়েছে!</b>\n\n"
                f"📧 <b>Your Mail:</b>\n"
                f"<code>{email_addr}</code>\n"
                f"<i>(ক্লিক করলেই কপি হবে)</i>\n\n"
                f"📡 <b>Server:</b> {srv_type}\n"
                f"🟢 <b>Status:</b> Live Sync Active\n"
            )
            bot.edit_message_text(layout, chat_id, anim_msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {html.escape(str(e))}", chat_id, anim_msg.message_id)

    elif text == "📥 Inbox":
        acc = db["users"][chat_id].get("account")
        if not acc:
            bot.send_message(chat_id, "⚠️ আপনার কোনো অ্যাক্টিভ মেইল নেই। আগে '✨ Generate Mail' এ ক্লিক করুন।")
        else:
            anim_msg = bot.send_message(chat_id, "<i>🔄 ইনবক্স রিফ্রেশ করা হচ্ছে...</i>")
            count = check_mail_for_account(chat_id, acc)
            if count == 0:
                bot.edit_message_text("⏳ <b>এখনো কোনো নতুন মেইল আসেনি!</b>\nমেইল আসলে অটোমেটিক নিচে শো করবে।", chat_id, anim_msg.message_id)
            else:
                bot.delete_message(chat_id, anim_msg.message_id)

    elif text == "🌐 Server Change":
        curr_srv = db["users"][chat_id].get("server_pref", "mail.tm")
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton(f"{'✅' if curr_srv == 'mail.tm' else '⬜'} Mail.tm (Super Fast)", callback_data="set_srv_mail.tm"),
            InlineKeyboardButton(f"{'✅' if curr_srv == 'mail.gw' else '⬜'} Mail.gw (Anonymous)", callback_data="set_srv_mail.gw"),
            InlineKeyboardButton(f"{'✅' if curr_srv == '1secmail' else '⬜'} Moakt / 1SecMail (Fast)", callback_data="set_srv_1secmail"),
            InlineKeyboardButton(f"{'✅' if curr_srv == 'mail.td' else '⬜'} Mail.td (Premium)", callback_data="set_srv_mail.td")
        )
        bot.send_message(chat_id, "🌐 <b>আপনার পছন্দের সার্ভার বেছে নিন:</b>\n(যেকোনো একটি সিলেক্ট করুন)", reply_markup=markup)

    elif text == "🎧 Support":
        bot.send_message(chat_id, f"👨‍💻 <b>যেকোনো প্রয়োজনে যোগাযোগ করুন:</b>\n\nঅ্যাডমিন: {SUPPORT_ADMIN}")

    elif text == "⚙️ Admin Panel" and is_admin(chat_id):
        bot.send_message(chat_id, "⚙️ <b>Admin Control Panel</b>", reply_markup=get_admin_menu())

# --- Admin Other Functions ---
def process_add_api(message):
    new_token = message.text.strip()
    if len(new_token) > 5: 
        if new_token not in db["apis"]["mailtd"]:
            db["apis"]["mailtd"].append(new_token)
            save_data()
            bot.send_message(message.chat.id, f"✅ <b>API Added Successfully!</b>\n\nমোট API: {len(db['apis']['mailtd'])}", reply_markup=get_back_button())
        else: bot.send_message(message.chat.id, "⚠️ এই API Token টি আগেই লিস্টে আছে।", reply_markup=get_back_button())
    else: bot.send_message(message.chat.id, "❌ ইনভ্যালিড টোকেন!", reply_markup=get_back_button())

def process_ban(message):
    uid = str(message.text.strip())
    if uid not in db.get("banned", []):
        db.setdefault("banned", []).append(uid)
        save_data()
    bot.send_message(message.chat.id, f"✅ <b>{uid}</b> কে সাসপেন্ড করা হয়েছে!", reply_markup=get_back_button())

def process_unban(message):
    uid = str(message.text.strip())
    if uid in db.get("banned", []):
        db["banned"].remove(uid)
        save_data()
    bot.send_message(message.chat.id, f"✅ অ্যাকাউন্ট অ্যাক্টিভ করা হয়েছে!", reply_markup=get_back_button())

def broadcast_promo(message):
    bot.clear_step_handler_by_chat_id(message.chat.id) 
    bot.send_message(message.chat.id, "🚀 <b>Broadcast Started...</b>")
    def send_to_all():
        for uid in list(db["users"].keys()):
            try: bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            except: pass
            time.sleep(0.05) 
    threading.Thread(target=send_to_all, daemon=True).start()

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = str(call.message.chat.id)

    if call.data == "verify_join":
        if not get_unjoined_channels(call.from_user.id):
            bot.delete_message(chat_id, call.message.message_id)
            bot.send_message(chat_id, "✅ <b>ভেরিফাই সফল হয়েছে!</b>\nমেনু থেকে অপশন বেছে নিন।", reply_markup=get_main_menu(chat_id))
        else:
            bot.answer_callback_query(call.id, "❌ আপনি এখনো চ্যানেলে জয়েন করেননি!", show_alert=True)

    elif call.data.startswith("set_srv_"):
        new_srv = call.data.split('_')[2]
        db["users"][chat_id]["server_pref"] = new_srv
        save_data()
        
        bot.answer_callback_query(call.id, f"✅ Server Updated!", show_alert=False)
        
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton(f"{'✅' if new_srv == 'mail.tm' else '⬜'} Mail.tm (Super Fast)", callback_data="set_srv_mail.tm"),
            InlineKeyboardButton(f"{'✅' if new_srv == 'mail.gw' else '⬜'} Mail.gw (Anonymous)", callback_data="set_srv_mail.gw"),
            InlineKeyboardButton(f"{'✅' if new_srv == '1secmail' else '⬜'} Moakt / 1SecMail (Fast)", callback_data="set_srv_1secmail"),
            InlineKeyboardButton(f"{'✅' if new_srv == 'mail.td' else '⬜'} Mail.td (Premium)", callback_data="set_srv_mail.td")
        )
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)

    elif is_admin(chat_id):
        if call.data == "admin_back":
            bot.edit_message_text("⚙️ <b>Admin Control Panel</b>", chat_id, call.message.message_id, reply_markup=get_admin_menu())
            
        elif call.data == "admin_toggle_bot":
            db["settings"]['bot_active'] = not db["settings"].get('bot_active', True)
            save_data()
            bot.answer_callback_query(call.id, f"Bot is now {'ON' if db['settings']['bot_active'] else 'OFF'}", show_alert=True)
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_admin_menu())

        elif call.data == "admin_apis_select":
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("➕ Add API Token", callback_data="admin_addapi"))
            markup.add(InlineKeyboardButton("🔙 Back to Panel", callback_data="admin_back"))
            
            api_info = f"🔑 <b>Mail.td APIs</b>\n\nTotal: {len(db['apis']['mailtd'])}\n"
            bot.edit_message_text(api_info, chat_id, call.message.message_id, reply_markup=markup)

        elif call.data == "admin_addapi":
            msg = bot.edit_message_text("➕ <b>Add New API Token</b>\n\nআপনার নতুন Mail.td API Token টি সেন্ড করুন:", chat_id, call.message.message_id, reply_markup=get_back_button())
            bot.register_next_step_handler(msg, process_add_api)
            
        elif call.data == "admin_stats":
            t_users = len(db["users"])
            t_gen = db["stats"]["total_generated"]
            stats = f"📊 <b>Bot Live Statistics</b>\n\n👥 Total Users: <b>{t_users}</b>\n🚫 Suspended: <b>{len(db.get('banned', []))}</b>\n📧 Total Mails Gen: <b>{t_gen}</b>"
            bot.edit_message_text(stats, chat_id, call.message.message_id, reply_markup=get_back_button())
            
        elif call.data == "admin_users":
            user_list = "👥 <b>Recent Users List:</b>\n\n"
            for uid, data in list(db["users"].items())[-20:]:
                user_list += f"• {data.get('name', 'User')} (<code>{uid}</code>) - <b>{data.get('total', 0)} Mails</b>\n"
            bot.edit_message_text(user_list, chat_id, call.message.message_id, reply_markup=get_back_button())

        elif call.data == "admin_ban":
            bot.edit_message_text("✍️ <b>Suspend User ID:</b>", chat_id, call.message.message_id, reply_markup=get_back_button())
            bot.register_next_step_handler(call.message, process_ban)
            
        elif call.data == "admin_unban":
            bot.edit_message_text("✍️ <b>Activate User ID:</b>", chat_id, call.message.message_id, reply_markup=get_back_button())
            bot.register_next_step_handler(call.message, process_unban)
            
        elif call.data == "admin_send_promo":
            bot.clear_step_handler_by_chat_id(chat_id)
            msg = bot.edit_message_text("📢 <b>Broadcast:</b>\n\nযেকোনো মেসেজ বা ছবি সেন্ড করুন:", chat_id, call.message.message_id, reply_markup=get_back_button())
            bot.register_next_step_handler(msg, broadcast_promo)

if __name__ == "__main__":
    threading.Thread(target=auto_check_loop, daemon=True).start()
    print("🚀 Pro Mail Bot (Termux JSON Optimized) is Live...")
    while True:
        try: bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception: time.sleep(5)
