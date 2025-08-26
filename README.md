# GROUPV4.5 – Real-Time Group Chat App 💬

**GROUPV4.5** is a self-hosted web chat application built with **Flask** and **Socket.IO**.  
It provides real-time messaging, groups, DMs, polls, file sharing, voice notes, reactions, and calls.  
⚠️ All data (users, messages, polls, files) is stored only in **server memory** – everything is lost when the server restarts.

---

## ✨ Features
- 🔐 User login & registration with CAPTCHA
- 👥 Global chat + private groups with multiple channels
- 📩 Direct Messages (DMs) with optional calls
- 📁 File & image sharing (with previews)
- 🎙️ Voice message recording (up to 60s)
- 📊 Poll creation & voting
- 😂 Emoji reactions
- 📝 Edit, reply & delete messages
- 🔎 Search loaded messages
- 🎨 Light & dark theme toggle
- 🚫 Banned word filter
- 🔔 Desktop notifications
- 📱 Fully responsive UI

---

## ⚡ Installation & Running

### 1. Clone the repository
```bash
git clone https://github.com/blei920/Private-Chat.git
```

2.Open cd
```bash
cd Private-Chat
```

3. Install modules
```bash
pip install flask flask-socketio requests beautifulsoup4
```

4. Run the server
```bash
python3 GROUPV4.5.py
```

5. Open in your browser
```bash
http://127.0.0.1:5000
```


---

⚙️ Configuration

File size limit: 1 MB per file

Voice message limit: 60 seconds

Rate limit: 1000 requests per 5 minutes per IP

Spam protection: prevents rapid spam messages

Banned words: built-in filter list

---

📜 License

Released under the MIT License.
You are free to use and modify this project for personal or educational purposes.
