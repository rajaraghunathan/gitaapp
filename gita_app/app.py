import os
from config import Config
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from dotenv import load_dotenv
from database import db, mail, migrate
from models import Chapter, Verse, Student, AcharyaComment
from translate import text_translate_google, batch_translate_google, translate_large_text_with_google

from auth import user, admin, routes

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')


# Database Setup
app.config.from_object(Config)
mail.init_app(app)

# Ensure upload directory exists
UPLOAD_FOLDER = Config.UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
db.init_app(app)

# Initialize migration system
migrate.init_app(app, db)

# Register blueprint
app.register_blueprint(user)
app.register_blueprint(admin)
app.register_blueprint(routes)


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/')
def home():
    if 'user_id' not in session:
        return render_template('index.html')
    else:
        student = db.session.get(Student, session.get('user_id'))
        return render_template('index.html', student=student)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# --- REPOSITORY READ AND UPDATE ENGINE PIPELINES ---
@app.route('/api/chapters', methods=['GET']) #Finalised & Working
def get_chapters():
    chapters = Chapter.query.order_by(Chapter.num).all()
    chapters_list = []
    for c in chapters:
        verses = Verse.query.filter(Verse.chapter_number == c.num).all() #Getting the number of verses in each chapter
        chapters_list.append({
            "id": c.id, "chapter_number": c.num,
            "name": c.name, "summary": c.summary['en'], "verse_count": len(verses) #"verses": verse_list
        })
    return jsonify(chapters_list)

@app.route('/api/chapterShlokas', methods=['GET']) #Finalised & Working
def get_chapter_and_verses():
    chapter_num = request.args.get('chapter', type=int)
    if not chapter_num:
        chapter_num = 1

    results = db.session.query(Chapter, Verse).where(Chapter.num == chapter_num). \
        join(Chapter, Chapter.num == Verse.chapter_number ). \
        order_by(Verse.verse_number). \
        all()

    verses_list = []
    for chapter, verse in results:
        cols_to_skip_in_chapter = {'id', 'num'}
        cols_to_skip_in_verse = {'youtube_url', 'comments'}
        c_dict = {k: v for k, v in chapter.__dict__.items()
                  if not k.startswith('_') and k not in cols_to_skip_in_chapter}
        v_dict = {
            'id': verse.id,
            'chapter_number': verse.chapter_number,
            'verse_number': verse.verse_number,
            'shloka': verse.shloka,
            'description': verse.meaning.get('en').get('description')
        }
        # v_dict = {k: v for k, v in verse.__dict__.items()
        #           if not k.startswith('_') and k not in cols_to_skip_in_verse}
        verses_list.append(c_dict | v_dict)
    return jsonify(verses_list)

@app.route('/api/translate', methods=['POST'])
def translate_text_stream():
    data = request.get_json() or {}
    text = data.get('enText', '').strip()
    anvayam = data.get('enAnvayam', [])
    source = data.get('sourceLang', 'en').strip()
    target = data.get('targetLang', 'en').strip()

    translated_description, success_text = text_translate_google(text, source, target)
    translated_anvayam, success_batch = batch_translate_google(anvayam, source, target)

    if success_text and success_batch:
        return jsonify({
            "success": True,
            "translated_text": translated_description,
            "translated_anvayam": translated_anvayam
        }), 200

    error_details = []
    if not success_text:
        error_details.append(f"Main text error: {translated_description}")
    if not success_batch:
        error_details.append(f"Batch items error: {translated_anvayam}")

    return jsonify({
        "success": False,
        "message": "Translation processing failed.",
        "details": " | ".join(error_details)
    }), 500

@app.route('/api/admin/acharya_translate', methods=['POST'])
def get_acharya_translate_admin():
    data = request.get_json() or {}
    acharya = str(data.get('acharya'))
    chapter_number = data.get('chapter_number')
    verse_number = data.get('verse_number')
    target_lang = data.get('targetLang', 'en').strip()

    record = (db.session.query(AcharyaComment).filter(
        AcharyaComment.chapter_number == chapter_number,
        AcharyaComment.verse_number == verse_number
    ).first())
    acharya_dict = getattr(record, acharya)
    if acharya_dict.get('sa'):
        source_lang = 'sa'
        commentary = acharya_dict.get('sa')
    else:
        source_lang = 'en'
        commentary = acharya_dict.get('en')
    if commentary:
        translated_commentary, success = translate_large_text_with_google(commentary, source_lang, target_lang)
    else:
        translated_commentary, success = translate_large_text_with_google("", source_lang, target_lang)
    if success:
        return jsonify({
            "success": True,
            "translated_text": translated_commentary
        }), 200
    else:
        return jsonify({
            "success": False,
            "message": "Translation processing failed.",
            "details": f"Main text error: {translated_commentary}"
        }), 500

with app.app_context():
    db.create_all()
    # if Verse.query.count() == 0:
    #     db.session.add(Verse(chapter=1, verse_number=1, shloka="धर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः ।",
    #                          meaning="Dhritarashtra said: O Sanjaya...", youtube_url="https://youtube.com"))
    #     db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)