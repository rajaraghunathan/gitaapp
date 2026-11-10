import os, json, uuid, re, requests, io, csv
import time

from flask import Blueprint, jsonify, request,flash, redirect, url_for, session, render_template, make_response
from database import db
from models import Chapter, Student, Verse, AcharyaComment, Comment, QuizQuestion, QuizQuestionTamil, GlossaryFaq
from zoneinfo import ZoneInfo
from translate import remove_non_printable_from_object
from pathlib import Path
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

admin = Blueprint("admin", __name__)

ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) #Current File Directory
BASE_DIR = os.path.dirname(CURRENT_DIR) #One Level Up to Next Directory

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
    meaning = remove_non_printable_from_object(payload.get('meaning'))
    youtube_urls = remove_non_printable_from_object(payload.get('youtube_urls'))
    shloka = remove_non_printable_from_object(payload.get('shloka'))
    verse = (db.session.query(Verse)
             .where(Verse.chapter_number == chapter_number, Verse.verse_number == verse_number)
             .scalar())
    verse.meaning = meaning
    verse.youtube_url = youtube_urls
    # verse.shloka = shloka
    verse.shlok = shloka
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
    cleaned_commentary = remove_non_printable_from_object(commentaries)
    if current_db_dict == cleaned_commentary:
        return jsonify({"status": "similar", "message": "No changes detected. Data is identical."}), 200

    # 5. Inject/Update the database if they are not similar
    try:
        # Assigning a new dict or modifying a MutableDict flags it as dirty for SQLAlchemy
        setattr(record, acharya, cleaned_commentary)
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

@admin.route('/admin/quiz', methods=['GET'])
def admin_quiz_get():
    if not session.get('admin_logged_in'):
        return "Unauthorized", 403
    lang = request.args.get('lang', 'en')
    chapter = int(request.args.get('chapter', 1))
    table = QuizQuestion if lang == 'en' else QuizQuestionTamil if lang == 'ta' else None
    if not table:
        return jsonify({'message': 'Data does not exist'})
    quiz = db.session.query(table).where(table.chapter == chapter).order_by(table.id).all()
    quiz_list = [{
        k: v for k, v in q.__dict__.items() if not k.startswith('_')
    } for q in quiz]
    return jsonify(quiz_list)

@admin.route('/admin/quiz/update', methods=['POST'])
def admin_quiz_update():
    if not session.get('admin_logged_in'):
        return "Unauthorized", 403
    payload = request.get_json()
    lang = payload.get('lang')
    chapter = int(payload.get('chapter'))
    questions = remove_non_printable_from_object(payload.get('questions'))

    table = QuizQuestion if lang == 'en' else QuizQuestionTamil

    try:
        for item in questions:
            status = item.get('status')
            item_id = item.get('id')
            if status == 'new':
                question_entry = table(
                    chapter=item["chapter"],
                    question=item["question"],
                    option_a=item["option_a"],
                    option_b=item["option_b"],
                    option_c=item["option_c"],
                    option_d=item["option_d"],
                    answer= item["answer"],
                    correct_answer=item["correct_answer"]
                )
                db.session.add(question_entry)
            elif status == 'updated':
                quiz = table.query.get(item_id)
                quiz.question = item["question"]
                quiz.option_a = item["option_a"]
                quiz.option_b = item["option_b"]
                quiz.option_c = item["option_c"]
                quiz.option_d = item["option_d"]
                quiz.answer = item["answer"]
                quiz.correct_answer = item["correct_answer"]
            elif status == 'deleted':
                quiz = table.query.get(item_id)
                if quiz:
                    db.session.delete(quiz)

        db.session.commit()
        return jsonify({'success': True, 'message': 'DB Updated Successfully'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database update failed", "details": str(e)}), 500

@admin.route('/admin/glossary', methods=['GET'])
def admin_glossary_get():
    if not session.get('admin_logged_in'):
        return "Unauthorized", 403
    chapter = int(request.args.get('chapter', 1))
    verse = int(request.args.get('verse', 1))
    table = GlossaryFaq
    glossary = db.session.query(table).where(table.chapter == chapter, table.verse == verse, table.type == 'glossary').order_by(table.id).all()
    if not glossary:
        return jsonify([])
    glossary_list = [{
        k: v for k, v in q.__dict__.items() if not k.startswith('_')
    } for q in glossary]
    return jsonify(glossary_list)

@admin.route('/admin/glossary/update_or_delete', methods=['POST'])
def admin_glossary_update_or_delete():
    if not session.get('admin_logged_in'):
        return "Unauthorized", 403
    payload = request.get_json()
    action = payload.get('action')
    ch = int(payload.get('chapter'))
    ver = int(payload.get('verse'))
    lang = payload.get('lang')
    idx = payload.get('id')
    question = remove_non_printable_from_object(payload.get('question'))
    answer = remove_non_printable_from_object(payload.get('answer'))
    table = GlossaryFaq
    try:
        if action == 'update':
            if idx == 'new':
                new_glossary = table(chapter=ch, verse=ver, type='glossary', question={lang:question}, answer={lang:answer})
                db.session.add(new_glossary)
            else:
                glossary = db.session.query(table).where(table.id == int(idx)).scalar()
                glossary.question[lang] = question
                glossary.answer[lang] = answer
            db.session.commit()
            return jsonify({'success': True, 'message': 'Item Updated Successfully in Database'}), 200
        if action == 'delete':
            glossary = table.query.get(int(idx))
            glossary.question.pop(lang)
            glossary.answer.pop(lang)
            if glossary.question == {}:
                db.session.delete(glossary)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Item Deleted Successfully in Database'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, "message": "Database update failed" + str(e)}), 500

@admin.route('/admin/faq', methods=['GET'])
def admin_faq_get():
    if not session.get('admin_logged_in'):
        return "Unauthorized", 403
    chapter = int(request.args.get('chapter', 1))
    verse = int(request.args.get('verse', 1))
    table = GlossaryFaq
    faq = db.session.query(table).where(table.chapter == chapter, table.verse == verse, table.type == 'faq').order_by(table.id).all()
    if not faq:
        return jsonify([])
    faq_list = [{
        k: v for k, v in q.__dict__.items() if not k.startswith('_')
    } for q in faq]
    return jsonify(faq_list)

@admin.route('/admin/faq/update_or_delete', methods=['POST'])
def admin_faq_update_or_delete():
    if not session.get('admin_logged_in'):
        return "Unauthorized", 403
    payload = request.get_json()
    action = payload.get('action')
    ch = int(payload.get('chapter'))
    ver = int(payload.get('verse'))
    lang = payload.get('lang')
    idx = payload.get('id')
    question = remove_non_printable_from_object(payload.get('question'))
    answer = remove_non_printable_from_object(payload.get('answer'))
    table = GlossaryFaq
    try:
        if action == 'update':
            if idx == 'new':
                new_faq = table(chapter=ch, verse=ver, type='faq', question={lang:question}, answer={lang:answer})
                db.session.add(new_faq)
            else:
                faq = db.session.query(table).where(table.id == int(idx)).scalar()
                faq.question[lang] = question
                faq.answer[lang] = answer
            db.session.commit()
            return jsonify({'success': True, 'message': 'FAQ Item Updated Successfully in Database'}), 200
        if action == 'delete':
            faq = table.query.get(int(idx))
            faq.question.pop(lang)
            faq.answer.pop(lang)
            if faq.question == {}:
                db.session.delete(faq)
            db.session.commit()
            return jsonify({'success': True, 'message': 'FAQ Item Deleted Successfully in Database'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, "message": "Database update failed" + str(e)}), 500

# Update DB data vis-à-vis local and production from Google Drive
FOLDER_ID = "11yhz_aFxzjlTHuN1ob85eySdmNEI0fSD"
def get_drive_service():
    SCOPES = ["https://www.googleapis.com/auth/drive"]
    KEY_FILE = json.loads(os.getenv('GOOGLE_OAUTH_CREDENTIALS_JSON'))
    creds = None
    try:
        if os.path.exists("credentials/token.json"):
            creds = Credentials.from_authorized_user_file("credentials/token.json", SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                KEY_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)
            with open("credentials/token.json", "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        drive = build('drive', 'v3', credentials=creds)
        return drive, 'success'
    except Exception as e:
        error_details = {"error_type": e.__class__.__name__, "message": str(e)}
        return None, error_details


def get_files_drive(drive):
    query = f"'{FOLDER_ID}' in parents and trashed = false"
    json_files = []
    page_token = None

    while True:
        result = drive.files().list(
            q=query,
            pageSize=1000,
            pageToken=page_token,
            fields="nextPageToken,files(id,name,mimeType)",
        ).execute()

        json_files.extend(
            f for f in result.get("files", [])
            if f["name"].lower().endswith(".json")
            or f["mimeType"] == "application/json"
        )

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return json_files

def upload_to_drive(drive, json_file_name):
    json_dir = os.path.join(BASE_DIR, "static", "json_files")
    files_uploaded = []

    file_path = os.path.join(json_dir, json_file_name)
    json_file = Path(file_path)

    # Find existing file(s) with this name in the target folder.
    query = (
        f"'{FOLDER_ID}' in parents and name = '{json_file.name}' and trashed = false"
        # f"and name = '{json_file.name}' "
        # "and trashed = false"
    )
    result = drive.files().list(
        q=query,
        fields="files(id,name)",
    ).execute()

    # Move existing match(es) to Trash.
    for old_file in result.get("files", []):
        drive.files().update(
            fileId=old_file["id"],
            body={"trashed": True},
        ).execute()

    # Upload the new file
    metadata = {"name": json_file.name, "mimeType": "application/json", "parents": [FOLDER_ID],}
    uploaded = drive.files().create(
        body=metadata,
        media_body=MediaFileUpload(
            str(json_file),
            mimetype="application/json",
            resumable=True,
        ),
        fields="id,name",
    ).execute()
    files_uploaded.append({"file_name": uploaded["name"], "id": uploaded["id"]})
    if os.path.exists(os.path.join(json_dir, json_file_name)):
        os.remove(os.path.join(json_dir, json_file_name))
    time.sleep(1)
    drive_files = get_files_drive(drive)
    drive_files.append({"name": uploaded["name"], "id": uploaded["id"]})
    local_host = True if CURRENT_DIR.startswith('E:') else False
    if not local_host:
        drive_files[:] = [f for f in drive_files if f.get('name').startswith('local')]
    else:
        drive_files[:] = [f for f in drive_files if not f.get('name').startswith('local')]

    return files_uploaded, drive_files

table_class = {'chapter': Chapter, 'verse': Verse,
                   'acharya_comment': AcharyaComment, 'quiz_question': QuizQuestion,
                   'quiz_question-tamil': QuizQuestionTamil, 'glossary_faq': GlossaryFaq}

def export_data (table_name, col_name, filter_criteria):
    table = table_class.get(table_name)
    if hasattr(table, col_name):
        verse = db.session.query(table).where(getattr(table, col_name) == filter_criteria).all()
    else:
        verse = []
    data = {'table_name': table_name, 'col_name': col_name, 'filter_criteria': filter_criteria, 'table_data':[]}
    for v in verse:
        temp_data = {k: v for k, v in v.__dict__.items() if not k.startswith('_')}
        data['table_data'].append(temp_data)
    # today_date = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    db_location = 'local' if BASE_DIR.startswith('E:') else 'webapp'
    file_name_construct = f"{db_location}_db_{col_name}_{filter_criteria}_{table_name}.json"
    json_path = os.path.join(BASE_DIR, "static", "json_files", file_name_construct)
    if len(data.get('table_data')) > 0:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return file_name_construct

@admin.route('/admin/upload_drive', methods=['POST'])
def admin_upload_drive():
    if not session.get('admin_logged_in'):
        return "Unauthorized", 403
    payload = request.get_json()
    table_name =  payload.get('table', 'chapter')
    criteria = int(payload.get('criteria','1'))
    col_name = payload.get('col_name', 'num')
    json_file_name = export_data(table_name, col_name, criteria) # It's a function
    time.sleep(1)
    drive, res = get_drive_service()
    if drive:
        files_uploaded, drive_files = upload_to_drive(drive, json_file_name) # It's a function
        return jsonify({'success': True, 'files_to_drive': files_uploaded,
                        'drive_files': drive_files,'message': 'Uploaded Successfully'}), 200
    else:
        return jsonify({'success': False, 'message': str(res)}), 500

@admin.route('/admin/get_drive_files')
def admin_get_drive_files():
    if not session.get('admin_logged_in'):
        return "Unauthorized", 403
    drive, res = get_drive_service()
    if drive:
        drive_files = get_files_drive(drive)
        local_host = True if CURRENT_DIR.startswith('E:') else False
        if not local_host:
            drive_files[:] = [f for f in drive_files if f.get('name').startswith('local')]
        else:
            drive_files[:] = [f for f in drive_files if not f.get('name').startswith('local')]
        return jsonify({'success': True, 'drive_files': drive_files, 'message': 'Files are loaded Successfully'}), 200
    else:
        return jsonify({'success': False, 'drive_files': [], 'message': str(res)}), 500

def get_json_from_drive(drive_service, file_id):
    try:
        # 1. Request the file content using the file_id
        requested = drive_service.files().get_media(fileId=file_id)

        # 2. Create an in-memory byte buffer to hold the downloaded data
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, requested)

        # 3. Stream and download the file data
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(f"Download progress: {int(status.progress() * 100)}%")

        # 4. Rewind the buffer pointer to the beginning
        fh.seek(0)

        # 5. Load the bytes directly into a Python dictionary/list
        json_data = json.loads(fh.read().decode('utf-8'))
        return {'json_data': json_data}

    except Exception as e:
        return {'json_data': None, 'message': str(e)}

@admin.route('/admin/update_db/<string:file_id>')
def admin_update_db(file_id):
    # flag_modified(verse, 'meaning')
    if not session.get('admin_logged_in'):
        return "Unauthorized", 403
    drive, res = get_drive_service()
    if drive:
        json_data = get_json_from_drive(drive, file_id)
    else:
        return jsonify({'success': False, 'message': f"Failed to get the Drive Instance. error: {str(res)}"}), 500
    if json_data.get('json_data') is None:
        return jsonify({'success': False, 'message': f"Failed to download data From Google Drive {json_data.get('message')}"}), 500
    try:
        data = json_data.get('json_data')
        db_table = table_class.get(data.get('table_name'))
        incoming_table = data.get('table_data', [])
        record_same = []
        record_diff = []
        record_new = []
        record_deleted = []

        # 1. Map the incoming records by their unique ID
        incoming_records_map = {row['id']: row for row in incoming_table}
        incoming_ids = set(incoming_records_map.keys())

        # 2. Fetch all current records from the main DB for this scope (e.g., Chapter 2)
        # Fetching them all at once avoids running a slow query inside a loop
        incoming_col = data.get('col_name')
        incoming_filter = data.get('filter_criteria')
        existing_records = db.session.query(db_table).where(getattr(db_table, incoming_col) == incoming_filter).all()
        existing_records_map = {record.id: record for record in existing_records}
        existing_ids = set(existing_records_map.keys())
        ids_to_delete = existing_ids - incoming_ids
        ids_to_update = existing_ids & incoming_ids
        ids_to_insert = incoming_ids - existing_ids

        # --- PHASE 1: HANDLE DELETIONS ---
        for record_id in ids_to_delete:
            print(existing_records_map[record_id])
            db.session.delete(existing_records_map[record_id])
            record_deleted.append(record_id)
        if len(record_deleted) > 0:
            db.session.flush()

        # --- PHASE 2: HANDLE UPDATES ---
        for record_id in ids_to_update:
            current_record = existing_records_map[record_id]
            new_data = incoming_records_map[record_id]

            for key, value in new_data.items():
                if key != 'id' and getattr(current_record, key) != value:
                    setattr(current_record, key, value)
                    if not record_id in record_diff:
                        record_diff.append(record_id)
                else:
                    if not record_id in record_same:
                        record_same.append(record_id)

        # --- PHASE 3: HANDLE INSERTS ---
        for record_id in ids_to_insert:
            new_row_data = incoming_records_map[record_id]
            if 'id' in new_row_data.keys():
                new_row_data.pop('id')
            # Unpack the dictionary safely including the original ID to keep sync intact
            new_record = GlossaryFaq(**new_row_data)
            db.session.add(new_record)
            record_new.append(record_id)

        if len(record_diff) + len(record_new) + len(record_deleted) > 0:
            db.session.commit()
        if drive:
            drive.files().delete(fileId=file_id).execute()
        return jsonify({'success': True if drive else False,
                        'found': f'{len(existing_records)} records found in {data.get('table_name')}',
                        'same': f'{len(record_same)} records are same',
                        'Updated': f'{len(record_diff)} records are updated. Updated ids are {record_diff}',
                        'Inserted': f'{len(record_new)} records are inserted. Inserted ids are {record_new}',
                        'Deleted': f'{len(record_deleted)} number of records are deleted. Deleted ids are {record_deleted}',
                        'message': 'All inserts, updates, and deletes! Synced Successfully in Database'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, "message": "Database update failed", 'error': str(e)}), 500