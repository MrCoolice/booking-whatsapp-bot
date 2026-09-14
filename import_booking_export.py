#!/usr/bin/env python3
import sys
import os
import re
import csv
import io
import sqlite3
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_database.db")

def normalize_phone(raw_phone):
    if not raw_phone:
        return ""
    s = re.sub(r"[\s\.\-\(\)]", "", str(raw_phone).strip())
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

def import_file(filepath):
    if not os.path.exists(filepath):
        print(f"HATA: Dosya bulunamadi: {filepath}")
        return

    with open(filepath, "rb") as f:
        content_bytes = f.read()

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
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("SELECT value FROM settings WHERE key = 'suite_name'")
    row = cur.fetchone()
    suite_name = row[0] if row else "Dalaman Airport Suite 11"

    matched = 0
    created = 0
    total = 0

    for r in reader:
        checkout_val = (r.get("Check-out") or r.get("Checkout") or r.get("Cikis") or "").strip()
        phone_val = (r.get("Phone number") or r.get("Phone") or r.get("Telefon") or "").strip()
        duration_val = (r.get("Duration (nights)") or r.get("Nights") or r.get("Gece") or "1").strip()

        if not checkout_val or not phone_val:
            continue

        norm_p = normalize_phone(phone_val)
        if not norm_p:
            continue

        total += 1
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

        cur.execute("SELECT uid FROM reservations WHERE checkout = ? AND (checkin = ? OR checkin = '')", (c_out_str, c_in_str))
        found = cur.fetchone()

        if found:
            cur.execute("UPDATE reservations SET guest_phone = ? WHERE uid = ?", (norm_p, found[0]))
            matched += 1
        else:
            new_uid = f"booking-csv-{c_in_str}-{c_out_str}-{norm_p[-6:]}"
            cur.execute("""
                INSERT OR IGNORE INTO reservations (uid, checkin, checkout, suite_name, notified_new, guest_phone, created_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
            """, (new_uid, c_in_str, c_out_str, suite_name, norm_p, now_str))
            created += 1

    conn.commit()
    conn.close()

    print(f"Tamamlandi! Toplam {total} satir islendi.")
    print(f"- Mevcut rezervasyonla eslesen: {matched}")
    print(f"- Yeni misafir olarak eklenen: {created}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanim: python3 import_booking_export.py <dosya_yolu.tsv/csv>")
        sys.exit(1)
    import_file(sys.argv[1])
