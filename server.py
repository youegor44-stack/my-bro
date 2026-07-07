import http.server
import socketserver
import json
import os
import datetime
import urllib.request
import urllib.error
import base64
import time

PORT = 8000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
CHATS_FILE = os.path.join(BASE_DIR, "chats.json")
RELATIONS_FILE = os.path.join(BASE_DIR, "relations.json")
BLOCKS_FILE = os.path.join(BASE_DIR, "blocks.json")
SIGNAL_FILE = os.path.join(BASE_DIR, "signals.json")
STATUS_FILE = os.path.join(BASE_DIR, "status.json")  # новый файл для статусов

# Gemini API – используем модель gemini-2.5-flash (она есть в списке!)
GEMINI_API_KEY = "AQ.Ab8RN6KAYsFw8gsRCzUR9GBHRsEDjP4G2LanYMv3BrSk-B8Bzw"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GEMINI_BOT_USERNAME = "gemini"
GEMINI_PASSWORD = "910838277"

def init_files():
    for f in [USERS_FILE, CHATS_FILE, RELATIONS_FILE, BLOCKS_FILE, SIGNAL_FILE, STATUS_FILE]:
        if not os.path.exists(f):
            with open(f, "w", encoding="utf-8") as fp:
                json.dump({}, fp)

init_files()

def load_avatar_as_base64():
    for ext in ['.jpg', '.jpeg', '.png']:
        avatar_path = os.path.join(BASE_DIR, f"gemini{ext}")
        if os.path.exists(avatar_path):
            with open(avatar_path, "rb") as f:
                return base64.b64encode(f.read()).decode('utf-8')
    return ""

def create_chat_relation(user1, user2):
    chat_id = f"{min(user1, user2)}_{max(user1, user2)}"

    with open(RELATIONS_FILE, "r", encoding="utf-8") as f:
        relations = json.load(f)
    if chat_id not in relations:
        relations[chat_id] = {"user1": user1, "user2": user2, "last_seen": int(datetime.datetime.now().timestamp())}
        with open(RELATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(relations, f, indent=4, ensure_ascii=False)

    with open(CHATS_FILE, "r", encoding="utf-8") as f:
        all_chats = json.load(f)
    if chat_id not in all_chats:
        all_chats[chat_id] = {"messages": []}
        with open(CHATS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_chats, f, indent=4, ensure_ascii=False)

    return chat_id

def ensure_bot_user():
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)

    avatar_base64 = load_avatar_as_base64()

    if GEMINI_BOT_USERNAME not in users:
        users[GEMINI_BOT_USERNAME] = {
            "password": GEMINI_PASSWORD,
            "display_name": "Gemini AI",
            "avatar": avatar_base64,
            "bio": "🤖 Бот на Gemini 2.5 Flash. Напиши мне!",
            "calls_enabled": False
        }
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    else:
        users[GEMINI_BOT_USERNAME]["password"] = GEMINI_PASSWORD
        if avatar_base64:
            users[GEMINI_BOT_USERNAME]["avatar"] = avatar_base64
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=4, ensure_ascii=False)

    for uname in list(users.keys()):
        if uname != GEMINI_BOT_USERNAME:
            create_chat_relation(uname, GEMINI_BOT_USERNAME)

ensure_bot_user()

def update_status(username):
    """Обновляет время последнего действия пользователя"""
    with open(STATUS_FILE, "r", encoding="utf-8") as f:
        statuses = json.load(f)
    statuses[username] = int(time.time())
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(statuses, f, indent=4, ensure_ascii=False)

def get_statuses(usernames):
    """Возвращает словарь {username: bool} (онлайн если < 30 сек)"""
    with open(STATUS_FILE, "r", encoding="utf-8") as f:
        statuses = json.load(f)
    now = int(time.time())
    result = {}
    for u in usernames:
        last = statuses.get(u, 0)
        result[u] = (now - last) < 30  # 30 секунд – онлайн
    return result

def ask_gemini(user_text):
    """Отправляет запрос в Gemini API через прокси Happ"""
    try:
        payload = json.dumps({
            "contents": [{
                "parts": [{"text": user_text}]
            }]
        }).encode("utf-8")

        url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
        
        # Прокси через Happ (порт 10809)
        happ_proxy = "http://127.0.0.1:10809"
        proxy_handler = urllib.request.ProxyHandler({
            'http': happ_proxy,
            'https': happ_proxy
        })
        opener = urllib.request.build_opener(proxy_handler)

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        with opener.open(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            
            try:
                return result["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                return "⚠️ Не удалось прочитать ответ. Возможно, фильтр Google."
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', 'ignore')
        print(f"❌ Gemini API ошибка: {error_body}")
        
        if "API key not valid" in error_body or "API_KEY_INVALID" in error_body:
            return "⚠️ Неверный API ключ. Проверьте ключ в Google AI Studio."
        elif "quota" in error_body.lower() or "429" in str(e.code):
            return "⚠️ Квота исчерпана. Подождите 1–2 минуты или до завтра."
        elif "403" in str(e.code):
            return "⚠️ Доступ запрещён. Проверьте прокси Happ."
        elif "404" in str(e.code):
            return "⚠️ Модель не найдена. Проверьте имя модели в коде."
        else:
            return f"⚠️ Ошибка API ({e.code})"
    except Exception as e:
        print(f"❌ Системная ошибка: {e}")
        return f"⚠️ Не удалось связаться с прокси Happ: {e}"

class OmegaHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        try:
            content_len = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_len)
            data = json.loads(post_data.decode('utf-8'))
        except:
            self.send_json({"status": "error", "message": "Invalid JSON"}, 400)
            return

        path = self.path

        if path == "/register":
            username = data.get("username", "").strip().lower()
            password = data.get("password", "").strip()
            display_name = data.get("display_name", username)

            if not username or not password:
                self.send_json({"status": "error", "message": "Fill all fields"})
                return

            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users = json.load(f)

            if username in users:
                self.send_json({"status": "error", "message": "Username taken"})
                return

            users[username] = {
                "password": password,
                "display_name": display_name,
                "avatar": "",
                "bio": "",
                "calls_enabled": True
            }
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(users, f, indent=4, ensure_ascii=False)

            if username != GEMINI_BOT_USERNAME:
                create_chat_relation(username, GEMINI_BOT_USERNAME)

            update_status(username)  # обновляем статус
            self.send_json({"status": "ok", "message": "Registered"})
            return

        if path == "/login":
            username = data.get("username", "").strip().lower()
            password = data.get("password", "").strip()

            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users = json.load(f)

            if username not in users:
                self.send_json({"status": "error", "message": "User not found"})
                return
            
            if users[username]["password"] != password:
                self.send_json({"status": "error", "message": "Wrong password"})
                return

            update_status(username)  # обновляем статус
            self.send_json({
                "status": "ok",
                "user": {
                    "username": username,
                    "display_name": users[username]["display_name"],
                    "avatar": users[username].get("avatar", ""),
                    "bio": users[username].get("bio", ""),
                    "calls_enabled": users[username].get("calls_enabled", True)
                }
            })
            return

        if path == "/update_profile":
            username = data.get("username", "").strip().lower()
            
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users = json.load(f)

            if username not in users:
                self.send_json({"status": "error", "message": "User not found"})
                return

            if "display_name" in data:
                users[username]["display_name"] = data["display_name"]
            if "avatar" in data:
                users[username]["avatar"] = data["avatar"]
            if "bio" in data:
                users[username]["bio"] = data["bio"]
            if "calls_enabled" in data:
                users[username]["calls_enabled"] = data["calls_enabled"]

            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(users, f, indent=4, ensure_ascii=False)

            update_status(username)  # обновляем статус
            self.send_json({"status": "ok", "message": "Profile updated"})
            return

        if path == "/search":
            query = data.get("query", "").strip().lower()
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users = json.load(f)
            result = []
            for u, info in users.items():
                if query in u.lower() or query in info["display_name"].lower():
                    result.append({
                        "username": u,
                        "display_name": info["display_name"],
                        "avatar": info.get("avatar", ""),
                        "bio": info.get("bio", "")
                    })
            self.send_json({"users": result})
            return

        if path == "/get_profile":
            target = data.get("target", "").strip().lower()
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users = json.load(f)

            if target not in users:
                self.send_json({"status": "error", "message": "User not found"})
                return

            self.send_json({
                "status": "ok",
                "profile": {
                    "username": target,
                    "display_name": users[target]["display_name"],
                    "avatar": users[target].get("avatar", ""),
                    "bio": users[target].get("bio", "")
                }
            })
            return

        if path == "/create_chat":
            user1 = data.get("user1", "").strip().lower()
            user2 = data.get("user2", "").strip().lower()
            if not user1 or not user2:
                self.send_json({"status": "error", "message": "Missing users"})
                return

            chat_id = create_chat_relation(user1, user2)
            update_status(user1)
            update_status(user2)
            self.send_json({"status": "ok", "chat_id": chat_id})
            return

        if path == "/get_chats":
            username = data.get("username", "").strip().lower()
            if not username:
                self.send_json({"status": "ok", "chats": []})
                return

            update_status(username)  # обновляем статус

            with open(RELATIONS_FILE, "r", encoding="utf-8") as f:
                relations = json.load(f)
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users = json.load(f)
            with open(CHATS_FILE, "r", encoding="utf-8") as f:
                all_chats = json.load(f)

            user_chats = []
            for chat_id, rel in relations.items():
                user1 = rel.get("user1")
                user2 = rel.get("user2")
                if username not in (user1, user2):
                    continue
                partner = user2 if username == user1 else user1
                chat_data = all_chats.get(chat_id, {})
                partner_info = users.get(partner, {})
                msgs = chat_data.get("messages", [])
                user_chats.append({
                    "id": chat_id,
                    "partner": partner,
                    "display_name": partner_info.get("display_name", partner),
                    "avatar": partner_info.get("avatar", ""),
                    "last_message": msgs[-1]["text"] if msgs else ""
                })

            self.send_json({"status": "ok", "chats": user_chats})
            return

        if path == "/get_messages":
            chat_id = data.get("chat_id")
            with open(CHATS_FILE, "r", encoding="utf-8") as f:
                all_chats = json.load(f)
            chat = all_chats.get(chat_id, {})
            messages = chat.get("messages", [])
            self.send_json({"status": "ok", "messages": messages})
            return

        if path == "/send":
            chat_id = data.get("chat_id")
            from_user = data.get("from")
            text = data.get("text")
            time = data.get("time")

            if not chat_id or not from_user or not text:
                self.send_json({"status": "error", "message": "Missing data"})
                return

            parts = chat_id.split("_")
            u1, u2 = parts[0], parts[1]
            with open(BLOCKS_FILE, "r", encoding="utf-8") as f:
                blocks = json.load(f)
            block_key = f"{u1}_{u2}"
            if block_key in blocks:
                if blocks[block_key].get("blocked_by") == u1 and from_user == u2:
                    self.send_json({"status": "error", "message": "You are blocked"})
                    return
                if blocks[block_key].get("blocked_by") == u2 and from_user == u1:
                    self.send_json({"status": "error", "message": "You are blocked"})
                    return

            with open(CHATS_FILE, "r", encoding="utf-8") as f:
                all_chats = json.load(f)

            if chat_id not in all_chats:
                all_chats[chat_id] = {"messages": []}

            msg_id = str(time) + "_" + from_user
            all_chats[chat_id]["messages"].append({
                "id": msg_id,
                "from": from_user,
                "text": text,
                "time": time
            })

            with open(CHATS_FILE, "w", encoding="utf-8") as f:
                json.dump(all_chats, f, indent=4, ensure_ascii=False)

            # Обновляем статусы обоих участников
            update_status(u1)
            update_status(u2)

            other_user = u2 if from_user == u1 else u1
            if other_user == GEMINI_BOT_USERNAME and from_user != GEMINI_BOT_USERNAME:
                bot_reply = ask_gemini(text)
                bot_time = int(datetime.datetime.now().timestamp() * 1000)
                bot_msg_id = str(bot_time) + "_" + GEMINI_BOT_USERNAME
                all_chats[chat_id]["messages"].append({
                    "id": bot_msg_id,
                    "from": GEMINI_BOT_USERNAME,
                    "text": bot_reply,
                    "time": bot_time
                })
                with open(CHATS_FILE, "w", encoding="utf-8") as f:
                    json.dump(all_chats, f, indent=4, ensure_ascii=False)
                # обновляем статус бота (хотя он всегда офлайн)
                update_status(GEMINI_BOT_USERNAME)

            self.send_json({"status": "ok"})
            return

        if path == "/delete_message":
            chat_id = data.get("chat_id")
            msg_id = data.get("msg_id")

            with open(CHATS_FILE, "r", encoding="utf-8") as f:
                all_chats = json.load(f)

            if chat_id in all_chats:
                all_chats[chat_id]["messages"] = [m for m in all_chats[chat_id]["messages"] if m["id"] != msg_id]
                with open(CHATS_FILE, "w", encoding="utf-8") as f:
                    json.dump(all_chats, f, indent=4, ensure_ascii=False)

            self.send_json({"status": "ok"})
            return

        if path == "/delete_chat":
            chat_id = data.get("chat_id")
            username = data.get("username", "").strip().lower()

            if not chat_id or not username:
                self.send_json({"status": "error", "message": "Missing data"})
                return

            with open(RELATIONS_FILE, "r", encoding="utf-8") as f:
                relations = json.load(f)
            
            if chat_id in relations:
                del relations[chat_id]
                with open(RELATIONS_FILE, "w", encoding="utf-8") as f:
                    json.dump(relations, f, indent=4, ensure_ascii=False)

            with open(CHATS_FILE, "r", encoding="utf-8") as f:
                all_chats = json.load(f)
            
            if chat_id in all_chats:
                del all_chats[chat_id]
                with open(CHATS_FILE, "w", encoding="utf-8") as f:
                    json.dump(all_chats, f, indent=4, ensure_ascii=False)

            update_status(username)
            self.send_json({"status": "ok", "message": "Chat deleted"})
            return

        if path == "/block_user":
            chat_id = data.get("chat_id")
            target = data.get("target")
            action = data.get("action")
            requester = data.get("from")

            if not chat_id or not target or not action or not requester:
                self.send_json({"status": "error", "message": "Missing data"})
                return

            parts = chat_id.split("_")
            u1, u2 = parts[0], parts[1]
            if requester not in (u1, u2):
                self.send_json({"status": "error", "message": "You are not in this chat"})
                return

            with open(BLOCKS_FILE, "r", encoding="utf-8") as f:
                blocks = json.load(f)

            block_key = f"{u1}_{u2}"
            if block_key not in blocks:
                blocks[block_key] = {"blocked_by": None}

            if action == "block":
                blocks[block_key]["blocked_by"] = requester
            elif action == "unblock":
                if blocks[block_key].get("blocked_by") == requester:
                    blocks[block_key]["blocked_by"] = None

            with open(BLOCKS_FILE, "w", encoding="utf-8") as f:
                json.dump(blocks, f, indent=4, ensure_ascii=False)

            update_status(requester)
            self.send_json({"status": "ok"})
            return

        if path == "/call_signal":
            from_user = data.get("from", "").strip().lower()
            target = data.get("target", "").strip().lower()
            signal_type = data.get("type")
            payload = data.get("payload")

            if not from_user or not target or not signal_type:
                self.send_json({"status": "error", "message": "Missing call data"})
                return

            with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
                signals = json.load(f)

            if target not in signals:
                signals[target] = []

            signals[target].append({
                "from": from_user,
                "type": signal_type,
                "payload": payload
            })

            with open(SIGNAL_FILE, "w", encoding="utf-8") as f:
                json.dump(signals, f, indent=4, ensure_ascii=False)

            update_status(from_user)
            update_status(target)
            self.send_json({"status": "ok"})
            return

        if path == "/get_signal":
            username = data.get("username", "").strip().lower()
            if not username:
                self.send_json({"status": "ok", "messages": []})
                return

            with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
                signals = json.load(f)

            user_signals = signals.get(username, [])
            signals[username] = []
            with open(SIGNAL_FILE, "w", encoding="utf-8") as f:
                json.dump(signals, f, indent=4, ensure_ascii=False)

            update_status(username)
            self.send_json({"status": "ok", "messages": user_signals})
            return

        if path == "/add_call_event":
            chat_id = data.get("chat_id")
            text = data.get("text")
            time = data.get("time")
            from_user = data.get("from")

            if not chat_id or not text:
                self.send_json({"status": "error", "message": "Missing data"})
                return

            with open(CHATS_FILE, "r", encoding="utf-8") as f:
                all_chats = json.load(f)

            if chat_id not in all_chats:
                all_chats[chat_id] = {"messages": []}

            msg_id = "call_" + str(time)
            all_chats[chat_id]["messages"].append({
                "id": msg_id,
                "from": from_user,
                "text": text,
                "time": time,
                "is_call_event": True
            })

            with open(CHATS_FILE, "w", encoding="utf-8") as f:
                json.dump(all_chats, f, indent=4, ensure_ascii=False)

            update_status(from_user)
            self.send_json({"status": "ok"})
            return

        # НОВЫЙ ЭНДПОИНТ: получение статусов
        if path == "/get_status":
            usernames = data.get("usernames", [])
            if not usernames:
                self.send_json({"status": "ok", "statuses": {}})
                return
            statuses = get_statuses(usernames)
            self.send_json({"status": "ok", "statuses": statuses})
            return

        self.send_json({"status": "error", "message": "Unknown path"}, 404)

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_GET(self):
        if self.path == "/":
            self.path = "/omega.html"
        return super().do_GET()


if __name__ == "__main__":
    print(f"🔥 Omega Server running on http://localhost:{PORT}")
    print(f"🤖 Gemini AI бот активирован (модель: gemini-2.5-flash)")
    print(f"🔑 Пароль для Gemini: {GEMINI_PASSWORD}")
    print("📁 Положите файл gemini.jpg в папку с сервером для аватарки")
    print("🌐 Используется прокси Happ на порту 10809")
    print("🟢 Индикатор онлайн/офлайн активен (30 секунд)")
    print("Нажмите Ctrl+C чтобы остановить")
    socketserver.TCPServer.allow_reuse_address = True
    socketserver.TCPServer(("", PORT), OmegaHandler).serve_forever()