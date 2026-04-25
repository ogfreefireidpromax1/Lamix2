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

# ===== TELEGRAM SENDER WITH copy_text =====
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
            logger.error(f"Telegram API error: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False

def send_telegram_sms(date_str: str, num: str, sms_text: str, otp: str, cli_source: str, is_update: bool = False):
    """
    Send SMS notification with instant copy button using copy_text parameter
    🔥 এক ক্লিকেই OTP কপি হবে - কোনো লোডিং, কোনো অ্যালার্ট নেই!
    """
    masked = f"***{num[-4:]}" if len(num) > 4 else num
    header = "🔴 NEW SMS RECEIVED" if not is_update else "🔄 UPDATED SMS"
    
    text = f"""<b>{header}</b>

📱 <b>Number:</b> <code>{masked}</code>
🟢 <b>Service:</b> <code>{cli_source}</code>
🟡 <b>Time:</b> <code>{date_str}</code>
🔵 <b>OTP:</b> <code>{otp}</code>

✅ <b>Full Message:</b>
<code>{sms_text[:500]}</code>"""
    
    # 🔥 copy_text প্যারামিটার ব্যবহার করে ইনস্ট্যান্ট কপি বাটন
    # Telegram API version 21.7+ এ এটি সাপোর্ট করে
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": f"📋 {otp}",
                    "copy_text": otp  # ← এই লাইনটাই magic! এক ক্লিকেই কপি
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
        logger.info(f"📁 Saved to Firebase: {num[-4:]}")
    except Exception as e:
        logger.error(f"Firebase error: {e}")

async def login(page):
    """Login to the panel"""
    try:
        logger.info("🔐 Logging in...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Find and solve math captcha
        result = await page.evaluate(f"""
            (function() {{
                const myUser = "{MY_USER}";
                const myPass = "{MY_PASS}";
                
                // Find math question
                const match = document.body.innerText.match(/What is\\s+(\\d+)\\s*\\+\\s*(\\d+)/i);
                if (!match) return false;
                
                const sum = parseInt(match[1]) + parseInt(match[2]);
                console.log("Math:", match[1], "+", match[2], "=", sum);
                
                // Find input fields
                const inputs = document.querySelectorAll('input');
                let userField = null, passField = null, answerField = null;
                
                for(let inp of inputs) {{
                    const placeholder = (inp.placeholder || "").toLowerCase();
                    const type = inp.type || "";
                    const name = (inp.name || "").toLowerCase();
                    
                    if (type === 'password') {{
                        passField = inp;
                    }}
                    else if (placeholder.includes('user') || type === 'text' || name.includes('user')) {{
                        userField = inp;
                    }}
                    else if (placeholder.includes('answer') || name.includes('ans') || name.includes('captcha')) {{
                        answerField = inp;
                    }}
                }}
                
                if (userField && passField && answerField) {{
                    userField.value = myUser;
                    passField.value = myPass;
                    answerField.value = sum;
                    
                    // Trigger events
                    userField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    passField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    answerField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    
                    // Find and click login button
                    const buttons = document.querySelectorAll('button, input[type="submit"]');
                    for(let btn of buttons) {{
                        const btnText = (btn.innerText || btn.value || "").toLowerCase();
                        if(btnText.includes('login') || btnText.includes('sign')) {{
                            btn.click();
                            console.log("Login button clicked");
                            return true;
                        }}
                    }}
                    
                    // Try form submit
                    const form = document.querySelector('form');
                    if(form) {{
                        form.submit();
                        return true;
                    }}
                }}
                return false;
            }})()
        """)
        
        if result:
            await page.wait_for_timeout(5000)
            # Check if login successful
            current_url = page.url
            if "login" not in current_url.lower():
                logger.info("✅ Login successful")
                return True
            else:
                logger.warning("⚠️ Login may have failed")
                return False
        else:
            logger.error("❌ Login script failed")
            return False
            
    except Exception as e:
        logger.error(f"Login error: {e}")
        return False

async def start_bot():
    """Main bot loop"""
    logger.info("🚀 PDX SMS Bot starting...")
    logger.info("⚡ Using copy_text - Instant OTP copy without loading!")
    
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
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0'
        )
        
        page = await context.new_page()
        
        # Login with retry
        login_success = False
        for attempt in range(3):
            logger.info(f"Login attempt {attempt + 1}/3")
            if await login(page):
                login_success = True
                break
            await asyncio.sleep(10)
        
        if not login_success:
            logger.error("❌ Failed to login after 3 attempts")
            await browser.close()
            return
        
        is_first_scan = True
        consecutive_errors = 0
        
        while True:
            try:
                # Navigate to target page
                await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                
                # Check if redirected to login
                current_url = page.url
                if "login" in current_url.lower():
                    logger.warning("🔄 Redirected to login, re-authenticating...")
                    if await login(page):
                        consecutive_errors = 0
                        continue
                    else:
                        raise Exception("Re-login failed")
                
                # Extract SMS data from table
                valid_rows = []
                rows = await page.query_selector_all("table tbody tr")
                
                if rows:
                    logger.info(f"📊 Found {len(rows)} rows in table")
                    
                    for row in rows:
                        cols = await row.query_selector_all("td")
                        if len(cols) >= 7:
                            try:
                                date = (await cols[0].inner_text()).strip()
                                number = (await cols[2].inner_text()).strip()
                                sms = (await cols[4].inner_text()).strip()
                                cli = (await cols[3].inner_text()).strip()
                                
                                # Clean number
                                digits_only = re.sub(r'\D', '', number)
                                if date and len(digits_only) >= 8:
                                    valid_rows.append({
                                        "date": date,
                                        "num": number,
                                        "sms": sms,
                                        "cli": cli if cli else "Unknown"
                                    })
                            except Exception as e:
                                logger.warning(f"Row parse error: {e}")
                                continue
                
                if valid_rows:
                    logger.info(f"✅ Valid SMS rows: {len(valid_rows)}")
                    
                    if is_first_scan:
                        # Send the latest SMS on first scan
                        item = valid_rows[0]
                        otp = extract_otp(item['sms'])
                        
                        if send_telegram_sms(item['date'], item['num'], item['sms'], otp, item['cli']):
                            update_firebase(item['num'], item['sms'], item['date'], item['cli'])
                            logger.info(f"📨 Initial SMS sent - OTP: {otp}")
                        
                        # Cache all existing messages
                        for item in valid_rows:
                            sent_msgs[f"{item['num']}|{item['sms']}"] = item['date']
                        
                        is_first_scan = False
                        consecutive_errors = 0
                        
                    else:
                        # Check for new messages
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
                                
                                # Rate limit to avoid flooding
                                if new_count >= 5:
                                    await asyncio.sleep(2)
                        
                        if new_count > 0:
                            logger.info(f"📤 Sent {new_count} new SMS messages")
                
                # Clean old cache
                if len(sent_msgs) > 2000:
                    old_count = len(sent_msgs)
                    sent_msgs.clear()
                    logger.info(f"🧹 Cache cleared: {old_count} items removed")
                
                consecutive_errors = 0
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"❌ Loop error #{consecutive_errors}: {e}")
                
                wait_time = min(60, 5 * consecutive_errors)
                logger.info(f"⏳ Waiting {wait_time} seconds...")
                await asyncio.sleep(wait_time)
                
                # Recreate page on too many errors
                if consecutive_errors >= 5:
                    logger.warning("🔄 Too many errors, recreating page...")
                    await page.close()
                    page = await context.new_page()
                    if await login(page):
                        consecutive_errors = 0
                        logger.info("✅ Page recreated and logged in")
                    else:
                        logger.error("❌ Failed to re-login")
                        await asyncio.sleep(30)
            
            await asyncio.sleep(3)  # Scan interval

async def main():
    """Main entry point with auto-restart"""
    while True:
        try:
            await start_bot()
            logger.info("Bot stopped, restarting in 10 seconds...")
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
