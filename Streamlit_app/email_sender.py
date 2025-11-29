# email_sender.py — improved, production-friendly
import os
import smtplib
import time
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# ------------------------------
# ENV VARS (explicit)
# ------------------------------
# Buyer notification sender (explicit env names)
SMTP_BUYER_USER = os.getenv("SMTP_USER")      # e.g. your-buyer-sender@gmail.com
SMTP_BUYER_PASS = os.getenv("SMTP_PASS")      # app password for buyer sender
SENDER_BUYER_EMAIL = "v.n.s.pavankumar.batchu@gmail.com"

# Seller notification sender (explicit env names)
SMTP_SELLER_USER = os.getenv("SMTP_SELLER")
SMTP_SELLER_PASS = os.getenv("SMTP_SELLER_PASS")
SENDER_SELLER_EMAIL = "pavankumar.batchu23@vit.edu"

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

# Small pause between emails to avoid provider rate-limits (seconds)
EMAIL_SEND_DELAY = float(os.getenv("EMAIL_SEND_DELAY", "0.2"))

# ------------------------------
# Helper: send a single email
# ------------------------------
def send_email(to_email: str, subject: str, body: str, smtp_user: str, smtp_pass: str, from_email: str = None) -> bool:
    from_addr = from_email or smtp_user
    if not smtp_user or not smtp_pass:
        logging.error("Missing SMTP credentials for sender: %s", smtp_user)
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = from_addr
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20)
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_addr, [to_email], msg.as_string())
        server.quit()

        logging.info("Email sent to %s (from %s)", to_email, from_addr)
        return True

    except Exception as e:
        logging.exception("Failed to send email to %s: %s", to_email, e)
        return False

# --------------------------------------------------------
# EMAIL: Notify buyers (auction started)
# --------------------------------------------------------
def notify_buyers(product_name, auction_code, start_time, duration_minutes, meet_link, base_price):
    """
    Sends auction-start emails to all users with role='Buyer' and non-null email in MySQL users table.
    Returns a tuple: (success_count, total_count)
    """
    subject = f"🔔 New Auction Live: {product_name} ({auction_code})"
    body = f"""\
<html><body style="font-family:Arial, sans-serif; color:#333;">
  <div style="max-width:600px;margin:0 auto;padding:18px;border:1px solid #e6e6e6;border-radius:8px;">
    <h2 style="color:#2b7a78;text-align:center;">New Auction — {product_name}</h2>
    <p><b>Auction Code:</b> {auction_code}</p>
    <p><b>Start Time (UTC):</b> {start_time} &nbsp; <b>Duration:</b> {duration_minutes} minutes</p>
    <p><b>Starting Price:</b> ${base_price}</p>
    <div style="text-align:center;margin:20px 0;">
      <a href="{meet_link}" style="display:inline-block;padding:12px 20px;background:#2b7a78;color:#fff;border-radius:6px;text-decoration:none;">
        🎥 Join Google Meet
      </a>
    </div>
    <p style="font-size:12px;color:#666;text-align:center;">Use the auction code above to join the bidding room.</p>
  </div>
</body></html>
"""

    # Load buyers from MySQL
    try:
        import mysql.connector
        DB_CONFIG = {
            "host": "localhost",
            "user": "root",
            "password": "123456",
            "database": "auction_system"
        }
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT email FROM users WHERE role='Buyer' AND email IS NOT NULL")
        buyers = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.exception("Failed to fetch buyers from DB: %s", e)
        return 0, 0

    if not buyers:
        logging.info("No buyer emails found to notify.")
        return 0, 0

    success = 0
    total = len(buyers)

    for b in buyers:
        email = b.get("email")
        if not email:
            continue
        ok = send_email(
            to_email=email,
            subject=subject,
            body=body,
            smtp_user=SMTP_BUYER_USER,
            smtp_pass=SMTP_BUYER_PASS,
            from_email=SENDER_BUYER_EMAIL
        )
        if ok:
            success += 1
        time.sleep(EMAIL_SEND_DELAY)

    logging.info("notify_buyers: sent %d/%d emails for auction %s", success, total, auction_code)
    return success, total

# --------------------------------------------------------
# EMAIL: Notify seller when auction finished
# --------------------------------------------------------
def notify_seller(seller_email: str, product_name: str, winner: str, final_bid: float):
    subject = f"Auction Result — {product_name}"
    body = f"""\
<html><body style="font-family:Arial, sans-serif;color:#333;">
  <div style="max-width:600px;margin:0 auto;padding:18px;border:1px solid #e6e6e6;border-radius:8px;">
    <h2 style="color:#2b7a78;">Your Auction has Ended</h2>
    <p><b>Product:</b> {product_name}</p>
    <p><b>Winner:</b> {winner}</p>
    <p><b>Final Price:</b> ${final_bid}</p>
  </div>
</body></html>
"""
    return send_email(
        to_email=seller_email,
        subject=subject,
        body=body,
        smtp_user=SMTP_SELLER_USER,
        smtp_pass=SMTP_SELLER_PASS,
        from_email=SENDER_SELLER_EMAIL
    )

# --------------------------------------------------------
# Helper: quick test to validate SMTP credentials & sending
# --------------------------------------------------------
def test_send(receiver_email: str, which: str = "buyer"):
    """
    Quick function you can call from Python to verify credentials.
    which: 'buyer' or 'seller'
    """
    if which == "buyer":
        return send_email(receiver_email, "TEST BUYER SMTP", "<p>Test message</p>", SMTP_BUYER_USER, SMTP_BUYER_PASS, SENDER_BUYER_EMAIL)
    else:
        return send_email(receiver_email, "TEST SELLER SMTP", "<p>Test message</p>", SMTP_SELLER_USER, SMTP_SELLER_PASS, SENDER_SELLER_EMAIL)
