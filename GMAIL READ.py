import imaplib
import email
import os

# ---------- CONFIG ----------
IMAP_SERVER = "imap.gmail.com"
EMAIL_ACCOUNT = "airsprint.gpsfeed@gmail.com"
EMAIL_PASSWORD = "bhzz onml blgt hlud"
SAVE_FOLDER = "./csv_reports"

os.makedirs(SAVE_FOLDER, exist_ok=True)

# ---------- CONNECT ----------
mail = imaplib.IMAP4_SSL(IMAP_SERVER)
mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
mail.select("inbox")

# ---------- SEARCH ----------
# Look for the most recent email from WestCoastGPS
status, messages = mail.search(None, '(FROM "no-reply@telematics.guru")')

if status == "OK":
    latest_email_id = messages[0].split()[-1]  # grab the newest one
    status, msg_data = mail.fetch(latest_email_id, "(RFC822)")
    msg = email.message_from_bytes(msg_data[0][1])

    # ---------- ATTACHMENT LOOP ----------
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get("Content-Disposition") is None:
            continue
        filename = part.get_filename()
        if filename and filename.endswith(".csv"):
            filepath = os.path.join(SAVE_FOLDER, filename)
            with open(filepath, "wb") as f:
                f.write(part.get_payload(decode=True))
            print(f"✅ Saved latest report as {filepath}")
else:
    print("⚠️ No messages found")
