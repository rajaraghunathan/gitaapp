import os, json, uuid, re, requests, io, csv
from flask import Blueprint, jsonify, request,flash, redirect, url_for, session, render_template, make_response
from database import db
from models import Student, Verse, AcharyaComment, Comment
from zoneinfo import ZoneInfo

admin = Blueprint("admin", __name__)

ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')

# --- HTML TEMPLATE ROUTING RENDERERS ---

@admin.route('/admin-dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        flash('Access Denied: Admin authorization required.', 'danger')
        return redirect(url_for('home'))
    if not session.get('temp'):
        return render_template('admin.html')
    else:
        vid = session['temp'].get('id')
        chapter = session['temp'].get('chapter')
        verse = session['temp'].get('verse')
        return render_template('admin.html',vid=vid,chapter=chapter,verse=verse)

@admin.route('/api/auth/admin', methods=['POST'])
def api_admin_login():
    data = request.get_json() or {}
    if data.get('password') == ADMIN_PASSWORD:
        session.clear()
        session['admin_logged_in'] = True
        return jsonify({"success": True, "redirect": "/admin-dashboard"})
    return jsonify({"success": False, "message": "Invalid Admin Credentials"})

@admin.route('/api/singleverse/admin', methods=['GET']) #Finalised & Working
def get_single_verse_admin():
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 403
    chapter_number = request.args.get('chapter', type=int)
    verse_number = request.args.get('verse', type=int)
    verse = (db.session.query(Verse)
             .where(Verse.chapter_number == chapter_number, Verse.verse_number == verse_number)
             .scalar())
    v_dict = {k: v for k, v in verse.__dict__.items() if not k.startswith('_')}
    session['temp'] = {
        'id': verse.id,
        'chapter': chapter_number,
        'verse': verse_number
    }
    return jsonify(v_dict)

@admin.route('/api/meaning/update', methods=['POST']) #Finalised & Working
def update_verse_admin():
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 403

    payload = request.get_json()
    if not payload:
        return jsonify({"error": "Missing payload"}), 400

    chapter_number = int(payload.get('chapter_number'))
    verse_number = int(payload.get('verse_number'))
    meaning = payload.get('meaning')
    youtube_urls = payload.get('youtube_urls')
    shloka = payload.get('shloka')
    verse = (db.session.query(Verse)
             .where(Verse.chapter_number == chapter_number, Verse.verse_number == verse_number)
             .scalar())
    verse.meaning = meaning
    verse.youtube_url = youtube_urls
    verse.shloka = shloka
    db.session.commit()

    return jsonify({"success": True, "message": "Database updated successfully."}), 200

@admin.route('/api/acharya', methods=['GET'])
def get_acharya_comment_admin():
    if session.get('admin_logged_in') :
        chapter_number = request.args.get('chapter', type=int)
        verse_number = request.args.get('verse', type=int)
        result = db.session.execute(db.select(AcharyaComment)
        .where(AcharyaComment.chapter_number == chapter_number, AcharyaComment.verse_number == verse_number)
            ).scalar()

        if result is not None:
            payload = {
                'ramanuja': result.ramanuja,
                'sankara': result.sankara,
                'madhava': result.madhava,
                'desika': result.desika,
                'siva': result.siva
            }
            return jsonify(payload)
        else:
            return jsonify({})
    else:
        return jsonify({"error": "Unauthorized"}), 403

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) #Current File Directory
BASE_DIR = os.path.dirname(CURRENT_DIR) #One Level Up to Next Directory
acharya_cache_file = os.path.join(BASE_DIR, "json using codes", "acharya_translations_cache.json")
def load_acharya_cache():
    if os.path.exists(acharya_cache_file):
        try:
            with open(acharya_cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_to_acharya_cache(cache_data):
    try:
        with open(acharya_cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving to cache file: {e}")

# ADDED EXTRA PARAMETERS: ch, vs, acharya
def safe_translate_large_text(text, target_lang, ch, vs, acharya):
    if not text or not str(text).strip():
        return ""

    # Normalize language codes
    if target_lang == 'sc': target_lang = 'sa'
    if target_lang == 'ht': target_lang = 'hi'
    if target_lang in ['tamil', 'ta']:
        target_lang = 'ta'
    elif target_lang in ['telugu', 'te']:
        target_lang = 'te'
    elif target_lang in ['english', 'en']:
        target_lang = 'en'

    text_str = str(text).strip()
    ch_str = str(ch)
    vs_str = str(vs)

    # 1. READABLE NESTED CACHE CHECK
    cache = load_acharya_cache()

    # Safely navigate down the tree to see if this translation exists
    if (ch_str in cache and
            vs_str in cache[ch_str] and
            acharya in cache[ch_str][vs_str] and
            target_lang in cache[ch_str][vs_str][acharya]):
        print(f"⚡ Cache Hit! Chapter {ch} Verse {vs} ({acharya}) in {target_lang} loaded from disk.")
        return cache[ch_str][vs_str][acharya][target_lang]

    # 2. Cache Miss: Execute Azure translation setup
    AZURE_KEY = os.getenv('AZURE_KEY')
    AZURE_ENDPOINT = "https://api.cognitive.microsofttranslator.com"
    AZURE_REGION = "eastus"
    MAX_LIMIT = 4000
    constructed_url = AZURE_ENDPOINT + '/translate'
    # if target_lang == 'hi':
    #     params = {'api-version': '3.0', 'from': 'sa', 'to': target_lang}
    # else:
    #     params = {'api-version': '3.0', 'from': 'hi', 'to': target_lang}

    headers = {
        'Ocp-Apim-Subscription-Key': AZURE_KEY,
        'Ocp-Apim-Subscription-Region': AZURE_REGION,
        'Content-type': 'application/json',
        'X-ClientTraceId': str(uuid.uuid4())
    }

    def call_azure_api(text_to_send):
        # EXPLICIT COUPLING FIX FOR HINDI
        if target_lang == 'hi':
            try:
                import mtranslate
                print("Running web-scraping bridge for Sanskrit-to-Hindi pipeline...")

                # mtranslate explicitly handles sa -> hi without script copy errors
                web_translation = mtranslate.translate(text_to_send, 'hi', 'sa')
                return web_translation
            except Exception as e:
                print(f"Sanskrit to Hindi mtranslate engine failed: {e}")
                return None

        # UNIVERSAL AZURE ROUTE FOR ENGLISH, TAMIL, TELUGU
        else:
            params = {
                'api-version': '3.0',
                'from': 'hi',
                'to': target_lang
            }
            body = [{'text': text_to_send}]
            try:
                response = requests.post(constructed_url, params=params, headers=headers, json=body)
                if response.status_code == 200:
                    return response.json()[0]['translations'][0]['text']
                else:
                    print(f"Azure Error Code {response.status_code}: {response.text}")
                    return None
            except Exception as e:
                print(f"Network error linking to Azure: {e}")
                return None

    if len(text_str) <= MAX_LIMIT:
        translated = call_azure_api(text_str)
        final_result = translated if translated else text_str
    else:
        print(f"🌐 Cache Miss. Translating Ch {ch} Vs {vs} ({acharya}) via Azure...")
        sentences = re.split(r'(?<=[.!?।])\s+', text_str)
        chunks = []
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= MAX_LIMIT:
                current_chunk += (" " if current_chunk else "") + sentence
            else:
                if current_chunk: chunks.append(current_chunk)
                if len(sentence) > MAX_LIMIT:
                    for i in range(0, len(sentence), MAX_LIMIT): chunks.append(sentence[i:i + MAX_LIMIT])
                    current_chunk = ""
                else:
                    current_chunk = sentence
        if current_chunk: chunks.append(current_chunk)

        translated_chunks = []
        for chunk in chunks:
            translated_part = call_azure_api(chunk)
            if translated_part:
                translated_chunks.append(translated_part)
            else:
                return text_str
        final_result = " ".join(translated_chunks)

    # 3. SAVE TO NESTED TREE DICTIONARY
    if final_result and final_result != text_str:
        # Create empty parent objects on the fly if they don't exist yet
        if ch_str not in cache: cache[ch_str] = {}
        if vs_str not in cache[ch_str]: cache[ch_str][vs_str] = {}
        if acharya not in cache[ch_str][vs_str]: cache[ch_str][vs_str][acharya] = {}

        cache[ch_str][vs_str][acharya][target_lang] = final_result
        save_to_acharya_cache(cache)
        print(f"💾 Saved Translation: Ch {ch} Vs {vs} [{acharya}] ({target_lang}) to cache.")

    return final_result

@admin.route('/api/commentaries/update', methods=['POST'])
def update_commentaries():
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 403

    payload = request.get_json()
    if not payload:
        return jsonify({"error": "Missing payload"}), 400

    try:
        chapter_number = int(payload.get('chapter_number'))
        verse_number = int(payload.get('verse_number'))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid chapter or verse number format"}), 400

    acharya = payload.get('acharya')  # e.g., 'siva'
    commentaries = payload.get('commentary_data')  # This is the incoming dict

    # 1. Validation and Guarding Columns
    if not acharya or not hasattr(AcharyaComment, acharya):
        return jsonify({"error": f"Invalid column: {acharya}"}), 400

    # 2. Query the entire row model instead of just a scalar value
    record = (db.session.query(AcharyaComment)
              .filter(
        AcharyaComment.chapter_number == chapter_number,
        AcharyaComment.verse_number == verse_number
    ).first())

    if not record:
        return jsonify({"error": "Commentary record not found"}), 404

    # 3. Retrieve the current DB dictionary value
    current_db_dict = getattr(record, acharya)

    # 4. Compare both dictionaries
    # Fast equality check for dictionaries in Python
    if current_db_dict == commentaries:
        return jsonify({"status": "similar", "message": "No changes detected. Data is identical."}), 200

    # 5. Inject/Update the database if they are not similar
    try:
        # Assigning a new dict or modifying a MutableDict flags it as dirty for SQLAlchemy
        setattr(record, acharya, commentaries)
        db.session.commit()
        return jsonify({"success": True, "message": "Database updated successfully."}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database update failed", "details": str(e)}), 500

@admin.route('/api/comments/all', methods=['GET'])
def get_all_comments_admin():
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 403
    user_tz_name = request.headers.get('X-User-Timezone', 'UTC')
    try:
        user_zone = ZoneInfo(user_tz_name)
    except Exception:
        user_zone = ZoneInfo('UTC')  # Fallback if timezone name is unrecognized
    comments = Comment.query.order_by(Comment.timestamp.desc()).all()
    return jsonify([{
        "id": c.id, "text": c.text, "student_name": c.student.name, "student_email": c.student.email,
        "chapter": c.verse.chapter_number, "verse_number": c.verse.verse_number,
        "timestamp": c.timestamp.astimezone(user_zone).strftime('%d-%b-%Y %I:%M %p') if c.timestamp else 'Just now'
    } for c in comments])

@admin.route('/api/students/all', methods=['GET'])
def get_all_students_admin():
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 403
    students = Student.query.order_by(Student.id).all()
    return jsonify([{
        k: v for k, v in student.__dict__.items() if not k.startswith('_')
    } for student in students])

@admin.route('/api/students/<int:sid>', methods=['DELETE'])
def delete_student(sid):
    student = Student.query.get_or_404(sid)
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized Access Rule"}), 403
    db.session.delete(student)
    db.session.commit()
    return jsonify({"success": True})

@admin.route('/admin/export/<string:data_type>')
def admin_csv_export(data_type):
    if not session.get('admin_logged_in'):
        return "Unauthorized", 403

    output = io.StringIO()
    writer = csv.writer(output)

    if data_type == 'comments':
        writer.writerow(
            ['Comment ID', 'Student Name', 'Student Email', 'Chapter', 'Verse', 'Comment Text', 'Timestamp'])
        comments = Comment.query.all()
        for c in comments:
            writer.writerow(
                [c.id, c.student.name, c.student.email, c.verse.chapter_number, c.verse.verse_number, c.text, c.timestamp])
        filename = "gita_student_comments.csv"

    elif data_type == 'students':
        writer.writerow(['Student ID', 'Name', 'Email', 'Age', 'Phone', 'Gender', 'Address'])
        students = Student.query.all()
        for s in students:
            writer.writerow([s.id, s.name, s.email, s.age, s.phone, s.gender, s.address])
        filename = "gita_registered_students.csv"

    else:
        return "Invalid Data Type", 400

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-type"] = "text/csv"
    return response