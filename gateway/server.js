const express = require('express');
const http = require('http');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const pino = require('pino');
const QRCode = require('qrcode');
const path = require('path');
const fs = require('fs');

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;
const AUTH_DIR = path.join(__dirname, 'auth_info');

if (!fs.existsSync(AUTH_DIR)) {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
}

let sock = null;
let qrCodeData = null;
let qrCodeImage = null;
let connectionStatus = 'disconnected'; // 'disconnected', 'connecting', 'qr_ready', 'connected'
let connectedUser = null;
const sentMessages = new Map();

async function startSock() {
    connectionStatus = 'connecting';
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version, isLatest } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
        version,
        logger: pino({ level: 'silent' }),
        printQRInTerminal: true,
        auth: state,
        browser: ['DalamanSuiteBot', 'Chrome', '120.0.0.0'],
        syncFullHistory: false,
        markOnlineOnConnect: true,
        getMessage: async (key) => {
            if (sentMessages.has(key.id)) {
                return sentMessages.get(key.id);
            }
            return undefined;
        }
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            qrCodeData = qr;
            connectionStatus = 'qr_ready';
            try {
                qrCodeImage = await QRCode.toDataURL(qr);
            } catch (err) {
                console.error('QR olusturma hatasi:', err);
            }
            console.log('Yeni WhatsApp QR Kodu hazir! Telefonunuzla okutun.');
        }

        if (connection === 'close') {
            const shouldReconnect = (lastDisconnect && lastDisconnect.error && lastDisconnect.error.output)
                ? lastDisconnect.error.output.statusCode !== DisconnectReason.loggedOut
                : true;

            console.log('Baglanti koptu. Yeniden baglaniliyor mu?', shouldReconnect);
            connectionStatus = 'disconnected';
            qrCodeData = null;
            qrCodeImage = null;
            connectedUser = null;

            if (shouldReconnect) {
                setTimeout(startSock, 5000);
            } else {
                console.log('Oturum kapatildi (Logged out). auth_info klasorunu temizleyip yeniden baslatin.');
            }
        } else if (connection === 'open') {
            connectionStatus = 'connected';
            qrCodeData = null;
            qrCodeImage = null;
            connectedUser = sock.user ? sock.user.id.split(':')[0] : 'Aktif';
            console.log(`WhatsApp baglantisi basariyla kuruldu! Kullanici: ${connectedUser}`);
        }
    });

    // 5. Iki Yonlu Dinleyici (Misafir Yanitlarini Yakalama & Webhook'a Bildirme)
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        if (type !== 'notify') return;
        for (const msg of messages) {
            if (!msg.message || msg.key.fromMe) continue;
            
            const sender = msg.key.remoteJid;
            if (!sender || sender.includes('@g.us') || sender === 'status@broadcast') continue;

            const text = msg.message.conversation || 
                         msg.message.extendedTextMessage?.text || 
                         msg.message.imageMessage?.caption || '';

            if (!text || !text.trim()) continue;

            const phone = sender.split('@')[0];
            console.log(`[INBOUND] Misafirden mesaj geldi (${phone}): ${text}`);

            try {
                const postData = JSON.stringify({
                    phone: phone,
                    text: text.trim(),
                    message_id: msg.key.id,
                    timestamp: msg.messageTimestamp
                });

                const reqPost = http.request({
                    hostname: '127.0.0.1',
                    port: 8000,
                    path: '/api/webhook/whatsapp-inbound',
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Content-Length': Buffer.byteLength(postData)
                    },
                    timeout: 5000
                }, (resPost) => {
                    resPost.resume();
                });

                reqPost.on('error', (err) => {
                    console.error('[INBOUND WEBHOOK ERROR]:', err.message);
                });

                reqPost.write(postData);
                reqPost.end();
            } catch (e) {
                console.error('[INBOUND WEBHOOK EXCEPTION]:', e.message);
            }
        }
    });
}

// 1. Baglanti Durumu
app.get('/status', (req, res) => {
    res.json({
        status: connectionStatus,
        phone: connectedUser,
        hasQr: !!qrCodeImage
    });
});

// 2. QR Kod Verisi (Data URL / JSON)
app.get('/qr', (req, res) => {
    if (connectionStatus === 'connected') {
        return res.json({ status: 'connected', message: 'Zaten bagli!' });
    }
    if (!qrCodeImage) {
        return res.json({ status: connectionStatus, message: 'QR kod henuz hazir degil, bekleyin...' });
    }
    res.json({
        status: 'qr_ready',
        qrImage: qrCodeImage
    });
});

// 3. QR Kod Sayfasi (Tarayicida acip telefonla okutmak icin direkt HTML)
app.get('/qr-view', (req, res) => {
    if (connectionStatus === 'connected') {
        return res.send(`
            <div style="font-family:sans-serif; text-align:center; padding:50px;">
                <h2 style="color:green;">✅ WhatsApp Baglantisi Aktif!</h2>
                <p>Bagli Hat: <b>${connectedUser}</b></p>
            </div>
        `);
    }
    if (!qrCodeImage) {
        return res.send(`
            <div style="font-family:sans-serif; text-align:center; padding:50px;">
                <h2>⏳ QR Kod Olusturuluyor...</h2>
                <p>Sayfayi 3 saniye sonra yenileyin.</p>
                <script>setTimeout(() => location.reload(), 3000);</script>
            </div>
        `);
    }
    res.send(`
        <div style="font-family:sans-serif; text-align:center; padding:30px;">
            <h2>📱 WhatsApp Web Cihaz Baglama</h2>
            <p>Telefonunuzdan <b>WhatsApp > Ayarlar > Bagli Cihazlar > Cihaz Bagla</b> deyip asagidaki kodu okutun:</p>
            <img src="${qrCodeImage}" style="width:280px; height:280px; border:2px solid #ccc; padding:10px; border-radius:10px;" />
            <p style="color:#666; font-size:12px;">Sayfa 15 saniyede bir otomatik yenilenir.</p>
            <script>setTimeout(() => location.reload(), 15000);</script>
        </div>
    `);
});

// 4. Mesaj Gonderme Ucu (POST /send)
app.post('/send', async (req, res) => {
    const rawPhone = req.body.phone || req.body.to;
    const message = req.body.message || req.body.text;

    if (!rawPhone || !message) {
        return res.status(400).json({ error: 'phone ve message alanlari zorunludur' });
    }

    if (connectionStatus !== 'connected' || !sock) {
        return res.status(503).json({ error: 'WhatsApp baglantisi aktif degil! Once QR kodu okutun.' });
    }

    try {
        let jid = String(rawPhone).trim();
        // Grup kontrolu
        if (jid.includes('@g.us')) {
            // jid grup zaten
        } else {
            // Normal telefon numarasi temizleme
            jid = jid.replace(/\+/g, '').replace(/\s+/g, '').replace(/-/g, '');
            if (!jid.includes('@s.whatsapp.net')) {
                jid = `${jid}@s.whatsapp.net`;
            }
        }

        const sent = await sock.sendMessage(jid, { text: message });
        if (sent && sent.key && sent.key.id && sent.message) {
            sentMessages.set(sent.key.id, sent.message);
            if (sentMessages.size > 500) {
                const firstKey = sentMessages.keys().next().value;
                sentMessages.delete(firstKey);
            }
        }
        return res.json({
            success: true,
            messageId: sent.key.id,
            to: jid
        });
    } catch (err) {
        console.error('Mesaj gonderme hatasi:', err);
        return res.status(500).json({ error: err.message || 'Mesaj gonderilemedi' });
    }
});

// Sunucuyu Baslat (Yalnizca localhost uzerinden erisilebilir - Ag Guvenligi)
app.listen(PORT, '127.0.0.1', () => {
    console.log(`Yerel WhatsApp Gateway yalnizca yerel (127.0.0.1:${PORT}) olarak guvenli calisiyor.`);
    startSock();
});
