from flask_mail import Message, Mail
import re

mail = Mail()

# Optimized hash set of major common email providers
ALLOWED_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "zoho.com"
}

# Simple regex pattern just to catch basic format typos (e.g. spaces, multiple @ symbols)
EMAIL_FORMAT_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
def is_valid_email(email):
    email = email.strip().lower()
    if not re.match(EMAIL_FORMAT_REGEX, email):
        # print("Validation failed: Bad string syntax formatting.")
        return False

    # Extract the domain name after the '@' sign safely
    try:
        username, domain = email.split('@', 1)
    except ValueError:
        return False

    # Strict check against your trusted providers list
    if domain not in ALLOWED_DOMAINS:
        # print(f"Validation failed: Domain '{domain}' is not on the allowed list.")
        return False

    # Validation succeeded instantly
    # print('validity', email)
    return email

def send_otp(email, otp, purpose):
    try:
        msg = Message(
            subject="Gita Registration OTP",
            recipients=[email]
        )
        msg.body = f"""
        Hari Om,
            
        Your One-Time Password (OTP) for {purpose} is: {otp}
        This OTP is valid for 5 minutes.If you didn't request this, please ignore this email.
              
        Regards,
        Gita Team
        """
        mail.send(msg)
    except Exception as e:
        error_msg = f"Error sending OTP: {e}"
        print(f"Error Sending Mail: {e}")
