# ğŸ¨ Booking.com WhatsApp & Legal Compliance (KBS) Automation Bot (Self-Hosted)

> ğŸŒ **Language / Dil:** [ğŸ‡¬ğŸ‡§ English](#-english) | [ğŸ‡¹ğŸ‡· TÃ¼rkÃ§e](#-tÃ¼rkÃ§e)  
> *English documentation is at the top. TÃ¼rkÃ§e aÃ§Ä±klamalar sayfanÄ±n alt kÄ±smÄ±nda yer almaktadÄ±r.*

---

# ğŸ‡¬ğŸ‡§ English

A 100% **self-hosted**, lightweight, and automated bot designed for hotels, boutique suites, villas, and short-term rentals (Booking.com). It monitors your reservations 24/7 via iCal, notifies you instantly on WhatsApp for new bookings, sends morning Check-in / Check-out reminders with legal police/identity reporting compliance notices (**Turkish KBS / Police Notification System**), and provides **1-Click Guest Welcome & Self Check-in WhatsApp Automation** (Wi-Fi, directions, and hours).

Includes a built-in **100% Free Self-Hosted WhatsApp Web Gateway (Baileys)**: no paid third-party APIs (UltraMsg, Twilio, etc.), no trial expirations, and zero monthly subscriptions!

---

## ğŸŒŸ Key Features

- ğŸ†“ **100% Free Self-Hosted WhatsApp Gateway:** Powered by Baileys & Node.js running directly on your server. Pair your phone once via QR code directly in the web UI. No paid subscriptions, no per-message fees!
- ğŸ› **Instant Booking Alerts:** Automatically polls the Booking.com iCal feed every 2 minutes. When a new reservation arrives, it sends an immediate WhatsApp notification to the host, reception, or staff group.
- ğŸš¨ **Legal Compliance & Police (KBS) Reminders:** 
  - Morning Check-in alert (`09:00` by default): Reminds staff of key handover and mandatory police guest registration.
  - Morning Check-out alert: Reminds staff to start housekeeping and file the police check-out notification.
- ğŸ”‘ **Guest Welcome & Self Check-in Dispatcher:**
  - One-click personalized bilingual (English & Turkish) WhatsApp message to incoming guests containing Wi-Fi credentials, check-in (`15:00`) / check-out (`11:00`) hours, and Google Maps pin.
- ğŸŒ **Modern & Responsive Web Dashboard:** Accessible at `http://<IP>:8000`, built with Tailwind CSS, showing today's arrivals, departures, live logs, active reservations, and an interactive WhatsApp QR pairing modal.
- ğŸ•’ **Smart Status Transition:** On check-out day, the reservation badge shows *"Check-out Today"* before 11:00 AM, and automatically turns into *"Checked Out"* after standard check-out time (11:00 AM).
- ğŸ“± **Multi-Number & WhatsApp Group Support:** Delivers alerts to multiple comma-separated phone numbers (`+905...,+905...`) or directly to a shared WhatsApp staff group.
- âœï¸ **Customizable Message Templates:** Edit WhatsApp notification templates (`{suite_name}`, `{checkin}`, `{checkout}`, `{wifi_name}`, `{wifi_password}`, `{maps_url}`) directly from the web dashboard with a single click.
- ğŸ’¾ **Persistent SQLite Database:** Retains state across server reboots, ensuring no duplicate messages are ever sent.
- ğŸš€ **Zero Cloud Subscription Fees:** Runs entirely on your own local server (Proxmox LXC, Raspberry Pi, or Linux VPS) with no monthly quotas (unlike Make.com or Zapier).

---

## ğŸ—ï¸ Architecture Diagram

```mermaid
graph TD
    A[Booking.com iCal Calendar] -->|Polling Every 2 Minutes| B(FastAPI Python Service :8000)
    B -->|State & Reservation DB| C[(SQLite Database)]
    B -->|Outgoing Messages| D[Local Baileys WhatsApp Gateway :3000]
    D -->|Host & Staff Alerts| E[Host & Staff WhatsApp Phones]
    D -->|Guest Welcome Messages| F[Incoming Guest WhatsApp Phone]
    G[Web Dashboard UI :8000] <-->|Interactive QR Code Modal| D
    G <-->|Management & Live Logs| B
```

---

## ğŸš€ Quick Start & Installation

### Step 1: Create a Proxmox LXC Container (1 Minute)
From your Proxmox web interface (`https://<proxmox-ip>:8006`), click **"Create CT"**:
- **Hostname:** `booking-bot`
- **Template:** `Debian 12` or `Debian 13` (or `Ubuntu 22.04 / 24.04`)
- **Disk:** `4 GB` or `8 GB`
- **CPU:** `1 Core`
- **RAM:** `512 MB` *(The bot and gateway combined consume only ~120 MB of RAM)*
- **Network:** `DHCP` (or static local IP)

Start the container and open the **">_ Console"** tab.

---

### Step 2: Install Packages & Clone the Repository
Inside the container console, run:

```bash
# Update and install required packages
apt update -y && apt install -y git python3 python3-pip python3-venv nodejs npm

# Clone this repository and enter the directory
git clone https://github.com/MrCoolice/booking-whatsapp-bot.git /opt/dalaman-suite-bot
cd /opt/dalaman-suite-bot
```

---

### Step 3: Run the 1-Click Installer Script

```bash
chmod +x install.sh
./install.sh
```

The script automatically:
- Creates an isolated Python virtual environment (`venv`),
- Installs Python dependencies (`fastapi`, `uvicorn`, `apscheduler`, `requests`, `jinja2`),
- Installs WhatsApp Gateway Node.js dependencies (`@whiskeysockets/baileys`, `express`, `qrcode`),
- Configures and starts both systemd services (`dalaman-bot` on `:8000` and `dalaman-gateway` on `:3000`) to run 24/7 in the background.

---

### Step 4: Open Web Dashboard & Link Your WhatsApp

1. Open your browser and navigate to:  
   ğŸ‘‰ **`http://<CONTAINER-IP>:8000`**
2. In the top right header, click the **"WhatsApp"** status button.
3. A popup will display the WhatsApp pairing QR code.
4. On your phone, open WhatsApp:  
   ğŸ‘‰ **Settings > Linked Devices > Link a Device** and scan the QR code on your screen.
5. The badge will instantly turn green: **"ğŸŸ¢ WhatsApp: Aktif (+90...)"**.

---

### Step 5: Configure Settings & Wi-Fi Details

In the **System Settings** section on the right side of the dashboard:
1. Enter your **Property / Suite Name**
2. Enter your **WhatsApp Phone Number(s)** (e.g., `+90542XXXXXXX`)
3. Enter your **Wi-Fi Name** and **Password**
4. Paste your **Booking.com iCal Link** (.ics)
5. Click **"Save All Settings & Templates"**.

---

## ğŸ”‘ How to Get Your Booking.com iCal Export Link

1. Log in to [Booking.com Extranet](https://admin.booking.com).
2. Go to **Rates & Availability > Sync Calendars**.
3. Under the desired room/suite, click **"Export Calendar"**.
4. Copy the provided `.ics` URL (e.g., `https://ical.booking.com/v1/export?t=...`).
5. Paste this URL into the **"Booking iCal Link"** field in the bot's web dashboard.

---

## âš™ï¸ Service Management

Both services are managed seamlessly via `systemd`:

```bash
# Python Bot (Port 8000)
systemctl status dalaman-bot
systemctl restart dalaman-bot
journalctl -u dalaman-bot -f

# WhatsApp Gateway (Port 3000)
systemctl status dalaman-gateway
systemctl restart dalaman-gateway
journalctl -u dalaman-gateway -f
```

---

<br><br>

---

# ğŸ‡¹ğŸ‡· TÃ¼rkÃ§e

Otel, apart, villa ve butik konaklama tesisleri iÃ§in geliÅŸtirilmiÅŸ; **Booking.com** rezervasyonlarÄ±nÄ± 7/24 izleyen, yeni rezervasyonlarÄ± ve gÃ¼nlÃ¼k Check-in / Check-out hatÄ±rlatmalarÄ±nÄ± yasal **KBS / Polis Kimlik Bildirimi uyarÄ±sÄ±yla** birlikte WhatsApp Ã¼zerinden ileten, **tek tÄ±kla misafir karÅŸÄ±lama ve Wi-Fi bilgilendirme otomasyonu** sunan **%100 yerel (self-hosted)** otomasyon platformu.

Sistem, bÃ¼nyesinde barÄ±ndÄ±rdÄ±ÄŸÄ± **%100 Ãœcretsiz Yerel WhatsApp Gateway (Baileys)** sayesinde Ã¼Ã§Ã¼ncÃ¼ parti Ã¼cretli API'lere (UltraMsg, Twilio vb.) aylÄ±k abonelik Ã¶demenize gerek kalmadan tamamen kendi sunucunuz Ã¼zerinden Ã§alÄ±ÅŸÄ±r!

---

## ğŸŒŸ Ã–ne Ã‡Ä±kan Ã–zellikler

- ğŸ†“ **%100 Ãœcretsiz & KalÄ±cÄ± Yerel WhatsApp AÄŸ GeÃ§idi:** Baileys & Node.js altyapÄ±sÄ±yla kendi sunucunuzda Ã§alÄ±ÅŸÄ±r. Web panelinden tek tÄ±kla QR kod okutarak kendi WhatsApp numaranÄ±zÄ± baÄŸlayÄ±n; aylÄ±k Ã¼cret veya mesaj kotasÄ± derdini unutun.
- ğŸ› **AnlÄ±k Rezervasyon Bildirimi:** Booking.com iCal takvimini 2 dakikada bir otomatik tarar; yeni rezervasyon dÃ¼ÅŸtÃ¼ÄŸÃ¼ an yÃ¶neticiye veya personele WhatsApp mesajÄ± iletir.
- ğŸš¨ **KBS / Polis Kimlik Bildirimi HatÄ±rlatÄ±cÄ±larÄ±:** 
  - Her sabah belirlediÄŸiniz saatte (Ã¶rn. `09:00`) o gÃ¼nkÃ¼ giriÅŸler iÃ§in kimlik bildirimi uyarÄ±sÄ±.
  - O gÃ¼nkÃ¼ Ã§Ä±kÄ±ÅŸlar iÃ§in oda temizlik hazÄ±rlÄ±ÄŸÄ± ve KBS Ã§Ä±kÄ±ÅŸ bildirimi uyarÄ±sÄ±.
- ğŸ”‘ **Misafir KarÅŸÄ±lama (Self Check-in & Wi-Fi) Otomasyonu:**
  - GiriÅŸ yapacak misafirlere tek tÄ±kla Wi-Fi ÅŸifresi, giriÅŸ (`15:00`) ve Ã§Ä±kÄ±ÅŸ (`11:00`) saatleri ile Google Haritalar konumunu iÃ§eren Ã§ift dilli (TÃ¼rkÃ§e & Ä°ngilizce) karÅŸÄ±lama mesajÄ± gÃ¶nderme.
- ğŸŒ **Modern & Responsive Web Paneli:** `http://<IP>:8000` adresinden eriÅŸilebilen, Tailwind CSS ile tasarlanmÄ±ÅŸ yÃ¶netim arayÃ¼zÃ¼ ve entegre WhatsApp QR eÅŸleme penceresi.
- ğŸ•’ **AkÄ±llÄ± Saat & Durum Takibi:** Ã‡Ä±kÄ±ÅŸ gÃ¼nÃ¼ saat 11:00 Ã¶ncesi *"BugÃ¼n Ã‡Ä±kÄ±ÅŸ"*, saat 11:00 sonrasÄ± otomatik olarak *"Ã‡Ä±kÄ±ÅŸ YaptÄ±"* rozetine geÃ§er.
- ğŸ“± **Ã‡oklu Numara & Grup Bildirimi:** VirgÃ¼lle ayrÄ±lmÄ±ÅŸ birden fazla telefon numarasÄ±na (`+905...,+905...`) veya personele ait WhatsApp grubuna aynÄ± anda bildirim gÃ¶nderir.
- âœï¸ **Dinamik Mesaj ÅablonlarÄ±:** WhatsApp mesaj ÅŸablonlarÄ±nÄ± web arayÃ¼zÃ¼nden tek tÄ±kla Ã¶zelleÅŸtirebilme.
- ğŸ’¾ **KalÄ±cÄ± SQLite HafÄ±zasÄ±:** Sunucu yeniden baÅŸlasa bile veriler kaybolmaz, aynÄ± rezervasyon iÃ§in mÃ¼kerrer mesaj atmaz.
- ğŸš€ **SÄ±fÄ±r Bulut Maliyeti:** Make.com veya Zapier gibi aylÄ±k kota sÄ±nÄ±rlamasÄ± olan servisler yerine kendi Proxmox sunucunuzda Ã¼cretsiz Ã§alÄ±ÅŸÄ±r.

---

## ğŸ—ï¸ Mimari Åema

```mermaid
graph TD
    A[Booking.com iCal Takvimi] -->|2 Dakikada Bir Polling| B(FastAPI Python Servisi :8000)
    B -->|Durum & Rezervasyon DB| C[(SQLite VeritabanÄ±)]
    B -->|Mesaj GÃ¶nderimi| D[Yerel Baileys WhatsApp Gateway :3000]
    D -->|YÃ¶netici & Resepsiyon Bildirimleri| E[YÃ¶netici & Resepsiyon TelefonlarÄ±]
    D -->|Misafir KarÅŸÄ±lama MesajlarÄ±| F[Gelen Misafir WhatsApp Telefonu]
    G[Web Dashboard Paneli :8000] <-->|CanlÄ± QR Kod ModalÄ±| D
    G <-->|YÃ¶netim & CanlÄ± Loglar| B
```

---

## ğŸš€ HÄ±zlÄ± Kurulum

### 1. AdÄ±m: Proxmox'ta LXC Konteyneri OluÅŸturma (1 Dakika)
Proxmox arayÃ¼zÃ¼nÃ¼zden (`https://<proxmox-ip>:8006`) saÄŸ Ã¼stteki **"Create CT"** butonuna basarak hafif bir Linux konteyneri aÃ§Ä±n:
- **Hostname:** `booking-bot`
- **Template:** `Debian 12` veya `Debian 13` (veya `Ubuntu 22.04 / 24.04`)
- **Disk:** `4 GB` veya `8 GB`
- **CPU:** `1 Core`
- **RAM:** `512 MB` *(Bot ve Gateway toplamda yalnÄ±zca ~120 MB RAM tÃ¼ketir)*
- **Network:** `DHCP` (veya statik yerel IP)

Konteyneri oluÅŸturduktan sonra **"Start"** butonuna basÄ±p **">_ Console"** sekmesini aÃ§Ä±n.

---

### 2. AdÄ±m: Gerekli Paketleri YÃ¼kleyin ve Depoyu KlonlayÄ±n

```bash
# Temel sistem paketlerini yÃ¼kleyin
apt update -y && apt install -y git python3 python3-pip python3-venv nodejs npm

# Projeyi klonlayÄ±n ve klasÃ¶re girin
git clone https://github.com/MrCoolice/booking-whatsapp-bot.git /opt/dalaman-suite-bot
cd /opt/dalaman-suite-bot
```

---

### 3. AdÄ±m: Otomatik Kurulum Scriptini Ã‡alÄ±ÅŸtÄ±rÄ±n

```bash
chmod +x install.sh
./install.sh
```

Script otomatik olarak:
- Ä°zole Python sanal ortamÄ±nÄ± (`venv`) oluÅŸturur,
- Gerekli Python kÃ¼tÃ¼phanelerini (`fastapi`, `uvicorn`, `apscheduler`, `requests`, `jinja2`) yÃ¼kler,
- Node.js WhatsApp Gateway kÃ¼tÃ¼phanelerini kurar (`@whiskeysockets/baileys`, `express`, `qrcode`),
- `dalaman-bot` (:8000) ve `dalaman-gateway` (:3000) servislerini Linux systemd'ye kaydedip 7/24 arka planda otomatik Ã§alÄ±ÅŸacak ÅŸekilde baÅŸlatÄ±r.

---

### 4. AdÄ±m: Web Paneline GiriÅŸ ve WhatsApp EÅŸleme

1. Kurulum bittiÄŸinde tarayÄ±cÄ±nÄ±zdan panele gidin:  
   ğŸ‘‰ **`http://<KONTEYNER-IP>:8000`**
2. Ãœst bardaki **"WhatsApp"** butonuna tÄ±klayÄ±n.
3. AÃ§Ä±lan penceredeki QR kodu telefonunuzdan okutun:  
   ğŸ‘‰ **WhatsApp > Ayarlar > BaÄŸlÄ± Cihazlar > Cihaz BaÄŸla**
4. EÅŸleÅŸme tamamlandÄ±ÄŸÄ±nda buton otomatik olarak **"ğŸŸ¢ WhatsApp: Aktif (+90...)"** ÅŸekline dÃ¶necektir.

---

### 5. AdÄ±m: Rezervasyon & Wi-Fi AyarlarÄ±nÄ± Kaydetme

Paneldeki **Sistem AyarlarÄ±** bÃ¶lÃ¼mÃ¼nden:
1. **Tesis / Oda AdÄ±**
2. **WhatsApp NumaralarÄ±** (Ã¶rn. `+90542XXXXXXX`)
3. **Wi-Fi AdÄ± & Åifresi**
4. **Booking.com iCal Linki** (.ics)

bilgilerini girip **"TÃ¼m AyarlarÄ± ve ÅablonlarÄ± Kaydet"** butonuna basmanÄ±z yeterlidir!

---

## ğŸ”‘ Booking.com iCal Linki (.ics) NasÄ±l AlÄ±nÄ±r?

1. [Booking.com Extranet](https://admin.booking.com) hesabÄ±nÄ±za giriÅŸ yapÄ±n.
2. Ãœst menÃ¼den **Fiyatlar ve Kontenjan > Takvimleri Senkronize Et** sayfasÄ±na gidin.
3. Ä°lgili odanÄ±n/sÃ¼itin altÄ±nda bulunan **"Takvimi DÄ±ÅŸa Aktar" (Export Calendar)** butonuna tÄ±klayÄ±n.
4. Ekrana gelen `https://ical.booking.com/v1/export?t=...` formatÄ±ndaki **.ics takvim baÄŸlantÄ±sÄ±nÄ± kopyalayÄ±n**.
5. Bu linki web panelinizdeki **"Booking iCal Linki"** alanÄ±na yapÄ±ÅŸtÄ±rÄ±n.

---

## âš™ï¸ Servis YÃ¶netimi

Her iki servis de `systemd` ile arka planda kesintisiz Ã§alÄ±ÅŸÄ±r:

```bash
# Python Web Botu Servisi (Port 8000)
systemctl status dalaman-bot
systemctl restart dalaman-bot
journalctl -u dalaman-bot -f

# Yerel WhatsApp Gateway Servisi (Port 3000)
systemctl status dalaman-gateway
systemctl restart dalaman-gateway
journalctl -u dalaman-gateway -f
```

---

## ğŸ› ï¸ KullanÄ±lan Teknolojiler

- **Backend:** Python 3, FastAPI, Uvicorn, APScheduler, Requests, SQLite
- **WhatsApp Gateway:** Node.js, Express, [@whiskeysockets/baileys](https://github.com/WhiskeySockets/Baileys), QRCode
- **Frontend:** Jinja2 Templates, Tailwind CSS, FontAwesome
- **AltyapÄ±:** Proxmox VE (LXC Debian 12 / 13), Systemd

---

## ğŸ“„ Lisans

Bu proje [MIT LisansÄ±](LICENSE) ile lisanslanmÄ±ÅŸtÄ±r. DilediÄŸiniz gibi geliÅŸtirebilir ve kendi tesislerinizde kullanabilirsiniz.

---

**GeliÅŸtirici:** [UlaÅŸ Ã–zbek (GÃ¶lgeSiber)](https://golgesiber.com)