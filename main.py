# -*- coding: utf-8 -*-
import os
import asyncio
import re
import requests
import time
import logging
import sys
from datetime import datetime
from playwright.async_api import async_playwright

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sms_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MY_USER = os.getenv("MY_USER")
MY_PASS = os.getenv("MY_PASS")

# Check variables
required_vars = {
    "BOT_TOKEN": BOT_TOKEN,
    "CHAT_ID": CHAT_ID,
    "MY_USER": MY_USER,
    "MY_PASS": MY_PASS
}

missing_vars = [k for k, v in required_vars.items() if not v]
if missing_vars:
    logger.error(f"Missing: {', '.join(missing_vars)}")
    sys.exit(1)

logger.info("✅ All environment variables loaded")

TARGET_URL = "http://139.99.208.63/ints/client/SMSCDRStats"
LOGIN_URL = "http://139.99.208.63/ints/login"
FB_URL = "https://family-adc9d-default-rtdb.firebaseio.com/bot"

# Links
BOT_LINK = "https://t.me/OTP_UP_BOT"
CN_LINK = "https://t.me/The_Peradox_Tips"

sent_msgs = {}

# ===== TELEGRAM SENDER =====
def send_telegram_message(text: str, keyboard: dict = None) -> bool:
    """Send message to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if keyboard:
            payload["reply_markup"] = keyboard
        
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("✅ Message sent to Telegram")
            return True
        else:
            logger.error(f"Telegram API error: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False

def send_telegram_sms(date_str: str, num: str, sms_text: str, otp: str, cli_source: str, is_update: bool = False):
    """Send SMS notification with instant copy button"""
    masked = f"***{num[-4:]}" if len(num) > 4 else num
    header = "🔴 NEW SMS RECEIVED" if not is_update else "🔄 UPDATED SMS"
    
    text = f"""<b>{header}</b>

📱 <b>Number:</b> <code>{masked}</code>
🏠 <b>Service:</b> <code>{cli_source}</code>
⏰ <b>Time:</b> <code>{date_str}</code>
🔒 <b>OTP:</b> <code>{otp}</code>

✅ <b>Full Message:</b>
<code>{sms_text[:500]}</code>"""
    
    # 🔥 copy_text প্যারামিটার - এক ক্লিকেই কপি
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": f"📋 {otp}",
                    "copy_text": otp
                }
            ],
            [
                {"text": "🔢 MAIN CHANNEL", "url": BOT_LINK},
                {"text": "📱 NUMBER GROUP", "url": CN_LINK}
            ]
        ]
    }
    
    return send_telegram_message(text, keyboard)

def extract_otp(msg: str) -> str:
    """Extract OTP from message"""
    patterns = [
        r'(?<!\d)(\d{4,8})(?!\d)',
        r'(?:OTP|code|pin|verification|kode)[:\s]*(\d{4,8})',
        r'(?:is|your|adalah)[:\s]*(\d{4,8})',
        r'(\d{6})',
        r'(\d{4})',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, msg, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            if len(str(match)) >= 4 and len(str(match)) <= 8:
                return str(match)
    
    all_numbers = re.findall(r'\b\d{4,8}\b', msg)
    if all_numbers:
        return all_numbers[0]
    
    return "N/A"

def update_firebase(num: str, msg: str, date_str: str, cli_source: str = "Unknown"):
    """Store in Firebase"""
    try:
        url = f"{FB_URL}/sms_logs/{num}.json"
        payload = {
            "number": num[-4:],
            "message": msg[:200],
            "time": date_str,
            "source": cli_source,
            "received_at": datetime.now().isoformat(),
            "paid": False
        }
        requests.put(url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"Firebase error: {e}")

async def login(page):
    """Login to the panel"""
    try:
        logger.info("🔐 Logging in...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        
        result = await page.evaluate(f"""
            (function() {{
                const myUser = "{MY_USER}";
                const myPass = "{MY_PASS}";
                
                const match = document.body.innerText.match(/What is\\s+(\\d+)\\s*\\+\\s*(\\d+)/i);
                if (!match) return false;
                
                const sum = parseInt(match[1]) + parseInt(match[2]);
                
                const inputs = document.querySelectorAll('input');
                let userField = null, passField = null, answerField = null;
                
                for(let inp of inputs) {{
                    const placeholder = (inp.placeholder || "").toLowerCase();
                    const type = inp.type || "";
                    
                    if (type === 'password') passField = inp;
                    else if (placeholder.includes('user') || type === 'text') userField = inp;
                    else if (placeholder.includes('answer')) answerField = inp;
                }}
                
                if (userField && passField && answerField) {{
                    userField.value = myUser;
                    passField.value = myPass;
                    answerField.value = sum;
                    
                    userField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    passField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    answerField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    
                    const buttons = document.querySelectorAll('button, input[type="submit"]');
                    for(let btn of buttons) {{
                        if((btn.innerText || btn.value || "").toLowerCase().includes('login')) {{
                            btn.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }})()
        """)
        
        if result:
            await page.wait_for_timeout(5000)
            logger.info("✅ Login successful")
            return True
        else:
            logger.error("❌ Login failed")
            return False
            
    except Exception as e:
        logger.error(f"Login error: {e}")
        return False

async def start_bot():
    """Main bot loop"""
    logger.info("🚀 PDX SMS Bot starting...")
    
    # Send startup message
    startup_text = """<b>🟢 PDX SMS Bot Started</b>

✅ Monitoring active
⚡ <b>Instant OTP Copy</b> - Just click the button!
📋 OTP will be copied directly to clipboard

<i>No loading, no alerts, instant copy!</i>"""
    
    send_telegram_message(startup_text, None)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox"
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        page = await context.new_page()
        
        # Login with retry
        login_success = False
        for attempt in range(3):
            if await login(page):
                login_success = True
                break
            logger.warning(f"Login attempt {attempt + 1}/3 failed")
            await asyncio.sleep(10)
        
        if not login_success:
            logger.error("Failed to login after 3 attempts")
            await browser.close()
            return
        
        # 🔥 গুরুত্বপূর্ণ: প্রথম স্ক্যানে সব SMS পাঠাবে
        is_first_scan = True
        
        while True:
            try:
                await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                
                if "login" in page.url.lower():
                    logger.warning("Redirected to login, re-authenticating...")
                    await login(page)
                    continue
                
                # Extract SMS data
                valid_rows = []
                rows = await page.query_selector_all("table tbody tr")
                
                for row in rows:
                    cols = await row.query_selector_all("td")
                    if len(cols) >= 7:
                        try:
                            date = (await cols[0].inner_text()).strip()
                            number = (await cols[2].inner_text()).strip()
                            sms = (await cols[4].inner_text()).strip()
                            cli = (await cols[3].inner_text()).strip()
                            
                            digits_only = re.sub(r'\D', '', number)
                            if date and len(digits_only) >= 8:
                                valid_rows.append({
                                    "date": date,
                                    "num": number,
                                    "sms": sms,
                                    "cli": cli if cli else "Unknown"
                                })
                        except:
                            continue
                
                if valid_rows:
                    logger.info(f"📊 Found {len(valid_rows)} valid SMS rows")
                    
                    if is_first_scan:
                        # 🔥 প্রথম স্ক্যানে সব SMS পাঠানো হবে (উল্টো ক্রমে - নতুন থেকে পুরোনো)
                        logger.info("📨 First scan - sending ALL existing SMS records...")
                        
                        sent_count = 0
                        # সবগুলো SMS পাঠাও (reverse করে যাতে newest প্রথমে আসে)
                        for item in reversed(valid_rows):
                            otp = extract_otp(item['sms'])
                            if send_telegram_sms(item['date'], item['num'], item['sms'], otp, item['cli']):
                                update_firebase(item['num'], item['sms'], item['date'], item['cli'])
                                sent_count += 1
                                logger.info(f"📤 Sent SMS #{sent_count} - OTP: {otp}")
                                
                                # ক্যাশে সেভ করো
                                sent_msgs[f"{item['num']}|{item['sms']}"] = item['date']
                                
                                # Rate limit - 1 সেকেন্ড ব্যবধান
                                await asyncio.sleep(1)
                        
                        logger.info(f"✅ First scan complete! Sent {sent_count} SMS messages")
                        
                        # 🔥 প্রথম স্ক্যান শেষ - এখন থেকে শুধু নতুন আসা SMS পাঠাবে
                        is_first_scan = False
                        
                    else:
                        # স্বাভাবিক মোড - শুধু নতুন SMS পাঠাও
                        new_count = 0
                        for item in reversed(valid_rows):
                            uid = f"{item['num']}|{item['sms']}"
                            
                            if uid not in sent_msgs:
                                otp = extract_otp(item['sms'])
                                if send_telegram_sms(item['date'], item['num'], item['sms'], otp, item['cli']):
                                    update_firebase(item['num'], item['sms'], item['date'], item['cli'])
                                    sent_msgs[uid] = item['date']
                                    new_count += 1
                                    logger.info(f"🆕 New SMS #{new_count} - OTP: {otp}")
                                
                                if new_count >= 5:
                                    await asyncio.sleep(2)
                        
                        if new_count > 0:
                            logger.info(f"📤 Sent {new_count} new SMS messages")
                        else:
                            logger.info("📭 No new SMS found")
                else:
                    logger.warning("⚠️ No valid SMS rows found!")
                
                # Clean old cache
                if len(sent_msgs) > 2000:
                    sent_msgs.clear()
                    logger.info("🧹 Cache cleared")
                    
            except Exception as e:
                logger.error(f"Loop error: {e}")
                import traceback
                logger.error(traceback.format_exc())
            
            await asyncio.sleep(3)

async def main():
    """Main entry point"""
    try:
        await start_bot()
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
