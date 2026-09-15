import os
import re
import io
import csv
import sqlite3
import datetime
import time
import requests
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler

DB_PATH = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            uid TEXT PRIMARY KEY,
            checkin TEXT,
            checkout TEXT,
            suite_name TEXT,
            notified_new INTEGER DEFAULT 0,
            notified_checkin INTEGER DEFAULT 0,
            notified_checkout INTEGER DEFAULT 0,
            guest_phone TEXT DEFAULT '',
            notified_welcome INTEGER DEFAULT 0,
            notified_extension INTEGER DEFAULT 0,
            has_discount INTEGER DEFAULT 0,
            discount_code TEXT DEFAULT '',
            created_at TEXT
        )
    """)
    # Migrations for existing databases
    for col, col_type in [
        ("guest_phone", "TEXT DEFAULT ''"),
        ("notified_welcome", "INTEGER DEFAULT 0"),
        ("notified_extension", "INTEGER DEFAULT 0"),
        ("has_discount", "INTEGER DEFAULT 0"),
        ("discount_code", "TEXT DEFAULT ''"),
        ("booker_country", "TEXT DEFAULT ''"),
        ("language", "TEXT DEFAULT 'en'")
    ]:
        try:
            cur.execute(f"ALTER TABLE reservations ADD COLUMN {col} {col_type}")
        except Exception:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            message TEXT,
            status TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS inbound_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            phone TEXT,
            text TEXT,
            intent TEXT,
            language TEXT,
            status TEXT
        )
    """)
    
    defaults = {
        "sandbox_mode": "1", # 1: Güvenli Test Modu Açık, 0: Canlı Mod
        "test_phone": "+905423674599",
        "ical_url": os.getenv("ICAL_URL", ""),
        "phone_numbers": os.getenv("PHONE_NUMBERS", ""),
        "morning_time": "09:00",
        "welcome_auto_send": "1", # 1: Saat 15:00'te misafire otomatik karşılama gönder, 0: Kapalı
        "welcome_auto_time": "15:00",
        "suite_name": "Dalaman Airport Suite 11",
        "wifi_name": "VODAFONE_9P1076",
        "wifi_password": "y4b44CckUkHECRcd",
        "checkin_hour": "15:00",
        "checkout_hour": "11:00",
        "maps_url": "https://maps.google.com/?q=Ege+Mahallesi+Isparta+Sokak+No:6/1+Daire:11+Dalaman+Muğla",
        "extension_enabled": "1",
        "extension_time": "20:00",
        "extension_price": "€75",
        "msg_new_booking": "🛎 *YENİ BOOKING REZERVASYONU DÜŞTÜ!*\n\n🏨 *Tesis:* {suite_name}\n📅 *Giriş Tarihi:* {checkin}\n🚪 *Çıkış Tarihi:* {checkout}\n\nDetaylar Booking Extranet panelinize eklendi.",
        "msg_checkin": "🏨 *BUGÜN GİRİŞ (CHECK-IN) GÜNÜ!*\n\n🏨 *Tesis:* {suite_name}\n📅 *Giriş:* Bugün ({checkin})\n🚪 *Çıkış:* {checkout}\n\n🔑 Oda hazırlığını ve anahtar teslimini yapınız.\n🚨 *DİKKAT:* KBS / Polis Sistemine misafir kimlik kaydını girmeyi unutmayınız!",
        "msg_checkout": "🧹 *BUGÜN CHECK-OUT (ÇIKIŞ) GÜNÜ!*\n\n🏨 *Tesis:* {suite_name}\n🚪 *Çıkış:* Bugün ({checkout})\n📅 *Giriş Tarihi:* {checkin}\n\n🧹 Oda temizlik hazırlıklarını başlatınız.\n🚨 *DİKKAT:* KBS / Polis Sisteminden misafir çıkışını vermeyi unutmayınız!",
        "msg_extension": (
            "Dear Guest,\n\n"
            "I hope you are having a wonderful and comfortable stay at {suite_name}!\n\n"
            "We just had a last-minute cancellation for tomorrow, {tomorrow_date}, which unexpectedly opened up the calendar for an extra night.\n\n"
            "If you'd like to extend your stay and relax a bit longer without the rush of checking out, we would be delighted to offer you a special direct rate of {extension_price} (payable in cash, either in Euros or Turkish Liras).\n\n"
            "If you are interested, just let us know today so we can reserve the night for you before it reopens to online platforms.\n\n"
            "Best regards,\n"
            "{suite_name}"
        ),
        "msg_welcome": (
            "🏨 *Welcome to {suite_name}!* \n*(Dalaman Airport Suite'e Hoş Geldiniz!)*\n\n"
            "Dear Guest, we are delighted to host you. Here are your reservation & check-in details:\n"
            "*(Değerli misafirimiz, konaklama ve giriş bilgileriniz aşağıdadır:)*\n\n"
            "📅 *Dates / Tarihler:* {checkin} ➔ {checkout}\n"
            "📍 *Address / Adres:* Ege Mah. Isparta Sok. No: 6/1 Daire: 11, Dalaman / Muğla\n"
            "🗺 *Google Maps:* {maps_url}\n\n"
            "🕒 *Check-in Time:* {checkin_hour} onwards *(Giriş saati: {checkin_hour} itibarıyla)*\n"
            "🚪 *Check-out Time:* {checkout_hour} *(Çıkış saati: {checkout_hour})*\n"
            "📶 *Wi-Fi:* {wifi_name}\n"
            "🔐 *Wi-Fi Password:* {wifi_password}\n\n"
            "🎁 *EXCLUSIVE GIFT / DOĞRUDAN REZERVASYONDA %10 İNDİRİM:*\n"
            "Reply to this message with *\"YES\"* or *\"EVET\"* to activate your *%10 DIRECT BOOKING DISCOUNT* for your next stay or stay extensions via our website (dalamanairportsuites.com)!\n"
            "*(Bu mesaja \"EVET\" veya \"YES\" yazarak yanıt verin, web sitemiz veya WhatsApp üzerinden yapacağınız bir sonraki rezervasyonunuzda geçerli %10 DOĞRUDAN İNDİRİM kuponunuzu anında alın!)*\n\n"
            "🚗 *Location:* Only 10 mins from Dalaman International Airport (DLM).\n"
            "📞 WhatsApp Direct: +90 542 367 45 99\n"
            "🌐 Website: https://dalamanairportsuites.com/\n\n"
            "✨ *We wish you a wonderful and relaxing stay!*\n*(Keyifli bir konaklama dileriz!)*"
        ),
        "msg_discount_confirmed": (
            "🎉 *Congratulations! / Tebrikler!* 🌴\n\n"
            "Your *%10 DIRECT DISCOUNT* promo code has been activated:\n"
            "🏷 *PROMO CODE: DAS10*\n\n"
            "How to redeem your %10 discount:\n"
            "✅ Visit our website: https://dalamanairportsuites.com\n"
            "✅ Click the WhatsApp button or message us directly here with code *DAS10*\n"
            "✅ Save 100% on platform booking fees + get %10 instant discount!\n\n"
            "*(Web sitemizdeki WhatsApp butonuna tıklayarak veya doğrudan buradan bize 'DAS10' kodunu ileterek %10 indirimli, komisyonsuz doğrudan rezervasyonunuzu yapabilirsiniz.)*\n\n"
            "Wishing you a fantastic stay!"
        )
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
    # Auto-upgrade welcome template if existing template has %7.5
    cur.execute("SELECT value FROM settings WHERE key = 'msg_welcome'")
    curr_welcome = cur.fetchone()
    if curr_welcome and ("%7.5" in curr_welcome[0] or "%10" not in curr_welcome[0]):
        cur.execute("UPDATE settings SET value = ? WHERE key = 'msg_welcome'", (defaults["msg_welcome"],))
        
    cur.execute("SELECT value FROM settings WHERE key = 'msg_discount_confirmed'")
    curr_disc = cur.fetchone()
    if curr_disc and ("DAS75" in curr_disc[0] or "DAS10" not in curr_disc[0]):
        cur.execute("UPDATE settings SET value = ? WHERE key = 'msg_discount_confirmed'", (defaults["msg_discount_confirmed"],))
        
    conn.commit()
    conn.close()

def get_settings():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM settings")
    data = dict(cur.fetchall())
    conn.close()
    return data

def update_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def add_log(message, status="info"):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO logs (timestamp, message, status) VALUES (?, ?, ?)", (now_str, message, status))
    conn.commit()
    conn.close()

def send_whatsapp(body_text):
    cfg = get_settings()
    raw_phones = cfg.get("phone_numbers", "")
    phones = [p.strip() for p in raw_phones.split(",") if p.strip()]
    
    if not phones:
        add_log("WhatsApp gönderilemedi: Telefon numarası girilmemiş!", "error")
        return False
        
    local_gateway_url = "http://127.0.0.1:3000/send"
    success_count = 0
    
    for phone in phones:
        try:
            r = requests.post(local_gateway_url, json={"phone": phone, "message": body_text}, timeout=10)
            if r.status_code == 200:
                success_count += 1
                add_log(f"WhatsApp gönderildi -> {phone}", "success")
            else:
                err_data = r.text
                try:
                    err_data = r.json().get("error", err_data)
                except:
                    pass
                add_log(f"WhatsApp gönderilemedi ({phone}): {err_data}", "error")
        except Exception as e:
            add_log(f"WhatsApp Gateway bağlantı hatası ({phone}): {str(e)}", "error")
        time.sleep(1.5)
            
    return success_count > 0

def normalize_phone_number(raw_phone: str) -> str:
    if not raw_phone:
        return ""
    s = str(raw_phone).strip()
    s = re.sub(r"[\s\.\-\(\)]", "", s)
    if not s:
        return ""
    if s.startswith("00"):
        s = "+" + s[2:]
    elif s.startswith("+"):
        pass
    else:
        if len(s) == 11 and s.startswith("05"):
            s = "+9" + s
        elif len(s) == 10 and s.startswith("5"):
            s = "+90" + s
        else:
            s = "+" + s
    return s

def format_date_str(d_str):
    try:
        dt = datetime.datetime.strptime(d_str, "%Y%m%d")
        return dt.strftime("%d.%m.%Y")
    except:
        return d_str

def detect_guest_language(phone: str, country: str = "") -> str:
    clean_p = re.sub(r"\D", "", phone or "")
    c = (country or "").lower().strip()
    
    # Turkish / Azeri
    if clean_p.startswith("90") or clean_p.startswith("994") or c in ["tr", "az"]:
        return "tr"
    # German (Germany, Austria, Switzerland)
    if clean_p.startswith("49") or clean_p.startswith("43") or clean_p.startswith("41") or c in ["de", "at", "ch"]:
        return "de"
    # Russian (Russia, Kazakhstan, Ukraine, Belarus)
    if clean_p.startswith("7") or clean_p.startswith("380") or clean_p.startswith("375") or c in ["ru", "kz", "ua", "by"]:
        return "ru"
    # Default English (UK, USA, France, Poland, Middle East, etc.)
    return "en"

def get_multilingual_welcome(lang: str, params: dict) -> str:
    if lang == "de":
        return (
            "🏨 *Herzlich willkommen in der {suite_name}!* 🌴\n\n"
            "Lieber Gast, wir freuen uns sehr, Sie bei uns begrüßen zu dürfen. Hier sind Ihre Buchungs- und Anreisedetails:\n\n"
            "📅 *Termine:* {checkin} ➔ {checkout}\n"
            "📍 *Adresse:* Ege Mah. Isparta Sok. No: 6/1 Apt: 11, Dalaman / Muğla\n"
            "🗺 *Google Maps:* {maps_url}\n\n"
            "🕒 *Check-in:* ab {checkin_hour} Uhr\n"
            "🚪 *Check-out:* bis {checkout_hour} Uhr\n"
            "📶 *WLAN (Wi-Fi):* {wifi_name}\n"
            "🔐 *WLAN-Passwort:* {wifi_password}\n\n"
            "🎁 *EXKLUSIVES GESCHENK / %10 DIREKTRABATT:*\n"
            "Antworten Sie einfach auf diese Nachricht mit *\"JA\"* oder *\"YES\"*, um einen *%10 DIREKTRABATT (Gutscheincode: DAS10)* für Verlängerungsnächte oder Ihre nächste Buchung über unsere Website (https://dalamanairportsuites.com/) zu aktivieren!\n\n"
            "🚗 *Lage:* Nur 10 Minuten vom Flughafen Dalaman (DLM) entfernt.\n"
            "📞 WhatsApp Direkt: +90 542 367 45 99\n"
            "🌐 Website: https://dalamanairportsuites.com/\n\n"
            "✨ Wir wünschen Ihnen einen erholsamen Aufenthalt!"
        ).format(**params)
    elif lang == "ru":
        return (
            "🏨 *Добро пожаловать в {suite_name}!* 🌴\n\n"
            "Уважаемый гость, мы рады приветствовать вас! Данные вашего бронирования и заезда:\n\n"
            "📅 *Даты:* {checkin} ➔ {checkout}\n"
            "📍 *Адрес:* Ege Mah. Isparta Sok. No: 6/1 кв: 11, Dalaman / Muğla\n"
            "🗺 *Google Maps:* {maps_url}\n\n"
            "🕒 *Заезд (Check-in):* с {checkin_hour}\n"
            "🚪 *Выезд (Check-out):* до {checkout_hour}\n"
            "📶 *Wi-Fi:* {wifi_name}\n"
            "🔐 *Пароль от Wi-Fi:* {wifi_password}\n\n"
            "🎁 *СПЕЦИАЛЬНЫЙ ПОДАРОК / СКИДКА %10:*\n"
            "Ответьте на это сообщение *\"ДА\"* или *\"YES\"*, чтобы активировать *%10 СКИДКУ НА ПРЯМОЕ БРОНИРОВАНИЕ (Промокод: DAS10)* для продления проживания или следующего отдыха через наш сайт (https://dalamanairportsuites.com/)!\n\n"
            "🚗 *Расположение:* Всего 10 минут от аэропорта Даламан (DLM).\n"
            "📞 WhatsApp: +90 542 367 45 99\n"
            "🌐 Сайт: https://dalamanairportsuites.com/\n\n"
            "✨ Желаем вам прекрасного отдыха!"
        ).format(**params)
    elif lang == "tr":
        return (
            "🏨 *{suite_name}'e Hoş Geldiniz!* 🌴\n\n"
            "Değerli misafirimiz, sizi ağırlamaktan mutluluk duyuyoruz. Konaklama ve giriş bilgileriniz:\n\n"
            "📅 *Tarihler:* {checkin} ➔ {checkout}\n"
            "📍 *Adres:* Ege Mah. Isparta Sok. No: 6/1 Daire: 11, Dalaman / Muğla\n"
            "🗺 *Google Maps:* {maps_url}\n\n"
            "🕒 *Giriş Saati (Check-in):* {checkin_hour} itibarıyla\n"
            "🚪 *Çıkış Saati (Check-out):* {checkout_hour}\n"
            "📶 *Wi-Fi:* {wifi_name}\n"
            "🔐 *Wi-Fi Şifresi:* {wifi_password}\n\n"
            "🎁 *ÖZEL DOĞRUDAN REZERVASYONDA %10 İNDİRİM:*\n"
            "Bu mesaja *\"EVET\"* veya *\"YES\"* yazarak yanıt verin, konaklama uzatmanızda veya web sitemiz (https://dalamanairportsuites.com/) üzerinden yapacağınız sonraki rezervasyonda geçerli *%10 İNDİRİM (Kupon: DAS10)* kazanın!\n\n"
            "🚗 *Konum:* Dalaman Havalimanı'na (DLM) sadece 10 dakika.\n"
            "📞 WhatsApp İletişim: +90 542 367 45 99\n"
            "🌐 Web Sitemiz: https://dalamanairportsuites.com/\n\n"
            "✨ Keyifli ve huzurlu bir konaklama dileriz!"
        ).format(**params)
    else: # en
        return (
            "🏨 *Welcome to {suite_name}!* 🌴\n\n"
            "Dear Guest, we are delighted to host you. Here are your reservation & check-in details:\n\n"
            "📅 *Dates:* {checkin} ➔ {checkout}\n"
            "📍 *Address:* Ege Mah. Isparta Sok. No: 6/1 Apt: 11, Dalaman / Muğla\n"
            "🗺 *Google Maps:* {maps_url}\n\n"
            "🕒 *Check-in Time:* {checkin_hour} onwards\n"
            "🚪 *Check-out Time:* {checkout_hour}\n"
            "📶 *Wi-Fi:* {wifi_name}\n"
            "🔐 *Wi-Fi Password:* {wifi_password}\n\n"
            "🎁 *EXCLUSIVE GIFT / %10 DIRECT BOOKING DISCOUNT:*\n"
            "Reply to this message with *\"YES\"* or *\"EVET\"* to activate your *%10 DIRECT DISCOUNT (Promo Code: DAS10)* for extra nights or your next booking via our website (https://dalamanairportsuites.com/)!\n\n"
            "🚗 *Location:* Only 10 mins from Dalaman International Airport (DLM).\n"
            "📞 WhatsApp Direct: +90 542 367 45 99\n"
            "🌐 Website: https://dalamanairportsuites.com/\n\n"
            "✨ We wish you a wonderful and relaxing stay!"
        ).format(**params)

def get_multilingual_extension(lang: str, params: dict) -> str:
    if lang == "de":
        return (
            "Lieber Gast,\n\n"
            "wir hoffen, Sie genießen Ihren Aufenthalt in der {suite_name}!\n\n"
            "Aufgrund einer kurzfristigen Stornierung für morgen, {tomorrow_date}, ist unsere Suite unerwartet für eine zusätzliche Nacht frei geworden.\n\n"
            "Falls Sie Ihren Urlaub ohne Stress verlängern möchten, bieten wir Ihnen gerne einen exklusiven Direktpreis von {extension_price} (in bar zahlbar) an.\n\n"
            "Geben Sie uns einfach heute kurz per WhatsApp Bescheid!\n\n"
            "Beste Grüße,\n{suite_name}"
        ).format(**params)
    elif lang == "ru":
        return (
            "Уважаемый гость,\n\n"
            "Надеемся, вам нравится отдых в {suite_name}!\n\n"
            "В связи с отменой бронирования на завтра, {tomorrow_date}, апартаменты неожиданно освободились еще на одну ночь.\n\n"
            "Если вы хотите продлить свой отдых без спешки, мы с радостью предлагаем вам специальную прямую цену {extension_price} (оплата наличными).\n\n"
            "Если вам интересно, просто напишите нам сегодня в WhatsApp!\n\n"
            "С уважением,\n{suite_name}"
        ).format(**params)
    elif lang == "tr":
        return (
            "Değerli Misafirimiz,\n\n"
            "Umarız {suite_name} tesisimizde harika vakit geçiriyorsunuzdur!\n\n"
            "Yarın ({tomorrow_date}) için son dakika bir iptal yaşandı ve dairemiz beklenmedik şekilde bir gece için müsait oldu.\n\n"
            "Eğer tatilinizi uzatmak ve acele etmeden dinlenmek isterseniz, size doğrudan {extension_price} özel nakit fiyat teklif etmekten memnuniyet duyarız.\n\n"
            "Düşünürseniz bugün bize buradan yazmanız yeterlidir.\n\n"
            "İyi günler dileriz,\n{suite_name}"
        ).format(**params)
    else: # en
        return (
            "Dear Guest,\n\n"
            "I hope you are having a wonderful stay at {suite_name}!\n\n"
            "We just had a last-minute cancellation for tomorrow, {tomorrow_date}, which unexpectedly opened up the calendar for an extra night.\n\n"
            "If you'd like to extend your stay and relax a bit longer without the rush of checking out, we would be delighted to offer you a special direct rate of {extension_price} (payable in cash).\n\n"
            "If interested, just reply to this chat today!\n\n"
            "Best regards,\n{suite_name}"
        ).format(**params)

def get_multilingual_discount_confirmed(lang: str, params: dict) -> str:
    if lang == "de":
        return (
            "🎉 *Herzlichen Glückwunsch!* 🌴\n\n"
            "Ihr *%10 DIREKTRABATT* Promo-Code wurde aktiviert:\n"
            "🏷 *PROMO-CODE: DAS10*\n\n"
            "So lösen Sie Ihren %10-Rabatt ein:\n"
            "✅ Besuchen Sie unsere Website: https://dalamanairportsuites.com\n"
            "✅ Klicken Sie auf den WhatsApp-Button oder schreiben Sie uns direkt hier mit dem Code *DAS10*\n"
            "✅ Sparen Sie 100% der Buchungsgebühren + erhalten Sie %10 Sofortrabatt!\n\n"
            "Wir freuen uns darauf, Sie wiederzusehen!"
        ).format(**params)
    elif lang == "ru":
        return (
            "🎉 *Поздравляем!* 🌴\n\n"
            "Ваш промокод на *%10 СКИДКУ* активирован:\n"
            "🏷 *ПРОМОКОД: DAS10*\n\n"
            "Как использовать скидку %10:\n"
            "✅ Зайдите на наш сайт: https://dalamanairportsuites.com\n"
            "✅ Нажмите кнопку WhatsApp или напишите нам прямо сюда с кодом *DAS10*\n"
            "✅ Экономьте на комиссиях платформ + получайте скидку %10!\n\n"
            "Прекрасного отдыха!"
        ).format(**params)
    elif lang == "tr":
        return (
            "🎉 *Tebrikler!* 🌴\n\n"
            "*%10 DOĞRUDAN İNDİRİM* kuponunuz aktif edildi:\n"
            "🏷 *İNDİRİM KODU: DAS10*\n\n"
            "Nasıl kullanılır:\n"
            "✅ Web sitemizi ziyaret edin: https://dalamanairportsuites.com\n"
            "✅ Sitedeki WhatsApp butonuna tıklayın veya doğrudan buradan *DAS10* kodunu iletin\n"
            "✅ Aracı komisyonu olmadan anında %10 net indirim kazanın!\n\n"
            "Keyifli konaklamalar dileriz!"
        ).format(**params)
    else: # en
        return (
            "🎉 *Congratulations!* 🌴\n\n"
            "Your *%10 DIRECT DISCOUNT* promo code has been activated:\n"
            "🏷 *PROMO CODE: DAS10*\n\n"
            "How to redeem your %10 discount:\n"
            "✅ Visit our website: https://dalamanairportsuites.com\n"
            "✅ Click the WhatsApp button or message us directly here with code *DAS10*\n"
            "✅ Save 100% on platform booking fees + get %10 instant discount!\n\n"
            "Wishing you a fantastic stay!"
        ).format(**params)

def send_to_guest_or_sandbox(guest_phone: str, message: str, guest_lang: str = "en", guest_country: str = "") -> dict:
    cfg = get_settings()
    sandbox_mode = cfg.get("sandbox_mode", "1") == "1"
    test_phone = cfg.get("test_phone", "+905423674599")
    
    clean_target = normalize_phone_number(guest_phone)
    local_url = "http://127.0.0.1:3000/send"
    
    lang_names = {"de": "🇩🇪 Almanca", "ru": "🇷🇺 Rusça", "tr": "🇹🇷 Türkçe", "en": "🇬🇧 İngilizce"}
    lang_label = lang_names.get(guest_lang, guest_lang.upper())
    
    if sandbox_mode:
        # GÜVENLİ TEST MODU: Gerçek misafire ASLA gitmez! Sadece test_phone'a gider!
        sandbox_wrapper = (
            f"🧪 *[GÜVENLİ TEST MODU]*\n"
            f"👤 *Hedef Misafir:* {clean_target} ({lang_label})\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{message}"
        )
        try:
            r = requests.post(local_url, json={"phone": test_phone, "message": sandbox_wrapper}, timeout=15)
            if r.status_code == 200:
                add_log(f"Test mesajı yöneticinin telefonuna iletildi ({test_phone}) [Hedef: {clean_target} - {lang_label}]", "success")
                return {"success": True, "sandbox": True, "target": test_phone}
            else:
                add_log(f"Test mesajı gönderilemedi: {r.text}", "error")
                return {"success": False, "error": r.text}
        except Exception as e:
            add_log(f"Test mesajı bağlantı hatası: {str(e)}", "error")
            return {"success": False, "error": str(e)}
    else:
        # CANLI MOD: Gerçek misafire gider
        try:
            r = requests.post(local_url, json={"phone": clean_target, "message": message}, timeout=15)
            if r.status_code == 200:
                add_log(f"WhatsApp mesajı misafire iletildi -> {clean_target} ({lang_label})", "success")
                return {"success": True, "sandbox": False, "target": clean_target}
            else:
                add_log(f"Mesaj iletilemedi ({clean_target}): {r.text}", "error")
                return {"success": False, "error": r.text}
        except Exception as e:
            add_log(f"Bağlantı hatası ({clean_target}): {str(e)}", "error")
            return {"success": False, "error": str(e)}

def parse_ical(content):
    events = []
    blocks = content.split("BEGIN:VEVENT")
    for b in blocks[1:]:
        start_m = re.search(r"DTSTART;VALUE=DATE:(\d{8})", b)
        end_m = re.search(r"DTEND;VALUE=DATE:(\d{8})", b)
        uid_m = re.search(r"UID:([^\r\n]+)", b)
        
        if start_m and end_m and uid_m:
            events.append({
                "checkin": start_m.group(1),
                "checkout": end_m.group(1),
                "uid": uid_m.group(1).strip()
            })
    return events

def sync_calendar():
    cfg = get_settings()
    ical_url = cfg.get("ical_url")
    suite_name = cfg.get("suite_name", "Dalaman Airport Suite 11")
    msg_tpl = cfg.get("msg_new_booking", "🛎 *YENİ BOOKING REZERVASYONU DÜŞTÜ!*\n\n🏨 *Tesis:* {suite_name}\n📅 *Giriş Tarihi:* {checkin}\n🚪 *Çıkış Tarihi:* {checkout}")
    
    if not ical_url:
        return
        
    try:
        resp = requests.get(ical_url, timeout=20)
        if resp.status_code != 200:
            add_log(f"iCal indirilemedi! HTTP {resp.status_code}", "error")
            return
            
        events = parse_ical(resp.text)
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        new_count = 0
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for ev in events:
            cur.execute("SELECT uid FROM reservations WHERE uid = ?", (ev["uid"],))
            existing = cur.fetchone()
            
            if not existing:
                cur.execute("""
                    INSERT INTO reservations (uid, checkin, checkout, suite_name, notified_new, created_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                """, (ev["uid"], ev["checkin"], ev["checkout"], suite_name, now_str))
                conn.commit()
                new_count += 1
                
                c_in = format_date_str(ev["checkin"])
                c_out = format_date_str(ev["checkout"])
                
                # Sablondan mesaj olustur
                msg = msg_tpl.replace("{suite_name}", suite_name).replace("{checkin}", c_in).replace("{checkout}", c_out)
                send_whatsapp(msg)
                add_log(f"Yeni rezervasyon yakalandı: {c_in} - {c_out}", "success")
                
        conn.close()
        add_log(f"Takvim senkronize edildi. (Toplam {len(events)} rezervasyon, {new_count} yeni)", "info")
        
    except Exception as e:
        add_log(f"Senkronizasyon hatasi: {str(e)}", "error")

def check_daily_reminders():
    cfg = get_settings()
    suite_name = cfg.get("suite_name", "Dalaman Airport Suite 11")
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    
    checkout_tpl = cfg.get("msg_checkout", "🧹 *BUGÜN CHECK-OUT (ÇIKIŞ) GÜNÜ!*\n\n🏨 *Tesis:* {suite_name}\n🚪 *Çıkış:* Bugün ({checkout})\n📅 *Giriş Yapılan Tarih:* {checkin}\n\n⚠️ Lütfen oda boşaltma ve temizlik hazırlıklarını başlatınız.")
    checkin_tpl = cfg.get("msg_checkin", "🏨 *BUGÜN GİRİŞ (CHECK-IN) GÜNÜ!*\n\n🏨 *Tesis:* {suite_name}\n📅 *Giriş:* Bugün ({checkin})\n🚪 *Çıkış Tarihi:* {checkout}\n\n🔑 Oda hazırlığını ve anahtar teslim kontrolünü yapınız.")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # 1. Bugunku Cikislar (Check-out)
    cur.execute("SELECT uid, checkin, checkout FROM reservations WHERE checkout = ? AND notified_checkout = 0", (today_str,))
    checkouts = cur.fetchall()
    
    for r in checkouts:
        uid, c_in, c_out = r
        c_in_fmt = format_date_str(c_in)
        c_out_fmt = format_date_str(c_out)
        msg = checkout_tpl.replace("{suite_name}", suite_name).replace("{checkin}", c_in_fmt).replace("{checkout}", c_out_fmt)
        if send_whatsapp(msg):
            cur.execute("UPDATE reservations SET notified_checkout = 1 WHERE uid = ?", (uid,))
            conn.commit()
            add_log(f"Check-out hatirlatmasi gonderildi ({c_out_fmt})", "success")
            
    # 2. Bugunku Girisler (Check-in)
    cur.execute("SELECT uid, checkin, checkout FROM reservations WHERE checkin = ? AND notified_checkin = 0", (today_str,))
    checkins = cur.fetchall()
    
    for r in checkins:
        uid, c_in, c_out = r
        c_in_fmt = format_date_str(c_in)
        c_out_fmt = format_date_str(c_out)
        msg = checkin_tpl.replace("{suite_name}", suite_name).replace("{checkin}", c_in_fmt).replace("{checkout}", c_out_fmt)
        if send_whatsapp(msg):
            cur.execute("UPDATE reservations SET notified_checkin = 1 WHERE uid = ?", (uid,))
            conn.commit()
            add_log(f"Check-in hatirlatmasi gonderildi ({c_in_fmt})", "success")
            
    conn.close()

def check_extension_offers():
    cfg = get_settings()
    if cfg.get("extension_enabled", "1") != "1":
        return
        
    suite_name = cfg.get("suite_name", "Dalaman Airport Suite 11")
    ext_price = cfg.get("extension_price", "€75")
    ext_tpl = cfg.get("msg_extension", "")
    if not ext_tpl:
        return
        
    now = datetime.datetime.now()
    tomorrow_dt = now + datetime.timedelta(days=1)
    tomorrow_str = tomorrow_dt.strftime("%Y%m%d")
    tomorrow_fmt = tomorrow_dt.strftime("%d.%m.%Y")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # 1. Yarin odaya yeni giris var mi kontrol et (Oda yarin dolu mu?)
    cur.execute("SELECT uid FROM reservations WHERE checkin = ?", (tomorrow_str,))
    if cur.fetchone():
        conn.close()
        return
        
    # 2. Yarin cikis yapacak, numarasi girilmis ve henuz uzatma teklif edilmemis misafirleri bul
    cur.execute("""
        SELECT uid, checkin, checkout, guest_phone, booker_country, language 
        FROM reservations 
        WHERE checkout = ? AND guest_phone != '' AND notified_extension = 0
    """, (tomorrow_str,))
    candidates = cur.fetchall()
    
    for r in candidates:
        uid, c_in, c_out, phone, booker_country, guest_lang = r
        clean_phone = (phone or "").strip()
        if not clean_phone:
            continue
            
        lang = guest_lang or detect_guest_language(clean_phone, booker_country)
        params = {
            "suite_name": suite_name,
            "tomorrow_date": tomorrow_fmt,
            "extension_price": ext_price,
            "checkin": format_date_str(c_in),
            "checkout": format_date_str(c_out)
        }
        msg = get_multilingual_extension(lang, params)
        
        res = send_to_guest_or_sandbox(clean_phone, msg, lang, booker_country)
        if res.get("success"):
            cur.execute("UPDATE reservations SET notified_extension = 1 WHERE uid = ?", (uid,))
            conn.commit()
        time.sleep(2)
        
    conn.close()

def check_automatic_welcomes():
    cfg = get_settings()
    if cfg.get("welcome_auto_send", "1") != "1":
        return
        
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Bugün giriş yapacak, telefonu kayıtlı ve henüz karşılama gitmemiş misafirleri bul
    cur.execute("""
        SELECT uid, checkin, checkout, guest_phone, suite_name, booker_country, language 
        FROM reservations 
        WHERE checkin = ? AND guest_phone != '' AND guest_phone IS NOT NULL AND notified_welcome = 0
    """, (today_str,))
    candidates = cur.fetchall()
    
    if not candidates:
        conn.close()
        return
        
    suite_name = cfg.get("suite_name", "Dalaman Airport Suite 11")
    wifi_name = cfg.get("wifi_name", "VODAFONE_9P1076")
    wifi_password = cfg.get("wifi_password", "y4b44CckUkHECRcd")
    checkin_hour = cfg.get("checkin_hour", "15:00")
    checkout_hour = cfg.get("checkout_hour", "11:00")
    maps_url = cfg.get("maps_url", "https://maps.google.com/?q=Ege+Mahallesi+Isparta+Sokak+No:6/1+Daire:11+Dalaman+Muğla")
    
    for r in candidates:
        uid, c_in_raw, c_out_raw, phone, r_suite, booker_country, guest_lang = r
        clean_phone = (phone or "").strip()
        if not clean_phone:
            continue
            
        c_in = format_date_str(c_in_raw)
        c_out = format_date_str(c_out_raw)
        lang = guest_lang or detect_guest_language(clean_phone, booker_country)
        
        params = {
            "suite_name": suite_name,
            "checkin": c_in,
            "checkout": c_out,
            "wifi_name": wifi_name,
            "wifi_password": wifi_password,
            "checkin_hour": checkin_hour,
            "checkout_hour": checkout_hour,
            "maps_url": maps_url
        }
        
        msg = get_multilingual_welcome(lang, params)
        res = send_to_guest_or_sandbox(clean_phone, msg, lang, booker_country)
        
        if res.get("success"):
            cur.execute("UPDATE reservations SET language = ?, notified_welcome = 1 WHERE uid = ?", (lang, uid))
            conn.commit()
            add_log(f"Saat 15:00 Otomatik Karşılama İletildi ({lang.upper()}) -> {clean_phone}", "success")
        time.sleep(2)
        
    conn.close()

scheduler = BackgroundScheduler()

def scheduled_job():
    cfg = get_settings()
    morning_time = cfg.get("morning_time", "09:00")
    current_hm = datetime.datetime.now().strftime("%H:%M")
    
    sync_calendar()
    
    # Sabah saati geldiyse veya gecildiyse henuz iletilmemis gunluk hatirlatmalari gonder
    now = datetime.datetime.now()
    try:
        parts = morning_time.split(":")
        m_hour = int(parts[0])
        m_minute = int(parts[1]) if len(parts) > 1 else 0
        morning_dt = now.replace(hour=m_hour, minute=m_minute, second=0, microsecond=0)
        if now >= morning_dt:
            check_daily_reminders()
    except Exception:
        if current_hm >= morning_time:
            check_daily_reminders()
            
    # Saat 15:00: Bugun giris yapacak misafirlere kendi dilinde karsilama gonder
    try:
        w_time = cfg.get("welcome_auto_time", "15:00")
        w_parts = w_time.split(":")
        w_hour = int(w_parts[0])
        w_minute = int(w_parts[1]) if len(w_parts) > 1 else 0
        welcome_dt = now.replace(hour=w_hour, minute=w_minute, second=0, microsecond=0)
        if now >= welcome_dt:
            check_automatic_welcomes()
    except Exception:
        pass

    # Aksam uzatma teklifi kontrolu (varsayilan 20:00)
    try:
        ext_time = cfg.get("extension_time", "20:00")
        e_parts = ext_time.split(":")
        e_hour = int(e_parts[0])
        e_minute = int(e_parts[1]) if len(e_parts) > 1 else 0
        ext_dt = now.replace(hour=e_hour, minute=e_minute, second=0, microsecond=0)
        if now >= ext_dt:
            check_extension_offers()
    except Exception:
        pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    sync_calendar()
    scheduler.add_job(scheduled_job, "interval", minutes=2)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    cfg = get_settings()
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    today_display = datetime.datetime.now().strftime("%d.%m.%Y")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("SELECT uid, checkin, checkout, notified_checkout, guest_phone, notified_welcome FROM reservations WHERE checkout = ?", (today_str,))
    today_checkouts = [{"uid": r[0], "checkin": format_date_str(r[1]), "checkout": format_date_str(r[2]), "notified": r[3], "guest_phone": r[4] or "", "notified_welcome": r[5]} for r in cur.fetchall()]
    
    cur.execute("SELECT uid, checkin, checkout, notified_checkin, guest_phone, notified_welcome FROM reservations WHERE checkin = ?", (today_str,))
    today_checkins = [{"uid": r[0], "checkin": format_date_str(r[1]), "checkout": format_date_str(r[2]), "notified": r[3], "guest_phone": r[4] or "", "notified_welcome": r[5]} for r in cur.fetchall()]
    
    cur.execute("SELECT uid, checkin, checkout, created_at, notified_checkout, guest_phone, notified_welcome, notified_extension, has_discount, discount_code, booker_country, language FROM reservations ORDER BY checkin DESC LIMIT 100")
    all_res = []
    current_hour = datetime.datetime.now().hour
    
    for r in cur.fetchall():
        uid, c_in, c_out, created_at, notif_out, guest_phone, notif_welcome, notif_ext, has_discount, discount_code, booker_country, guest_lang = r
        
        if today_str > c_out:
            status = "Çıkış Yaptı"
        elif today_str == c_out:
            # Bugün çıkış günü: saat 11:00'i geçtiyse veya bildirim gittiyse "Çıkış Yaptı", öncesinde "Bugün Çıkış"
            if current_hour >= 11 or notif_out == 1:
                status = "Çıkış Yaptı"
            else:
                status = "Bugün Çıkış"
        elif today_str == c_in:
            status = "Bugün Giriş"
        elif c_in < today_str < c_out:
            status = "Konaklıyor"
        else:
            status = "Gelecek"
            
        calculated_lang = guest_lang or detect_guest_language(guest_phone or "", booker_country or "")
            
        all_res.append({
            "uid": uid,
            "short_uid": uid[:15] + "...",
            "checkin": format_date_str(c_in),
            "checkout": format_date_str(c_out),
            "status": status,
            "guest_phone": guest_phone or "",
            "notified_welcome": notif_welcome,
            "notified_extension": notif_ext,
            "has_discount": has_discount or 0,
            "discount_code": discount_code or "",
            "booker_country": (booker_country or "").upper(),
            "language": calculated_lang,
            "created_at": created_at
        })
        
    cur.execute("SELECT timestamp, message, status FROM logs ORDER BY id DESC LIMIT 40")
    logs = [{"time": r[0], "msg": r[1], "status": r[2]} for r in cur.fetchall()]
    
    cur.execute("SELECT timestamp, phone, text, intent, language, status FROM inbound_messages ORDER BY id DESC LIMIT 30")
    inbound_messages = [{"time": r[0], "phone": r[1], "text": r[2], "intent": r[3], "lang": r[4], "status": r[5]} for r in cur.fetchall()]
    
    cur.execute("SELECT COUNT(*) FROM reservations WHERE has_discount = 1")
    discount_res_count = cur.fetchone()[0]
    
    conn.close()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "config": cfg,
        "today_display": today_display,
        "today_checkouts": today_checkouts,
        "today_checkins": today_checkins,
        "reservations": all_res,
        "inbound_messages": inbound_messages,
        "discount_count": discount_res_count,
        "logs": logs
    })

@app.post("/api/settings")
async def save_settings(
    suite_name: str = Form(...),
    phone_numbers: str = Form(...),
    morning_time: str = Form(...),
    ical_url: str = Form(...),
    wifi_name: str = Form("VODAFONE_9P1076"),
    wifi_password: str = Form("y4b44CckUkHECRcd"),
    checkin_hour: str = Form("15:00"),
    checkout_hour: str = Form("11:00"),
    maps_url: str = Form("https://maps.google.com/?q=Ege+Mahallesi+Isparta+Sokak+No:6/1+Daire:11+Dalaman+Muğla"),
    extension_enabled: str = Form("1"),
    extension_time: str = Form("20:00"),
    extension_price: str = Form("€75"),
    welcome_auto_send: str = Form("1"),
    welcome_auto_time: str = Form("15:00"),
    msg_new_booking: str = Form(...),
    msg_checkin: str = Form(...),
    msg_checkout: str = Form(...),
    msg_welcome: str = Form(...),
    msg_extension: str = Form(...),
    msg_discount_confirmed: str = Form(None)
):
    update_setting("suite_name", suite_name.strip())
    update_setting("phone_numbers", phone_numbers.strip())
    update_setting("morning_time", morning_time.strip())
    update_setting("ical_url", ical_url.strip())
    update_setting("wifi_name", wifi_name.strip())
    update_setting("wifi_password", wifi_password.strip())
    update_setting("checkin_hour", checkin_hour.strip())
    update_setting("checkout_hour", checkout_hour.strip())
    update_setting("maps_url", maps_url.strip())
    update_setting("extension_enabled", extension_enabled.strip())
    update_setting("extension_time", extension_time.strip())
    update_setting("extension_price", extension_price.strip())
    update_setting("welcome_auto_send", welcome_auto_send.strip())
    update_setting("welcome_auto_time", welcome_auto_time.strip())
    update_setting("msg_new_booking", msg_new_booking.strip())
    update_setting("msg_checkin", msg_checkin.strip())
    update_setting("msg_checkout", msg_checkout.strip())
    update_setting("msg_welcome", msg_welcome.strip())
    update_setting("msg_extension", msg_extension.strip())
    if msg_discount_confirmed:
        update_setting("msg_discount_confirmed", msg_discount_confirmed.strip())
    add_log("Ayarlar ve mesaj şablonları güncellendi.", "info")
    return JSONResponse({"status": "ok", "message": "Tüm ayarlar ve özel mesaj şablonları başarıyla kaydedildi!"})

@app.post("/api/reservation/send-extension")
async def send_extension_offer(uid: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT uid, checkin, checkout, guest_phone, suite_name, booker_country, language FROM reservations WHERE uid = ?", (uid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return JSONResponse({"status": "error", "message": "Rezervasyon bulunamadı."})
        
    uid_res, c_in, c_out, phone, r_suite, booker_country, guest_lang = row
    clean_phone = (phone or "").strip()
    if not clean_phone:
        conn.close()
        return JSONResponse({"status": "error", "message": "Lütfen önce misafirin telefon numarasını girip kaydediniz."})
        
    cfg = get_settings()
    suite_name = cfg.get("suite_name", r_suite or "Dalaman Airport Suite 11")
    ext_price = cfg.get("extension_price", "€75")
    
    try:
        c_out_dt = datetime.datetime.strptime(c_out, "%Y%m%d")
        tomorrow_fmt = c_out_dt.strftime("%d.%m.%Y")
    except Exception:
        tomorrow_fmt = format_date_str(c_out)
        
    lang = guest_lang or detect_guest_language(clean_phone, booker_country)
    params = {
        "suite_name": suite_name,
        "tomorrow_date": tomorrow_fmt,
        "extension_price": ext_price,
        "checkin": format_date_str(c_in),
        "checkout": format_date_str(c_out)
    }
    msg = get_multilingual_extension(lang, params)
    
    res = send_to_guest_or_sandbox(clean_phone, msg, lang, booker_country)
    if res.get("success"):
        cur.execute("UPDATE reservations SET notified_extension = 1 WHERE uid = ?", (uid,))
        conn.commit()
        conn.close()
        target_info = "🛡️ [GÜVENLİ TEST MODU] Test telefonuna iletildi" if res.get("sandbox") else f"Misafire iletildi ({clean_phone})"
        return JSONResponse({"status": "ok", "message": f"1 Gece uzatma teklifi ({lang.upper()}) {target_info}!"})
    else:
        conn.close()
        return JSONResponse({"status": "error", "message": f"Mesaj iletilemedi: {res.get('error', 'Bilinmeyen hata')}"})

@app.post("/api/reservation/send-welcome")
async def send_welcome_message(uid: str = Form(...), phone: str = Form(...)):
    phone = phone.strip()
    if not phone:
        return JSONResponse({"status": "error", "message": "Lütfen geçerli bir telefon numarası giriniz."})
        
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT checkin, checkout, suite_name, booker_country, language FROM reservations WHERE uid = ?", (uid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return JSONResponse({"status": "error", "message": "Rezervasyon bulunamadı."})
        
    c_in_raw, c_out_raw, r_suite, booker_country, guest_lang = row
    c_in = format_date_str(c_in_raw)
    c_out = format_date_str(c_out_raw)
    
    cfg = get_settings()
    suite_name = cfg.get("suite_name", r_suite or "Dalaman Airport Suite 11")
    wifi_name = cfg.get("wifi_name", "VODAFONE_9P1076")
    wifi_password = cfg.get("wifi_password", "y4b44CckUkHECRcd")
    checkin_hour = cfg.get("checkin_hour", "15:00")
    checkout_hour = cfg.get("checkout_hour", "11:00")
    maps_url = cfg.get("maps_url", "https://maps.google.com/?q=Ege+Mahallesi+Isparta+Sokak+No:6/1+Daire:11+Dalaman+Muğla")
    
    lang = guest_lang or detect_guest_language(phone, booker_country)
    params = {
        "suite_name": suite_name,
        "checkin": c_in,
        "checkout": c_out,
        "wifi_name": wifi_name,
        "wifi_password": wifi_password,
        "checkin_hour": checkin_hour,
        "checkout_hour": checkout_hour,
        "maps_url": maps_url
    }
    
    msg = get_multilingual_welcome(lang, params)
    
    res = send_to_guest_or_sandbox(phone, msg, lang, booker_country)
    if res.get("success"):
        cur.execute("UPDATE reservations SET guest_phone = ?, language = ?, notified_welcome = 1 WHERE uid = ?", (phone, lang, uid))
        conn.commit()
        conn.close()
        target_info = "🛡️ [GÜVENLİ TEST MODU] Test telefonuna iletildi" if res.get("sandbox") else f"Misafire iletildi ({phone})"
        return JSONResponse({"status": "ok", "message": f"Karşılama mesajı ({lang.upper()}) {target_info}!"})
    else:
        conn.close()
        return JSONResponse({"status": "error", "message": f"Mesaj iletilemedi: {res.get('error', 'Bilinmeyen hata')}"})

@app.post("/api/reservation/save-phone")
async def save_guest_phone(uid: str = Form(...), phone: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE reservations SET guest_phone = ? WHERE uid = ?", (phone.strip(), uid))
    conn.commit()
    conn.close()
    return JSONResponse({"status": "ok", "message": "Misafir numarası kaydedildi."})

@app.post("/api/test-whatsapp")
async def test_whatsapp():
    cfg = get_settings()
    suite_name = cfg.get("suite_name", "Dalaman Airport Suite")
    now_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    msg = f"✅ *TEST BİLDİRİMİ BAŞARILI!*\n\n🏨 *Tesis:* {suite_name}\n🕒 *Tarih/Saat:* {now_str}\n\nProxmox Booking Bot sisteminiz sorunsuz şekilde WhatsApp mesajı gönderebilmektedir."
    res = send_whatsapp(msg)
    if res:
        return JSONResponse({"status": "ok", "message": "WhatsApp test mesajı başarıyla gönderildi!"})
    else:
        return JSONResponse({"status": "error", "message": "WhatsApp mesajı gönderilemedi. Logları ve ayarları kontrol edin."})

@app.post("/api/reservation/resend-new-alert")
async def resend_new_alert(uid: str = Form(None)):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if uid and uid.strip():
        cur.execute("SELECT uid, checkin, checkout, suite_name FROM reservations WHERE uid = ?", (uid.strip(),))
    else:
        cur.execute("SELECT uid, checkin, checkout, suite_name FROM reservations ORDER BY created_at DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return JSONResponse({"status": "error", "message": "Veritabanında kayıtlı rezervasyon bulunamadı."})
        
    uid_res, c_in_raw, c_out_raw, r_suite = row
    c_in = format_date_str(c_in_raw)
    c_out = format_date_str(c_out_raw)
    
    cfg = get_settings()
    suite_name = cfg.get("suite_name", r_suite or "Dalaman Airport Suite 11")
    msg_tpl = cfg.get("msg_new_booking", "🛎 *YENİ BOOKING REZERVASYONU DÜŞTÜ!*\n\n🏨 *Tesis:* {suite_name}\n📅 *Giriş Tarihi:* {checkin}\n🚪 *Çıkış Tarihi:* {checkout}\n\nDetaylar Booking Extranet panelinize eklendi.")
    
    msg = msg_tpl.replace("{suite_name}", suite_name).replace("{checkin}", c_in).replace("{checkout}", c_out)
    res = send_whatsapp(msg)
    if res:
        add_log(f"Rezervasyon bildirimi manuel tetiklendi: {c_in} - {c_out}", "success")
        return JSONResponse({"status": "ok", "message": f"'{c_in} - {c_out}' rezervasyon bildirimi WhatsApp'a başarıyla gönderildi!"})
    else:
        return JSONResponse({"status": "error", "message": "WhatsApp mesajı iletilemedi. Logları ve WhatsApp bağlantısını kontrol edin."})

@app.post("/api/sync-now")
async def manual_sync():
    sync_calendar()
    check_daily_reminders()
    return JSONResponse({"status": "ok", "message": "Takvim hemen senkronize edildi ve kontroller yapıldı."})

@app.get("/api/whatsapp/status")
async def wa_gateway_status():
    try:
        r = requests.get("http://127.0.0.1:3000/status", timeout=2)
        return JSONResponse(r.json())
    except Exception:
        return JSONResponse({"status": "offline", "phone": None, "hasQr": False})

@app.get("/api/whatsapp/qr")
async def wa_gateway_qr():
    try:
        r = requests.get("http://127.0.0.1:3000/qr", timeout=2)
        return JSONResponse(r.json())
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})

@app.get("/api/whatsapp/qr-view", response_class=HTMLResponse)
async def wa_gateway_qr_view():
    try:
        r = requests.get("http://127.0.0.1:3000/qr-view", timeout=2)
        return HTMLResponse(content=r.text, status_code=r.status_code)
    except Exception as e:
        return HTMLResponse(content=f"<div style='font-family:sans-serif; text-align:center; padding:50px;'><h3>Gateway Bağlantı Hatası: {e}</h3></div>", status_code=500)

# -------------------------------------------------------------
# İKİ YÖNLÜ DİNLİYİCİ WEBHOOK (GUEST INBOUND WHATSAPP HOOK)
# -------------------------------------------------------------
@app.post("/api/webhook/whatsapp-inbound")
async def whatsapp_inbound_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Geçersiz JSON formatı"}, status_code=400)
        
    raw_phone = str(data.get("phone", "")).strip()
    text = str(data.get("text", "")).strip()
    if not raw_phone or not text:
        return JSONResponse({"status": "ignored", "message": "Numara veya metin eksik"})
        
    clean_phone = re.sub(r"\D", "", raw_phone)
    last_9 = clean_phone[-9:] if len(clean_phone) >= 9 else clean_phone
    normalized = text.lower().strip()
    
    add_log(f"Misafir WhatsApp yanıtı alındı (+{clean_phone}): {text}", "info")
    
    # 1. EVET / YES, DAS10 ve Web Sitesi İndirim Kontrolü (Opt-in Hook)
    is_website_lead = bool(re.search(r"\b(das10|dalamanairportsuites|sitenizden|web|site)\b", normalized, re.IGNORECASE))
    is_affirmative = bool(
        re.search(r"^(evet|yes|kabul|sure|ok|tamam|istiyorum|yaparız|yapariz|indirim)\b", normalized, re.IGNORECASE) or 
        re.search(r"\b(evet|yes|das10|das75)\b", normalized, re.IGNORECASE)
    )
    is_extension_reply = bool(re.search(r"\b(uzat|extend|stay|gece|night|ekstra)\b", normalized, re.IGNORECASE))
    
    cfg = get_settings()
    suite_name = cfg.get("suite_name", "Dalaman Airport Suite")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Misafiri telefonundan bul (son 9 hanesi ile eşleme)
    cur.execute("SELECT uid, checkin, checkout, guest_phone, has_discount FROM reservations WHERE guest_phone LIKE ? ORDER BY checkin DESC LIMIT 1", (f"%{last_9}%",))
    res_row = cur.fetchone()
    
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    intent_label = "Genel Mesaj"
    status_label = "Kayıt Edildi"
    guest_lang = detect_guest_language(clean_phone, "")

    if is_website_lead:
        intent_label = "Web Sitesi (%10 DAS10)"
        status_label = "Yöneticiye Bildirildi ✓"
        if res_row:
            uid, c_in, c_out, g_phone, has_disc = res_row
            cur.execute("UPDATE reservations SET has_discount = 1, discount_code = 'DAS10' WHERE uid = ?", (uid,))
            conn.commit()
            
        host_alert = (
            f"🎉 *MİSAFİR WEB SİTESİNDEN %10 İNDİRİMLİ (DAS10) İLE YAZDI!*\n\n"
            f"📱 *Misafir:* +{clean_phone}\n"
            f"💬 *Mesaj:* \"{text}\"\n"
            f"🏷 *Kupon:* DAS10 (%10 Doğrudan İndirim)\n\n"
            f"Misafir dalamanairportsuites.com sitenizdeki WhatsApp butonundan %10 indirimle talepte bulundu. Komisyonsuz doğrudan rezervasyon fırsatı!"
        )
        send_whatsapp(host_alert)
        add_log(f"Web sitesinden doğrudan rezervasyon talebi alındı (DAS10) -> +{clean_phone}", "success")
        
    elif is_affirmative:
        intent_label = "İndirim Onayı ('EVET')"
        status_label = "%10 Kupon (DAS10) İletildi ✓"
        if res_row:
            uid, c_in, c_out, g_phone, has_disc = res_row
            cur.execute("SELECT booker_country, language FROM reservations WHERE uid = ?", (uid,))
            b_info = cur.fetchone()
            if b_info:
                b_country, b_lang = b_info
                guest_lang = b_lang or detect_guest_language(clean_phone, b_country)
            cur.execute("UPDATE reservations SET has_discount = 1, discount_code = 'DAS10', language = ? WHERE uid = ?", (guest_lang, uid))
            conn.commit()
        else:
            guest_lang = detect_guest_language(clean_phone, "")
            
        params = {"suite_name": suite_name}
        disc_msg = get_multilingual_discount_confirmed(guest_lang, params)
        send_to_guest_or_sandbox(clean_phone, disc_msg, guest_lang, "")
            
        # Yöneticiye anında WhatsApp alarmı gönder
        host_alert = (
            f"🎁 *MİSAFİR 'EVET' DEDİ & %10 WEB İNDİRİMİ KAZANDI!*\n\n"
            f"📱 *Misafir:* +{clean_phone} ({guest_lang.upper()})\n"
            f"💬 *Mesaj:* \"{text}\"\n"
            f"🏷 *Kupon:* DAS10 (%10 Web İndirimi Aktif)\n\n"
            f"Misafir doğrudan iletişim ve %10 indirim onayını verdi. Misafire kendi dilinde indirim kuponu iletildi."
        )
        send_whatsapp(host_alert)
        add_log(f"Misafir 'EVET' dedi ve %10 indirim kazandı -> +{clean_phone} ({guest_lang.upper()})", "success")
        
    elif is_extension_reply:
        intent_label = "Konaklama Uzatma Yanıtı"
        status_label = "Yöneticiye İletildi ✓"
        host_alert = (
            f"🚨 *MİSAFİR UZATMA TEKLİFİNE YANIT VERDİ!*\n\n"
            f"📱 *Misafir:* +{clean_phone}\n"
            f"💬 *Mesaj:* \"{text}\"\n\n"
            f"Lütfen WhatsApp uygulamanızı açıp misafirle görüşmeyi tamamlayınız."
        )
        send_whatsapp(host_alert)
        add_log(f"Misafir uzatma teklifine yanıt verdi -> +{clean_phone}", "info")
        
    cur.execute("""
        INSERT INTO inbound_messages (timestamp, phone, text, intent, language, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (now_str, clean_phone, text, intent_label, guest_lang, status_label))
    conn.commit()
    conn.close()
    return JSONResponse({"status": "ok", "processed": True})

# -------------------------------------------------------------
# BOOKING CSV / TSV TOPLU İÇE AKTARMA (IMPORT)
# -------------------------------------------------------------
@app.post("/api/reservation/import-csv")
async def import_booking_csv(file: UploadFile = File(...)):
    if not file.filename:
        return JSONResponse({"status": "error", "message": "Lütfen bir CSV veya TSV dosyası seçiniz."})
        
    content_bytes = await file.read()
    try:
        content_str = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content_str = content_bytes.decode("windows-1254")
        except UnicodeDecodeError:
            content_str = content_bytes.decode("latin-1")
            
    first_line = content_str.split("\n")[0] if "\n" in content_str else content_str
    delimiter = "\t" if "\t" in first_line else (";" if ";" in first_line else ",")
    
    reader = csv.DictReader(io.StringIO(content_str), delimiter=delimiter)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cfg = get_settings()
    suite_name = cfg.get("suite_name", "Dalaman Airport Suite 11")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    matched_count = 0
    created_count = 0
    total_processed = 0
    
    for row in reader:
        checkout_val = (row.get("Check-out") or row.get("Checkout") or row.get("Çıkış") or row.get("Cikis") or "").strip()
        phone_val = (row.get("Phone number") or row.get("Phone") or row.get("Telefon") or row.get("Cep") or "").strip()
        duration_val = (row.get("Duration (nights)") or row.get("Nights") or row.get("Gece") or "1").strip()
        country_val = (row.get("Booker country") or row.get("Country") or row.get("Ülke") or "").strip().lower()
        
        if not checkout_val or not phone_val:
            continue
            
        norm_phone = normalize_phone_number(phone_val)
        if not norm_phone:
            continue
            
        guest_lang = detect_guest_language(norm_phone, country_val)
        total_processed += 1
        
        c_out_date = None
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y%m%d"):
            try:
                c_out_date = datetime.datetime.strptime(checkout_val.split()[0], fmt).date()
                break
            except Exception:
                pass
                
        if not c_out_date:
            continue
            
        try:
            dur_int = int(duration_val)
        except Exception:
            dur_int = 1
            
        c_in_date = c_out_date - datetime.timedelta(days=dur_int)
        c_out_str = c_out_date.strftime("%Y%m%d")
        c_in_str = c_in_date.strftime("%Y%m%d")
        
        cur.execute("SELECT uid, guest_phone FROM reservations WHERE checkout = ? AND (checkin = ? OR checkin = '')", (c_out_str, c_in_str))
        found = cur.fetchone()
        
        if found:
            cur.execute("UPDATE reservations SET guest_phone = ?, booker_country = ?, language = ? WHERE uid = ?", (norm_phone, country_val, guest_lang, found[0]))
            matched_count += 1
        else:
            new_uid = f"booking-csv-{c_in_str}-{c_out_str}-{norm_phone[-6:]}"
            cur.execute("""
                INSERT OR IGNORE INTO reservations (uid, checkin, checkout, suite_name, notified_new, guest_phone, created_at, booker_country, language)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
            """, (new_uid, c_in_str, c_out_str, suite_name, norm_phone, now_str, country_val, guest_lang))
            created_count += 1
            
    conn.commit()
    conn.close()
    
    add_log(f"Booking dosyası içe aktarıldı: {matched_count} rezervasyon eşleştirildi, {created_count} yeni misafir kaydedildi (Toplam {total_processed}).", "success")
    return JSONResponse({
        "status": "ok",
        "matched": matched_count,
        "created": created_count,
        "total": total_processed,
        "message": f"İşlem Tamamlandı: {matched_count} rezervasyonun telefonu ve dili güncellendi, {created_count} yeni misafir rehbere eklendi (Toplam {total_processed})."
    })

# -------------------------------------------------------------
# MEVSİMSEL VE UÇUŞ KAMPANYALARI ("Hava Sıcak Gelin / Biletler İndi")
# -------------------------------------------------------------
CAMPAIGN_PRESETS = [
    {
        "id": "autumn",
        "title": "🍂 Sonbahar: Dalaman'da Deniz Hala Sıcacık & Ucuz Uçuşlar (Ekim - Kasım)",
        "season": "autumn",
        "template": (
            "🌴 *Dalaman'da Deniz Hala Sıcacık! (Autumn Secret Season)* ☀️\n\n"
            "Dear Guest,\n"
            "We hope you have wonderful memories from your stay at {suite_name}!\n\n"
            "Did you know that Autumn is the most relaxing season in Dalaman? The sea temperature is still a warm 24°C, beaches are peaceful, and flights from Europe & Istanbul are currently at bargain rates:\n"
            "✈️ *Dalaman Flight Deals:* https://www.google.com/travel/flights?q=flights+to+DLM\n\n"
            "🎁 As our previous guest, we'd love to offer you a direct booking special with *%15 DISCOUNT* (No platform fees + Promo Code: *AUTUMN15*).\n\n"
            "Just reply to this message anytime to book your sunny autumn escape! 🌊"
        )
    },
    {
        "id": "winter",
        "title": "❄️ Kış & Termal: Sultaniye Kaplıcaları & Erken Rezervasyon (Aralık - Şubat)",
        "season": "winter",
        "template": (
            "♨️ *Warm Winter Escape & Early Bird Special!* ❄️\n\n"
            "Dear Guest,\n"
            "Escape the winter chill! Just a short drive from {suite_name}, the ancient Sultaniye Thermal Springs are naturally bubbling at 39°C all year round.\n\n"
            "✈️ *Flights to Dalaman:* https://www.google.com/travel/flights?q=flights+to+DLM\n\n"
            "🌴 *Summer 2027 Early Bird:* Secure your next holiday dates now with promo code *EARLY2027* for *%15 OFF* on direct bookings.\n\n"
            "Reply to this chat anytime to check dates. We'd love to welcome you back!"
        )
    },
    {
        "id": "spring",
        "title": "🌸 İlkbahar: Likya Yolu & Uçuş Sezonu Başladı (Mart - Mayıs)",
        "season": "spring",
        "template": (
            "🌸 *Spring in Dalaman & Lycian Trail Walks!* 🥾\n\n"
            "Dear Guest,\n"
            "Spring has arrived in Dalaman! The orange blossoms are blooming and the famous Lycian Way hiking routes are at their absolute prime.\n\n"
            "Direct international flight routes to Dalaman (DLM) have officially resumed for the season:\n"
            "✈️ *Flight Schedules & Deals:* https://www.google.com/travel/flights?q=flights+to+DLM\n\n"
            "Book your spring escape directly with us using code *SPRING10* for *%10 DISCOUNT*.\n\n"
            "Feel free to reply right here on WhatsApp to plan your visit! 🌺"
        )
    },
    {
        "id": "summer",
        "title": "☀️ Yaz: Sarıgerme Kumsalları & Göcek Koyları (Haziran - Ağustos)",
        "season": "summer",
        "template": (
            "☀️ *Sun, Sea & Secret Bays in Dalaman!* 🏖️\n\n"
            "Dear Guest,\n"
            "The turquoise waters of Sarıgerme Beach and Göcek 12 Islands are waiting for you!\n\n"
            "Avoid middleman booking commissions and book directly with {suite_name} for guaranteed best rates + complimentary airport perks on weekly stays.\n\n"
            "✈️ *Check Flight Options:* https://www.google.com/travel/flights?q=flights+to+DLM\n\n"
            "Reply to this message to check our availability. Looking forward to hosting you again!"
        )
    }
]

@app.get("/api/campaign/presets")
async def get_campaign_presets():
    cfg = get_settings()
    suite_name = cfg.get("suite_name", "Dalaman Airport Suite 11")
    presets = []
    for p in CAMPAIGN_PRESETS:
        presets.append({
            "id": p["id"],
            "title": p["title"],
            "season": p["season"],
            "template": p["template"].replace("{suite_name}", suite_name)
        })
    return JSONResponse(presets)

@app.post("/api/campaign/send")
async def send_campaign(
    target: str = Form("opted_in"),
    custom_phone: str = Form(None),
    message: str = Form(...)
):
    message = message.strip()
    if not message:
        return JSONResponse({"status": "error", "message": "Kampanya mesajı boş olamaz."})
        
    cfg = get_settings()
    sandbox_mode = cfg.get("sandbox_mode", "1") == "1"
    test_phone = cfg.get("test_phone", "+905423674599")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    if custom_phone and custom_phone.strip():
        recipients = [normalize_phone_number(custom_phone)]
    elif target == "all_phones":
        cur.execute("SELECT DISTINCT guest_phone FROM reservations WHERE guest_phone != '' AND guest_phone IS NOT NULL")
        recipients = [normalize_phone_number(r[0]) for r in cur.fetchall() if r[0]]
    else: # opted_in or has_discount
        cur.execute("SELECT DISTINCT guest_phone FROM reservations WHERE (has_discount = 1 OR notified_welcome = 1) AND guest_phone != '' AND guest_phone IS NOT NULL")
        recipients = [normalize_phone_number(r[0]) for r in cur.fetchall() if r[0]]
        
    conn.close()
    recipients = list(set([p for p in recipients if p and len(p) >= 8]))
    
    if not recipients:
        return JSONResponse({"status": "error", "message": "Seçilen filtreye uygun kayıtlı misafir telefon numarası bulunamadı."})
        
    if sandbox_mode:
        # GÜVENLİ TEST MODU: Gerçek misafirlere ASLA gitmez! Sadece test_phone'a önizleme gider!
        test_wrapper = (
            f"🧪 *[GÜVENLİ TEST MODU - KAMPANYA ÖNİZLEMESİ]*\n"
            f"👥 *Hedef Kitle:* {len(recipients)} misafir seçildi\n"
            f"📱 *İletilen Test Telefonu:* {test_phone}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{message}"
        )
        local_url = "http://127.0.0.1:3000/send"
        try:
            r = requests.post(local_url, json={"phone": test_phone, "message": test_wrapper}, timeout=15)
            if r.status_code == 200:
                add_log(f"Kampanya test önizlemesi yöneticinin telefonuna iletildi ({test_phone}) [{len(recipients)} misafir hedefli]", "success")
                return JSONResponse({
                    "status": "ok",
                    "message": f"🛡️ GÜVENLİ TEST MODU DEVREDE: Gerçek misafirler rahatsız edilmedi! Kampanyanın birebir önizlemesi telefonunuza ({test_phone}) iletildi. Gerçek gönderim için üst bardan 'Canlı Mod'a geçebilirsiniz."
                })
            else:
                return JSONResponse({"status": "error", "message": f"WhatsApp hatası: {r.text}"})
        except Exception as e:
            return JSONResponse({"status": "error", "message": f"Bağlantı hatası: {str(e)}"})
            
    # CANLI MOD: Gerçek alıcılara gider
    def run_campaign(phone_list, text_body):
        success = 0
        local_url = "http://127.0.0.1:3000/send"
        add_log(f"CANLI Mevsimsel kampanya gönderimi başlatıldı ({len(phone_list)} alıcı, 10sn aralıklarla)...", "info")
        for p in phone_list:
            try:
                r = requests.post(local_url, json={"phone": p, "message": text_body}, timeout=15)
                if r.status_code == 200:
                    success += 1
                    add_log(f"Kampanya iletildi -> {p}", "success")
                else:
                    add_log(f"Kampanya iletilemedi ({p}): {r.text}", "error")
            except Exception as e:
                add_log(f"Kampanya ağ hatası ({p}): {str(e)}", "error")
            time.sleep(10) # 10 sn güvenli anti-spam bekleme
        add_log(f"Kampanya tamamlandı: {success}/{len(phone_list)} alıcıya başarıyla ulaştı.", "success")
        
    t = threading.Thread(target=run_campaign, args=(recipients, message), daemon=True)
    t.start()
    
    return JSONResponse({
        "status": "ok", 
        "message": f"Kampanya {len(recipients)} kişiye 10 saniyelik güvenli bekleme aralıklarıyla gönderilmek üzere arka planda başlatıldı! İlerlemeyi Sistem Olay Günlüğü'nden anlık izleyebilirsiniz."
    })

# -------------------------------------------------------------
# GÜVENLİ SANDBOX (TEST MODU) & ÇOK DİLLİ TEST LABORATUVARI
# -------------------------------------------------------------
@app.post("/api/sandbox/toggle")
async def toggle_sandbox():
    cfg = get_settings()
    curr = cfg.get("sandbox_mode", "1")
    new_val = "0" if curr == "1" else "1"
    update_setting("sandbox_mode", new_val)
    mode_name = "🛡️ GÜVENLİ TEST MODU (AÇIK - Tüm mesajlar +905423674599 numarasına gider)" if new_val == "1" else "🔴 CANLI GÖNDERİM MODU (DİKKAT - Gerçek misafirlere gider!)"
    add_log(f"Sistem Modu Değiştirildi: {mode_name}", "warning" if new_val == "0" else "info")
    return JSONResponse({"status": "ok", "sandbox_mode": new_val, "message": mode_name})

@app.get("/api/sandbox/status")
async def get_sandbox_status():
    cfg = get_settings()
    return JSONResponse({
        "sandbox_mode": cfg.get("sandbox_mode", "1"),
        "test_phone": cfg.get("test_phone", "+905423674599")
    })

@app.post("/api/sandbox/test-sample")
async def test_sandbox_sample(msg_type: str = Form(...), lang: str = Form("de")):
    cfg = get_settings()
    suite_name = cfg.get("suite_name", "Dalaman Airport Suite 11")
    wifi_name = cfg.get("wifi_name", "VODAFONE_9P1076")
    wifi_password = cfg.get("wifi_password", "y4b44CckUkHECRcd")
    checkin_hour = cfg.get("checkin_hour", "15:00")
    checkout_hour = cfg.get("checkout_hour", "11:00")
    maps_url = cfg.get("maps_url", "https://maps.google.com/?q=Ege+Mahallesi+Isparta+Sokak+No:6/1+Daire:11+Dalaman+Muğla")
    ext_price = cfg.get("extension_price", "€75")
    test_phone = cfg.get("test_phone", "+905423674599")
    
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    
    params = {
        "suite_name": suite_name,
        "checkin": today.strftime("%d.%m.%Y"),
        "checkout": tomorrow.strftime("%d.%m.%Y"),
        "tomorrow_date": tomorrow.strftime("%d.%m.%Y"),
        "wifi_name": wifi_name,
        "wifi_password": wifi_password,
        "checkin_hour": checkin_hour,
        "checkout_hour": checkout_hour,
        "maps_url": maps_url,
        "extension_price": ext_price
    }
    
    lang_names = {"de": "🇩🇪 Almanca", "ru": "🇷🇺 Rusça", "tr": "🇹🇷 Türkçe", "en": "🇬🇧 İngilizce"}
    lang_label = lang_names.get(lang, lang.upper())
    
    if msg_type == "welcome":
        content = get_multilingual_welcome(lang, params)
        title = f"Karşılama & Wi-Fi ({lang_label})"
    elif msg_type == "extension":
        content = get_multilingual_extension(lang, params)
        title = f"1 Gece Uzatma {ext_price} ({lang_label})"
    elif msg_type == "discount":
        content = get_multilingual_discount_confirmed(lang, params)
        title = f"%10 Web İndirim Kuponu DAS10 ({lang_label})"
    else:
        content = CAMPAIGN_PRESETS[0]["template"].replace("{suite_name}", suite_name)
        title = f"Mevsimsel Kampanya Önizlemesi ({lang_label})"
        
    sample_phone = "+4916091280550" if lang == "de" else ("+79123456789" if lang == "ru" else ("+905423674599" if lang == "tr" else "+447911123456"))
    
    test_wrapper = (
        f"🧪 *[LABORATUVAR TESTİ / {title}]*\n"
        f"👤 *Hedef Misafir Örneği:* {sample_phone} ({lang_label})\n"
        f"📱 *İletilen Test Telefonu:* {test_phone}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{content}"
    )
    
    local_url = "http://127.0.0.1:3000/send"
    try:
        r = requests.post(local_url, json={"phone": test_phone, "message": test_wrapper}, timeout=15)
        if r.status_code == 200:
            add_log(f"Laboratuvar testi başarıyla iletildi -> {test_phone} ({title})", "success")
            return JSONResponse({"status": "ok", "message": f"{title} testi telefonunuza ({test_phone}) başarıyla gönderildi!"})
        else:
            return JSONResponse({"status": "error", "message": f"WhatsApp hatası: {r.text}"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Bağlantı hatası: {str(e)}"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
