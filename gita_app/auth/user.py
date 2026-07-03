from django.contrib.messages.api import success

import email_utils, random
from flask import Blueprint, jsonify, request,flash, redirect, url_for, session, render_template
from database import db
from models import Student, Verse, Comment
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import (generate_password_hash, check_password_hash)

user = Blueprint("user", __name__)

def generate_otp():
    return str(random.randint(100000, 999999))

@user.route('/student-dashboard')
def student_dashboard():
    if 'user_id' not in session:
        flash('Access Denied: Please login as a student.', 'danger')
        return redirect(url_for('home'))
    student = db.get_or_404(Student, session['user_id'])
    # student = Student.query.get(session['user_id'])
    return render_template('student.html', student=student)

@user.route('/api/get_otp', methods=['POST'])
def get_otp():
    email = request.get_json()

    valid_email = email_utils.is_valid_email(email)
    if not valid_email:
        return jsonify({"success": False, "message": 'Not a Valid Email'})

    if Student.query.filter_by(email=email).first():
        return jsonify({"success": False, "message": "Email already Registered."})

    otp = generate_otp()
    purpose = 'Registration'

    # email_utils.send_otp(valid_email, otp, purpose)

    session["temp_user"] = {
        "otp": otp,
        "otp_created_at": datetime.now().isoformat()  # isoformat converts datetime → string
    }
    print(valid_email, session["temp_user"]["otp"], session["temp_user"]["otp_created_at"])
    return jsonify({"success": True, "message": "OTP Sent Successfully."})

@user.route('/api/sumbit_otp', methods=['POST'])
def get_otp_submit():
    if not session.get("temp_user"):
        return jsonify({"success": False, "message": "OTP Expired"})

    # OTP expiration check
    otp_time = datetime.fromisoformat(session["temp_user"].get("otp_created_at"))
    if datetime.now() - otp_time > timedelta(minutes=5):
        session.pop("temp_user", None)
        return jsonify({"success": False, "message": "OTP Expired"})

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
    hashed_password = generate_password_hash(str(data.get('password')), salt_length=16)
    student = Student(
        name=data.get('name'), email=email, password=password,
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

    # is_valid_password = check_password_hash(student.password, password)
    is_valid_password = (student.password == password)

    if is_valid_password:
        v_id = student.last_verse_id
        verse = Verse.query.filter_by(id=v_id).first()

        c_num = verse.chapter_number
        v_num = verse.verse_number
        session.clear()
        session['user_id'] = student.id
        redirect_url = f"/student-dashboard?verse_id={v_id}&c_num={c_num}&v_num={v_num}" if v_id else "/student-dashboard"
        return jsonify({"success": True, "redirect": redirect_url})
    return jsonify({"success": False, "message": "Invalid password entry"})

@user.route('/api/auth/forgotpassword', methods=['POST'])
def api_student_forgot_password():
    email = request.get_json()

    valid_email = email_utils.is_valid_email(email)
    if not valid_email:
        return jsonify({"success": False, "message": 'Not a Valid Email'})

    student = Student.query.filter_by(email=email).first()
    if student:
        otp = generate_otp()
        purpose = 'Reset Password'

        session["new_password"] = {
            "otp": otp,
            "otp_created_at": datetime.now().isoformat()  # isoformat converts datetime → string
        }
        # email_utils.send_otp(valid_email, otp, purpose)
        print(purpose, otp)
        return jsonify({"success": True, "message": "OTP Sent to Your Email Address."})
    else:
        return jsonify({"success": False, "message": "Email Address not found. Please Register."})

@user.route('/api/auth/changepassword', methods=['POST'])
def api_student_password_change():
    data = request.get_json() or {}
    email = data.get('email')
    password = str(data.get('newpassword'))
    otp = data.get('otp')
    student = Student.query.filter_by(email=email).first()
    if not student:
        return jsonify({"success": False, "message": "Your Profile Does Not Exist. Please Register First"})

    # OTP expiration check
    otp_time = datetime.fromisoformat(session["new_password"].get("otp_created_at"))
    if datetime.now() - otp_time > timedelta(minutes=5):
        session.pop("new_password", None)
        return jsonify({"success": False, "message": "OTP Expired"})

    if session["new_password"].get('otp') != otp:
        return jsonify({"success": False, "message": "OTP Mismatch"})

    session.pop('new_password', None)
    hashed_password = generate_password_hash(password, salt_length = 16)
    student.password = password #hashed_password
    db.session.commit()
    return jsonify({"success": True, "message": "Password Updated Successfully."})

@user.route('/api/auth/update', methods=['POST'])
def api_student_update():
    if 'user_id' not in session:
        return redirect(url_for('home'))
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


