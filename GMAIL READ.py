import imaplib
import email
import os

# ---------- CONFIG ----------
IMAP_SERVER = "imap.gmail.com"
EMAIL_ACCOUNT = "airsprint.gpsfeed@gmail.com"
EMAIL_PASSWORD = "bhzz onml blgt hlud"
SAVE_FOLDER = "./csv_reports"
SAVE_AS = "latest_report.csv"  # always overwrite this file

os.makedirs(SAVE_FOLDER, exist_ok=True)

# ---------- CONNECT ----------
mail = imaplib.IMAP4_SSL(IMAP_SERVER)
mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
mail.select("inbox")

# ---------- SEARCH ----------
# Search for the latest matching email
status, messages = mail.search(None, '(FROM "no-reply@telematics.guru" SUBJECT "ASP TRACKING EMAIL")')

if status == "OK" and messages[0]:
    latest_email_id = messages[0].split()[-1]
    status, msg_data = mail.fetch(latest_email_id, "(RFC822)")
    msg = email.message_from_bytes(msg_data[0][1])

    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get("Content-Disposition") is None:
            continue

        filename = part.get_filename()
        if filename and filename.endswith(".csv"):
            filepath = os.path.join(SAVE_FOLDER, SAVE_AS)
            with open(filepath, "wb") as f:
                f.write(part.get_payload(decode=True))
            print(f"✅ Saved report as {filepath} (overwritten)")
else:
    print("⚠️ No matching emails found")
