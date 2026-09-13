import os
import re
import sqlite3
import datetime
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
            created_at TEXT
        )
    """)
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
        "ultramsg_instance": os.getenv("ULTRAMSG_INSTANCE", ""),
        "ultramsg_token": os.getenv("ULTRAMSG_TOKEN", ""),
        "phone_numbers": os.getenv("PHONE_NUMBERS", ""),
        "morning_time": "09:00",
        "suite_name": "Dalaman Airport Suite 11",
        "msg_new_booking": "🛎 *YENİ BOOKING REZERVASYONU DÜŞTÜ!*\n\n🏨 *Tesis:* {suite_name}\n📅 *Giriş Tarihi:* {checkin}\n🚪 *Çıkış Tarihi:* {checkout}\n\nDetaylar Booking Extranet panelinize eklendi.",
        "msg_checkin": "🏨 *BUGÜN GİRİŞ (CHECK-IN) GÜNÜ!*\n\n🏨 *Tesis:* {suite_name}\n📅 *Giriş:* Bugün ({checkin})\n🚪 *Çıkış:* {checkout}\n\n🔑 Oda hazırlığını ve anahtar teslimini yapınız.\n🚨 *DİKKAT:* KBS / Polis Sistemine misafir kimlik kaydını girmeyi unutmayınız!",
        "msg_checkout": "🧹 *BUGÜN CHECK-OUT (ÇIKIŞ) GÜNÜ!*\n\n🏨 *Tesis:* {suite_name}\n🚪 *Çıkış:* Bugün ({checkout})\n📅 *Giriş Tarihi:* {checkin}\n\n🧹 Oda temizlik hazırlıklarını başlatınız.\n🚨 *DİKKAT:* KBS / Polis Sisteminden misafir çıkışını vermeyi unutmayınız!"
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
        sent_local = False
        # 1. Öncelik: Kendi Yerel Baileys Gateway'imiz (Sıfır Ücret & Kalıcı)
        try:
            r = requests.post(local_gateway_url, json={"phone": phone, "message": body_text}, timeout=10)
            if r.status_code == 200:
                success_count += 1
                sent_local = True
                add_log(f"WhatsApp gönderildi (Yerel Gateway) -> {phone}", "success")
            else:
                err_data = r.text
                try:
                    err_data = r.json().get("error", err_data)
                except:
                    pass
                add_log(f"Yerel Gateway ({phone}): {err_data}", "info")
        except Exception:
            pass
            
        # 2. Öncelik: Eğer Yerel Gateway bağlı değilse ve UltraMsg ayarları varsa yedek olarak dene
        if not sent_local:
            instance = cfg.get("ultramsg_instance")
            token = cfg.get("ultramsg_token")
            if instance and token:
                url = f"https://api.ultramsg.com/{instance}/messages/chat"
                payload = {
                    "token": token,
                    "to": phone,
                    "body": body_text,
                    "priority": "10"
                }
                try:
                    r2 = requests.post(url, data=payload, timeout=15)
                    if r2.status_code == 200:
                        success_count += 1
                        add_log(f"WhatsApp gönderildi (UltraMsg Yedek) -> {phone}", "success")
                    else:
                        add_log(f"UltraMsg hata ({phone}): {r2.text}", "error")
                except Exception as e2:
                    add_log(f"UltraMsg bağlantı hatası ({phone}): {str(e2)}", "error")
            else:
                add_log(f"WhatsApp gönderilemedi ({phone}): Yerel Gateway bağlı değil! Lütfen web panelinden QR kodu okutun.", "error")
            
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

scheduler = BackgroundScheduler()

def scheduled_job():
    cfg = get_settings()
    morning_time = cfg.get("morning_time", "09:00")
    current_hm = datetime.datetime.now().strftime("%H:%M")
    
    sync_calendar()
    
    if current_hm == morning_time:
        check_daily_reminders()

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
    
    cur.execute("SELECT uid, checkin, checkout, notified_checkout FROM reservations WHERE checkout = ?", (today_str,))
    today_checkouts = [{"uid": r[0], "checkin": format_date_str(r[1]), "checkout": format_date_str(r[2]), "notified": r[3]} for r in cur.fetchall()]
    
    cur.execute("SELECT uid, checkin, checkout, notified_checkin FROM reservations WHERE checkin = ?", (today_str,))
    today_checkins = [{"uid": r[0], "checkin": format_date_str(r[1]), "checkout": format_date_str(r[2]), "notified": r[3]} for r in cur.fetchall()]
    
    cur.execute("SELECT uid, checkin, checkout, created_at, notified_checkout FROM reservations ORDER BY checkin DESC LIMIT 50")
    all_res = []
    current_hour = datetime.datetime.now().hour
    
    for r in cur.fetchall():
        uid, c_in, c_out, created_at, notif_out = r
        
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
            "uid": uid[:15] + "...",
            "checkin": format_date_str(c_in),
            "checkout": format_date_str(c_out),
            "status": status,
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
    ultramsg_instance: str = Form(...),
    ultramsg_token: str = Form(...),
    msg_new_booking: str = Form(...),
    msg_checkin: str = Form(...),
    msg_checkout: str = Form(...)
):
    update_setting("suite_name", suite_name.strip())
    update_setting("phone_numbers", phone_numbers.strip())
    update_setting("morning_time", morning_time.strip())
    update_setting("ical_url", ical_url.strip())
    update_setting("ultramsg_instance", ultramsg_instance.strip())
    update_setting("ultramsg_token", ultramsg_token.strip())
    update_setting("msg_new_booking", msg_new_booking.strip())
    update_setting("msg_checkin", msg_checkin.strip())
    update_setting("msg_checkout", msg_checkout.strip())
    add_log("Ayarlar ve mesaj şablonları güncellendi.", "info")
    return JSONResponse({"status": "ok", "message": "Tüm ayarlar ve özel mesaj şablonları başarıyla kaydedildi!"})

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
