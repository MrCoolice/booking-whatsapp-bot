import os
import re
import sqlite3
import datetime
import time
import requests
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form
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
            created_at TEXT
        )
    """)
    # Migration
    try:
        cur.execute("ALTER TABLE reservations ADD COLUMN guest_phone TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE reservations ADD COLUMN notified_welcome INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE reservations ADD COLUMN notified_extension INTEGER DEFAULT 0")
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
    
    defaults = {
        "ical_url": os.getenv("ICAL_URL", ""),
        "phone_numbers": os.getenv("PHONE_NUMBERS", ""),
        "morning_time": "09:00",
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
            "🚗 *Location:* Only 10 mins from Dalaman International Airport (DLM).\n"
            "📞 If you need anything, please contact us on WhatsApp: +90 542 367 45 99.\n\n"
            "✨ *We wish you a wonderful and relaxing stay!*\n*(Keyifli bir konaklama dileriz!)*"
        )
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
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

def format_date_str(d_str):
    try:
        dt = datetime.datetime.strptime(d_str, "%Y%m%d")
        return dt.strftime("%d.%m.%Y")
    except:
        return d_str

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
        SELECT uid, checkin, checkout, guest_phone 
        FROM reservations 
        WHERE checkout = ? AND guest_phone != '' AND notified_extension = 0
    """, (tomorrow_str,))
    candidates = cur.fetchall()
    
    local_gateway_url = "http://127.0.0.1:3000/send"
    for r in candidates:
        uid, c_in, c_out, phone = r
        clean_phone = (phone or "").strip()
        if not clean_phone:
            continue
            
        msg = (ext_tpl
               .replace("{suite_name}", suite_name)
               .replace("{tomorrow_date}", tomorrow_fmt)
               .replace("{extension_price}", ext_price)
               .replace("{checkin}", format_date_str(c_in))
               .replace("{checkout}", format_date_str(c_out)))
               
        try:
            r_post = requests.post(local_gateway_url, json={"phone": clean_phone, "message": msg}, timeout=15)
            if r_post.status_code == 200:
                cur.execute("UPDATE reservations SET notified_extension = 1 WHERE uid = ?", (uid,))
                conn.commit()
                add_log(f"Misafire 1 gece uzatma teklifi iletildi -> {clean_phone} ({tomorrow_fmt} - {ext_price})", "success")
            else:
                add_log(f"Uzatma teklifi iletilemedi ({clean_phone}): {r_post.text}", "error")
        except Exception as e:
            add_log(f"Uzatma teklifi baglanti hatasi ({clean_phone}): {str(e)}", "error")
        time.sleep(1.5)
        
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
    
    cur.execute("SELECT uid, checkin, checkout, created_at, notified_checkout, guest_phone, notified_welcome, notified_extension FROM reservations ORDER BY checkin DESC LIMIT 50")
    all_res = []
    current_hour = datetime.datetime.now().hour
    
    for r in cur.fetchall():
        uid, c_in, c_out, created_at, notif_out, guest_phone, notif_welcome, notif_ext = r
        
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
            
        all_res.append({
            "uid": uid,
            "short_uid": uid[:15] + "...",
            "checkin": format_date_str(c_in),
            "checkout": format_date_str(c_out),
            "status": status,
            "guest_phone": guest_phone or "",
            "notified_welcome": notif_welcome,
            "notified_extension": notif_ext,
            "created_at": created_at
        })
        
    cur.execute("SELECT timestamp, message, status FROM logs ORDER BY id DESC LIMIT 15")
    logs = [{"time": r[0], "msg": r[1], "status": r[2]} for r in cur.fetchall()]
    
    conn.close()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "config": cfg,
        "today_display": today_display,
        "today_checkouts": today_checkouts,
        "today_checkins": today_checkins,
        "reservations": all_res,
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
    msg_new_booking: str = Form(...),
    msg_checkin: str = Form(...),
    msg_checkout: str = Form(...),
    msg_welcome: str = Form(...),
    msg_extension: str = Form(...)
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
    update_setting("msg_new_booking", msg_new_booking.strip())
    update_setting("msg_checkin", msg_checkin.strip())
    update_setting("msg_checkout", msg_checkout.strip())
    update_setting("msg_welcome", msg_welcome.strip())
    update_setting("msg_extension", msg_extension.strip())
    add_log("Ayarlar ve mesaj şablonları güncellendi.", "info")
    return JSONResponse({"status": "ok", "message": "Tüm ayarlar ve özel mesaj şablonları başarıyla kaydedildi!"})

@app.post("/api/reservation/send-extension")
async def send_extension_offer(uid: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT uid, checkin, checkout, guest_phone, suite_name FROM reservations WHERE uid = ?", (uid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return JSONResponse({"status": "error", "message": "Rezervasyon bulunamadı."})
        
    uid_res, c_in, c_out, phone, r_suite = row
    clean_phone = (phone or "").strip()
    if not clean_phone:
        conn.close()
        return JSONResponse({"status": "error", "message": "Lütfen önce misafirin telefon numarasını girip kaydediniz."})
        
    cfg = get_settings()
    suite_name = cfg.get("suite_name", r_suite or "Dalaman Airport Suite 11")
    ext_price = cfg.get("extension_price", "€75")
    ext_tpl = cfg.get("msg_extension", "")
    
    try:
        c_out_dt = datetime.datetime.strptime(c_out, "%Y%m%d")
        tomorrow_fmt = c_out_dt.strftime("%d.%m.%Y")
    except Exception:
        tomorrow_fmt = format_date_str(c_out)
        
    msg = (ext_tpl
           .replace("{suite_name}", suite_name)
           .replace("{tomorrow_date}", tomorrow_fmt)
           .replace("{extension_price}", ext_price)
           .replace("{checkin}", format_date_str(c_in))
           .replace("{checkout}", format_date_str(c_out)))
           
    local_gateway_url = "http://127.0.0.1:3000/send"
    try:
        r_post = requests.post(local_gateway_url, json={"phone": clean_phone, "message": msg}, timeout=15)
        if r_post.status_code == 200:
            cur.execute("UPDATE reservations SET notified_extension = 1 WHERE uid = ?", (uid,))
            conn.commit()
            conn.close()
            add_log(f"Misafire manuel uzatma teklifi iletildi -> {clean_phone} ({tomorrow_fmt} - {ext_price})", "success")
            return JSONResponse({"status": "ok", "message": f"1 Gece uzatma teklifi ({clean_phone}) numarasına başarıyla iletildi!"})
        else:
            conn.close()
            return JSONResponse({"status": "error", "message": f"Mesaj iletilemedi: {r_post.text}"})
    except Exception as e:
        conn.close()
        return JSONResponse({"status": "error", "message": f"Bağlantı hatası: {str(e)}"})

@app.post("/api/reservation/send-welcome")
async def send_welcome_message(uid: str = Form(...), phone: str = Form(...)):
    phone = phone.strip()
    if not phone:
        return JSONResponse({"status": "error", "message": "Lütfen geçerli bir telefon numarası giriniz."})
        
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT checkin, checkout, suite_name FROM reservations WHERE uid = ?", (uid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return JSONResponse({"status": "error", "message": "Rezervasyon bulunamadı."})
        
    c_in_raw, c_out_raw, r_suite = row
    c_in = format_date_str(c_in_raw)
    c_out = format_date_str(c_out_raw)
    
    cfg = get_settings()
    suite_name = cfg.get("suite_name", r_suite or "Dalaman Airport Suite 11")
    wifi_name = cfg.get("wifi_name", "VODAFONE_9P1076")
    wifi_password = cfg.get("wifi_password", "y4b44CckUkHECRcd")
    checkin_hour = cfg.get("checkin_hour", "15:00")
    checkout_hour = cfg.get("checkout_hour", "11:00")
    maps_url = cfg.get("maps_url", "https://maps.google.com/?q=Ege+Mahallesi+Isparta+Sokak+No:6/1+Daire:11+Dalaman+Muğla")
    welcome_tpl = cfg.get("msg_welcome", "")
    
    msg = (welcome_tpl
           .replace("{suite_name}", suite_name)
           .replace("{checkin}", c_in)
           .replace("{checkout}", c_out)
           .replace("{wifi_name}", wifi_name)
           .replace("{wifi_password}", wifi_password)
           .replace("{checkin_hour}", checkin_hour)
           .replace("{checkout_hour}", checkout_hour)
           .replace("{maps_url}", maps_url))
           
    local_gateway_url = "http://127.0.0.1:3000/send"
    try:
        r = requests.post(local_gateway_url, json={"phone": phone, "message": msg}, timeout=15)
        if r.status_code == 200:
            cur.execute("UPDATE reservations SET guest_phone = ?, notified_welcome = 1 WHERE uid = ?", (phone, uid))
            conn.commit()
            conn.close()
            add_log(f"Misafire karşılama mesajı iletildi -> {phone} ({c_in} - {c_out})", "success")
            return JSONResponse({"status": "ok", "message": f"Karşılama mesajı misafire ({phone}) başarıyla iletildi!"})
        else:
            conn.close()
            err_text = r.text
            try:
                err_text = r.json().get("error", err_text)
            except Exception:
                pass
            add_log(f"Misafir karşılama hatası ({phone}): {err_text}", "error")
            return JSONResponse({"status": "error", "message": f"Mesaj iletilemedi: {err_text}"})
    except Exception as e:
        conn.close()
        add_log(f"Misafir karşılama bağlantı hatası ({phone}): {str(e)}", "error")
        return JSONResponse({"status": "error", "message": f"Bağlantı hatası: {str(e)}"})

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
