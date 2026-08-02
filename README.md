# 🎬 MoviesHouse Telegram File-to-Link Bot

Telegram bot jo kisi bhi file ko upload karne par ek shareable link generate karta hai. Link par click karne par ek branded download page khulta hai.

## 📁 Project Structure
```
movieshouse-bot/
├── bot.py              # Telegram bot handler
├── web_server.py       # Flask web server
├── templates/
│   └── download.html   # MoviesHouse branded download page
├── uploads/            # File storage folder
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

## ⚙️ Setup

### 1. Bot Token (@BotFather)
- Telegram par @BotFather search karein
- `/newbot` command bhejein
- Bot ka naam aur username dein
- Token copy kar lein

### 2. Config Update
`bot.py` file mein ye values update karein:
```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
BASE_URL = "https://yourdomain.com"  # Apna domain ya ngrok URL
```

`templates/download.html` mein:
```html
<a href="https://t.me/YourBotUsername" ...>
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run
```bash
# Terminal 1 - Web Server
python web_server.py

# Terminal 2 - Bot
python bot.py
```

## 🚀 Deployment

### Render.com (Free)
- Web service banayein
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn web_server:app`

### Railway.app (Free)
- GitHub repo connect karein
- Auto-deploy ho jayega

## ⚠️ Production Tips
- **Database:** In-memory storage ki jagah SQLite/PostgreSQL use karein
- **File Storage:** Local storage ki jagah AWS S3/Cloudflare R2 use karein
- **Security:** Rate limiting aur file type validation add karein
