import random, re, resend, os
from flask import Blueprint, jsonify, request,flash, redirect, url_for, session, render_template
from flask_mail import Message
from database import db, mail
from models import Student, Verse, Comment, Chapter
from datetime import datetime, timedelta, timezone
from werkzeug.utils import secure_filename
from werkzeug.security import (generate_password_hash, check_password_hash)
from PIL import Image, ImageDraw, ImageFont
from translate import dynamic_sanskrit_transliterate #customized function

user = Blueprint("user", __name__)

# Optimized hash set of major common email providers
ALLOWED_DOMAINS = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "zoho.com"}
EMAIL_FORMAT_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
otp_expiry_time = 5 #in minutes
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
            subject=f"Gita {purpose} OTP",
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

resend.api_key = os.getenv("RESEND_API_KEY")
def send_otp_resend(user_email, otp, purpose):
    try:
        params = {
            "from": "onboarding@resend.dev",  # Or your verified domain
            "to": user_email,
            "subject": f"Gita {purpose} OTP",
            "html":
                f"""
                Hari Om,<br><br>

                Your One-Time Password (OTP) for {purpose} is: {otp} <br>
                This OTP is valid for 5 minutes.If you didn't request this, please ignore this email. <br><br>

                Regards,<br>
                Gita Team<br>
                """
        }
        email = resend.Emails.send(params)
        print("Mail dispatched perfectly via HTTP API hook!")
    except Exception as e:
        print(f"Error Dispatching Mail: {e}")

def generate_otp():
    return str(random.randint(100000, 999999))

@user.route('/student-dashboard')
def student_dashboard():
    if 'user_id' not in session:
        flash('Access Denied: Please login as a student.', 'danger')
        return redirect(url_for('home'))
    student = db.session.get(Student, session.get('user_id'))
    if student is None:
        session.clear()
        return redirect(url_for('home'))

    v_id = student.last_verse_id
    if v_id is None:
        return render_template('student.html', student=student)
    else:
        verse = Verse.query.filter_by(id=v_id).first()
        c_num = verse.chapter_number
        v_num = verse.verse_number
        language = session.get('language', 'en')
        return render_template('student.html',
            student=student,
            verse_id=v_id,
            c_num=c_num,
            v_num=v_num,
            language=language
        )

@user.route('/api/get_otp', methods=['POST'])
def get_otp():
    email = request.get_json()

    valid_email = is_valid_email(email)
    if not valid_email:
        return jsonify({"success": False, "message": 'Not a Valid Email'})

    if Student.query.filter_by(email=email).first():
        return jsonify({"success": False, "message": "Email already Registered."})

    otp = generate_otp()
    purpose = 'Registration'

    send_otp(valid_email, otp, purpose)
    # print(valid_email,otp,purpose)
    session["temp_user"] = {
        "email": email,
        "otp": otp,
        "otp_created_at": datetime.now().isoformat()  # isoformat converts datetime → string
    }
    return jsonify({"success": True, "message": "OTP Sent Successfully. Check the Spam folder also"})

@user.route('/api/sumbit_otp', methods=['POST'])
def get_otp_submit():
    if not session.get("temp_user"):
        return jsonify({"success": False, "message": "OTP Expired", "session": False})

    # OTP expiration check
    otp_time = datetime.fromisoformat(session["temp_user"].get("otp_created_at"))
    if datetime.now() - otp_time > timedelta(minutes=otp_expiry_time):
        session.pop("temp_user", None)
        return jsonify({"success": False, "message": "OTP Expired", "session": False})

    # OTP check
    otp = request.get_json()
    if otp != session['temp_user']['otp']:
        return jsonify({"success": False, "message": "OTP Mismatch"})

    session.pop("temp_user", None)

    return jsonify({"success": True, "message": "OTP Verified Successfully."})

@user.route('/api/auth/register', methods=['POST'])
def api_student_register():
    data = request.get_json() or {}
    email = data.get('email')
    if Student.query.filter_by(email=email).first():
        return jsonify({"success": False, "message": "Email identity already deployed inside records."})
    password = str(data.get('password'))
    hashed_password = generate_password_hash(password)
    student = Student(
        name=data.get('name'), email=email, password=hashed_password,
        age=int(data.get('age')) if data.get('age') else None,
        phone=data.get('phone'), address=data.get('address'), gender=data.get('gender')
    )

    db.session.add(student)
    db.session.commit()
    session.clear()
    session['user_id'] = student.id
    return jsonify({"success": True, "redirect": "/student-dashboard"})

@user.route('/api/auth/login', methods=['POST'])
def api_student_login():
    data = request.get_json() or {}
    email = data.get('email')
    password = str(data.get('password'))

    student = Student.query.filter_by(email=email).first()
    if not student:
        return jsonify({"success": False, "message": "Email Identity Not Registered"})

    is_valid_password = check_password_hash(student.password, password)
    # is_valid_password = (student.password == password)

    if is_valid_password:
        session.clear()
        session['user_id'] = student.id
        # redirect_url = f"/student-dashboard?verse_id={v_id}&c_num={c_num}&v_num={v_num}" if v_id else "/student-dashboard"
        redirect_url = f"/student-dashboard"
        return jsonify({"success": True, "redirect": redirect_url})
    return jsonify({"success": False, "message": "Invalid password entry"})

@user.route('/api/auth/forgotpassword', methods=['POST'])
def api_student_forgot_password():
    email = request.get_json()
    if session.get('new_password'):
        otp_time = datetime.fromisoformat(session["new_password"].get("otp_created_at"))
        session_email = session['new_password'].get('email')
        if datetime.now() - otp_time < timedelta(minutes=otp_expiry_time) and email == session_email:
            return jsonify({"success": False, "message": f'OTP already sent to email','session':True})

    valid_email = is_valid_email(email)
    if not valid_email:
        return jsonify({"success": False, "message": 'Not a Valid Email'})

    student = Student.query.filter_by(email=email).first()
    if student:
        otp = generate_otp()
        purpose = 'Reset Password'

        session["new_password"] = {
            'email': email,
            "otp": otp,
            "otp_created_at": datetime.now().isoformat()  # isoformat converts datetime → string
        }
        send_otp(valid_email, otp, purpose)
        # print(valid_email, otp, purpose)
        return jsonify({"success": True, "message": "OTP Sent to Your Email Address. Check the Spam folder also"})
    else:
        return jsonify({"success": False, "message": "Email Address not found. Please Register."})

@user.route('/api/auth/changepassword', methods=['POST'])
def api_student_password_change():
    if not session.get('new_password'):
        return jsonify({"success": False, "message": "OTP Expired", 'session': False})

    data = request.get_json() or {}
    email = data.get('email')
    password = str(data.get('newPassword'))
    otp = data.get('otp')
    session_email = session['new_password'].get('email')
    if session_email != email:
        return jsonify({"success": False, "message": "Email Entry Mismatch"})

    student = Student.query.filter_by(email=session_email).first()
    if not student:
        return jsonify({"success": False, "message": "Your Profile Does Not Exist. Please Register First"})

    # OTP expiration check
    otp_time = datetime.fromisoformat(session["new_password"].get("otp_created_at"))
    if datetime.now() - otp_time > timedelta(minutes=otp_expiry_time):
        session.pop("new_password", None)
        return jsonify({"success": False, "message": "OTP Expired", 'session': False})

    if session["new_password"].get('otp') != otp:
        return jsonify({"success": False, "message": "OTP Mismatch"})

    session.pop('new_password', None)
    hashed_password = generate_password_hash(password)
    student.password = hashed_password
    db.session.commit()
    return jsonify({"success": True, "message": "Password Updated Successfully."})

@user.route('/api/auth/update', methods=['POST'])
def api_student_update():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Session expired. Please log in again.", "redirect": url_for('home')}), 401
    data = request.get_json() or {}
    email = data.get('email')
    student = Student.query.filter_by(email=email).first()
    if not student:
        return jsonify({"success": False, "message": "Your Profile Does Not Exist. Please Register First"})
    student.age = data.get('age') if data.get('age') else None
    student.phone = data.get('phone') if data.get('phone') else None
    student.address = data.get('address') if data.get('address') else None
    student.gender = data.get('gender') if data.get('gender') else None
    db.session.commit()
    return jsonify({"success": True, "message": "Profile Updated Successfully."})

@user.route('/api/comments', methods=['POST'])
def post_new_comment():
    if 'user_id' not in session: return jsonify({"error": "Login required"}), 401
    data = request.get_json() or {}
    new_comment = Comment(text=data.get('text'), verse_id=int(data.get('verse_id')), student_id=session['user_id'])
    db.session.add(new_comment)
    db.session.commit()
    return jsonify({"success": True})

@user.route('/api/comments/<int:cid>', methods=['PUT'])
def edit_comment(cid):
    c = Comment.query.get_or_404(cid)
    if not session.get('admin_logged_in') and session.get('user_id') != c.student_id:
        return jsonify({"error": "Unauthorized Access Rule"}), 403
    data = request.get_json() or {}
    c.text = data.get('text')
    db.session.commit()
    return jsonify({"success": True})

@user.route('/api/comments/<int:cid>', methods=['DELETE'])
def delete_comment(cid):
    c = Comment.query.get_or_404(cid)
    if not session.get('admin_logged_in') and session.get('user_id') != c.student_id:
        return jsonify({"error": "Unauthorized Access Rule"}), 403
    db.session.delete(c)
    db.session.commit()
    return jsonify({"success": True})


CRON_TOKEN_MAIL = os.getenv('CRON_TOKEN_MAIL')
@user.route('/trigger-daily-email', methods=['GET'])
def send_daily_image_email():
    provided_token = request.args.get('token')
    if provided_token != CRON_TOKEN_MAIL:
        return jsonify({"error": "Unauthorized endpoint access"}), 403
    students = Student.query.all()
    receivers = ['chitraraja40@gmail.com'] if len(students) == 0 else [student.email for student in students]
    image_path = "./static/profile_pics/gita_daily_card.webp"
    if not os.path.exists(image_path):
        return jsonify({"error": "Image Card File Not Found"}), 403
    image_filename = os.path.basename(image_path)
    msg = Message(
        subject="Daily Gita Shloka Card",
        recipients=receivers
    )
    image_cid = "daily_shloka_image"
    msg.html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; text-align: center; background-color: #f7f7f7; padding: 20px;">
                <h2 style="color: #2a1b14;">✨ Gita Shloka Today ✨</h2>                    

                <!-- The magic happens here: src points directly to the CID -->
                <div style="margin: 20px auto; max-width: 600px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden;">
                    <img src="cid:{image_cid}" alt="Daily Shloka Card" style="width: 100%; height: auto; display: block;" />
                </div>

                <hr style="border: 0; border-top: 1px solid #dddddd; margin-top: 30px;" />
                <p style="font-size: 15px; color: #888888;">WebSite</p>
                <p style="font-size: 25px; color: #858888;"><a href="https://krishateach.pythonanywhere.com/">KrishnaTeach</a></p>               
            </body>
        </html>
        """
    # Open and attach the image binary data
    with open(image_path, "rb") as fp:
        msg.attach(
            filename=image_filename,
            content_type=f"image/{image_filename.split('.')[-1]}",
            data=fp.read(),
            disposition="inline",  # Crucial: Instructs email clients not to show it as a download [1]
            headers={"Content-ID": f"<{image_cid}>"}  # Maps the binary data directly to the HTML <img> tag [1]
        )
    mail.send(msg)
    os.remove(image_path)
    return jsonify({"status": "success. Mail Sent"}), 200

# Helper Functions for Pillow Drawing
def wrap_text(text, font, max_width):
    """
    Wrap text while preserving existing newline structure
    and word sequence.
    """

    all_lines = []

    # Preserve original line breaks
    paragraphs = text.strip().splitlines()

    for paragraph in paragraphs:

        # Handle empty lines
        if not paragraph.strip():
            all_lines.append("")
            continue

        words = paragraph.split()
        current_line = ""

        for word in words:

            if current_line:
                test_line = current_line + " " + word
            else:
                test_line = word

            bbox = font.getbbox(test_line)
            text_width = bbox[2] - bbox[0]

            if text_width <= max_width:
                current_line = test_line

            else:
                # Save current line
                if current_line:
                    all_lines.append(current_line)

                # Start new line with current word
                current_line = word

        # Save remaining text
        if current_line:
            all_lines.append(current_line)

    return all_lines

def get_multiline_text_height(draw, text, font, spacing=5):
    left, top, right, bottom = draw.multiline_textbbox(
        (0, 0), text, font=font, spacing=spacing
    )
    return bottom - top

def get_text_height(draw, text, font, stroke_width=0):
    """Return the rendered height of a single-line text string."""
    left, top, right, bottom = draw.textbbox(
        (0, 0), text, font=font, stroke_width=stroke_width,
    )
    return bottom - top

CRON_TOKEN_IMAGE = os.getenv('CRON_TOKEN_IMAGE')
@user.route('/trigger-daily-card', methods=['GET', 'POST'])
def generate_daily_card():
    card_download_dir = "./static/profile_pics"
    chapter, verse, lang = None, None, 'en'
    if request.method == 'GET':
        provided_token = request.args.get('token')
        chapter = request.args.get('c')
        verse = request.args.get('v')
        lang = request.args.get('lang', 'en')
        if provided_token != CRON_TOKEN_IMAGE:
            return jsonify({"error": "Unauthorized endpoint access"}), 403
        file_path = os.path.join(card_download_dir, 'gita_daily_card.webp')
        if os.path.exists(file_path):
            return jsonify({"message": "Card Already Exists"}), 200
    if request.method == 'POST':
        data = request.get_json() or {}
        chapter = data.get('c', None)
        verse = data.get('v', None)
        lang = data.get('lang', 'en')

    # Fetch random data
    if chapter is None or verse is None:
            chapters = Chapter.query.order_by(Chapter.num).all()
            chapters_list = []
            for c in chapters:
                verses = Verse.query.filter(
                    Verse.chapter_number == c.num).all()  # Getting the number of verses in each chapter
                chapters_list.append((c.num, len(verses)))
            random_tup = random.sample(chapters_list, 1)
            chapter_num = random_tup[0][0]
            verse_num = random.randint(1, random_tup[0][1])
    else:
        chapter_num = int(chapter)
        verse_num = int(verse)
    verse = Verse.query.where(Verse.chapter_number == chapter_num, Verse.verse_number == verse_num).one_or_none()
    if not verse:
        return jsonify({"error": "The Requested Shloka is not available in the DataBase"}), 403
    pat = r'<[^>]+>'
    meaning = re.sub(pat, '', verse.meaning.get(lang).get('description'))
    verse_data = {"chapter": chapter_num, "verse": verse_num,
        "shloka": dynamic_sanskrit_transliterate(verse.shloka, lang, source_lang='devanagari') if lang != 'en' else verse.shloka,
        "meaning": meaning
        }
    card_base_path = "./static/profile_pics/KrishnaTeach.webp"
    # 1. Base Canvas Preparation
    bg_img = Image.open(card_base_path)
    w, h = bg_img.width, bg_img.height
    o_b, i_b = int(w * 0.03), int(h * 0.04)
    inc = int(h * 0.01)

    overlay = Image.new("RGBA", bg_img.size, (0, 0, 0, 0))
    overlay_canvas = ImageDraw.Draw(overlay)
    box_coords = [o_b, o_b, w - o_b, h - o_b]
    overlay_canvas.rounded_rectangle(
        box_coords,
        radius=15,
        fill=(20, 20, 20, 180),  # Dark charcoal color with ~55% opacity
        outline=(212, 175, 55, 60),  # Optional: Very faint gold border matching your card
        width=2
    )
    card = Image.alpha_composite(bg_img.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(card)

    # 3. Draw Traditional Geometric Gold Borders
    # draw.rectangle([o_b, o_b, w - o_b, h - o_b], outline=(241, 196, 15, 140), width=2)
    draw.rectangle([i_b, i_b, w - i_b, h - i_b], outline=(230, 126, 34, 80), width=1)

    # 4. Initialize Typography
    if lang == 'ta':
        font = "./static/font/NotoSerifTamil-Regular.ttf"
        sanskrit_font = ImageFont.truetype(font, int(w * 0.035))
        meaning_font = ImageFont.truetype(font, int(w * 0.035))
    else:
        font = "./static/font/NotoSerifDevanagari-Regular.ttf"
        sanskrit_font = ImageFont.truetype(font, int(w * 0.055))
        meaning_font = ImageFont.truetype(font, int(w * 0.04))
    title_font = ImageFont.truetype(font, int(w * 0.04))
    footer_font = ImageFont.truetype(font, int(w * 0.03))

    today_date = datetime.now(timezone.utc)
    formatted_time = today_date.strftime('%d-%b-%Y')
    cur_y = int(h * 0.066)
    draw.text((w // 2, cur_y), formatted_time, fill=(241, 196, 15, 255), font=footer_font, anchor="mm")

    # 5. Render Header/Title Block
    cur_y += get_text_height(draw, formatted_time, footer_font) + (2 * inc)
    title_text = f"BHAGAVAD GITA • CHAPTER {verse_data['chapter']} VERSE {verse_data['verse']}"
    draw.text((w//2, cur_y), title_text, fill=(241, 196, 15, 255), font=title_font, anchor="mm")

    # Elegant Orange Accent Separator Line
    cur_y += get_text_height(draw, title_text, title_font) + inc
    draw.line([(w // 2 - int(w * 0.25), cur_y), (w // 2 + int(w * 0.25), cur_y)], fill=(230, 126, 34, 200), width=2)

    # 6. Render Devanagari Sanskrit Verses
    cur_y += get_text_height(draw, title_text, title_font) + (2 * inc)
    draw.text((w // 2, cur_y), "*** SHLOKA ***", fill=(241, 196, 15, 190), font=title_font, anchor="mm")

    cur_y += get_text_height(draw, "---SHLOKA---", title_font) + inc
    sanskrit_lines = wrap_text(verse_data['shloka'], sanskrit_font, int(w * 0.9))
    sanskrit_block = "\n".join(sanskrit_lines)
    if lang == 'ta':
        sanskrit_block = sanskrit_block.replace("꞉", ":")
    draw.multiline_text((w // 2, cur_y), sanskrit_block, fill=(255, 255, 255, 245),
                        font=sanskrit_font, anchor="ma", align="center", spacing=15)

    cur_y += get_multiline_text_height(draw, sanskrit_block, sanskrit_font, 20) + (7 * inc)
    draw.text((w // 2, cur_y), "*** MEANING ***", fill=(247, 115, 115, 190), font=title_font, anchor="mm")

    # 7. Render Translated Meaning Block with Dynamic Text Wrapping
    cur_y += get_text_height(draw, "---MEANING---", title_font) + inc
    meaning_block = "\n".join(wrap_text(verse_data['meaning'].strip(), meaning_font, int(w * 0.9)))
    draw.multiline_text((w//2, cur_y), meaning_block, fill=(218, 223, 230),
                        font=meaning_font, anchor="ma", align="center", spacing=12)

    # 8. Bottom Footer Layout
    footer_text = "---Gita Shloka Card---"
    draw.text((w // 2, h - int(w * 0.1)), footer_text, fill=(230, 126, 34, 130), font=footer_font, anchor="mm")

    # 9. Save and Display Inline in Colab Cell Output
    if request.method == 'POST':
        student_id = session['user_id']
        output_filename = f"{student_id}_BG_Card_{chapter_num}_{verse_num}_{lang}.webp"
    else:
        output_filename = "gita_daily_card.webp"
    final_card = card.resize((w // 2, h // 2), Image.Resampling.LANCZOS).convert("RGB")
    card_download_dir = "./static/profile_pics"
    file_path = os.path.join(card_download_dir, output_filename)
    final_card.save(file_path, "WEBP")
    response = {
        'status': True,
        'message': "success. Card Created",
        'file': url_for('static', filename=f'profile_pics/{output_filename}')
    }
    return jsonify(response), 200

@user.route('/deleteUserCards')
def delete_user_cards():
    card_dir = "./static/profile_pics"
    files = os.listdir(card_dir)
    student_id = session['user_id']
    for file in files:
        if f'{student_id}_BG_Card' in file:
            os.remove(os.path.join(card_dir, file))
    return jsonify(status='success'), 200