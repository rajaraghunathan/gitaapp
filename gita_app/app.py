import os, socket
from config import Config
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from dotenv import load_dotenv
from database import db, mail, migrate
from models import Chapter, Verse, Student, AcharyaComment
from translate import translate_api_groq, dynamic_sanskrit_transliterate

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
    lang = request.args.get('lang')
    chapters = Chapter.query.order_by(Chapter.num).all()
    chapters_list = []
    for c in chapters:
        summary = c.summary[lang] if c.summary.get(lang) else 'Un Available'
        verses = Verse.query.filter(Verse.chapter_number == c.num).all() #Getting the number of verses in each chapter
        chapters_list.append({
            "id": c.id, "chapter_number": c.num,
            "admin_logged": True if session.get('admin_logged_in') else False,
            "name": c.name, "summary": summary, "verse_count": len(verses) #"verses": verse_list
        })
    return jsonify(chapters_list)

@app.route('/api/chapterShlokas', methods=['GET']) #Finalised & Working
def get_chapter_and_verses():
    chapter_num = request.args.get('chapter', type=int)
    lang = request.args.get('lang', 'en')
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
            'shloka':  verse.shlok, #verse.shloka,
            'description': verse.meaning.get(lang).get('description'),
            "admin_logged": True if session.get('admin_logged_in') else False
        }
        # v_dict = {k: v for k, v in verse.__dict__.items()
        #           if not k.startswith('_') and k not in cols_to_skip_in_verse}
        verses_list.append(c_dict | v_dict)
    return jsonify(verses_list)

@app.route('/api/translate', methods=['POST'])
def translate_text_stream():
    data = request.get_json() or {}
    incoming_content = data.get('enIncoming')
    source = data.get('sourceLang')
    target = data.get('targetLang')
    requirement = data.get('requirement')
    if requirement == 'description':
        translated = translate_api_groq([incoming_content],target)
        return jsonify({
            "success": True,
            "translated_text": ' '.join(translated)
        })
    else:
        text_strings = [item.get('sa') for item in incoming_content]
        translated = translate_api_groq(text_strings, target)
        for (idx, item) in enumerate(incoming_content):
            shloka_word = dynamic_sanskrit_transliterate(incoming_content[idx].get('sa'),target)
            incoming_content[idx]['sa'] = shloka_word
            incoming_content[idx]['en'] = translated[idx]
        return jsonify({
            "success": True,
            "translated_text": incoming_content,
        })

@app.route('/api/admin/acharya_translate', methods=['POST'])
def get_acharya_translate_admin():
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json() or {}
    chapter_number = data.get('chapter_number')
    verse_number = data.get('verse_number')
    target_lang = data.get('target_lang', 'some').strip()
    record = (db.session.query(AcharyaComment).filter(
        AcharyaComment.chapter_number == int(chapter_number),
        AcharyaComment.verse_number == int(verse_number)
    ).first())
    acharya_dict = getattr(record, 'ramanuja')
    commentary = acharya_dict.get('sa',acharya_dict.get('en','Source Language is not Existing'))
    translated = translate_api_groq([commentary], target_lang)
    if isinstance(translated, list):
        return jsonify({
            "success": True,
            "translated_text": " ".join(translated)
        })
    else:
        return jsonify({
            "success": False,
            "translated_text": f"Translation processing failed: {translated}"
        })

with app.app_context():
    db.create_all()

def get_local_ip():
    """Finds the active local IPv4 address of the computer."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connects to a dummy local address to identify the active network card
        s.connect(("10.254.254.254", 1))
        ip_address = s.getsockname()[0]
    except Exception:
        # Fallback if no network interface or hotspot is connected
        ip_address = "127.0.0.1"
    finally:
        s.close()
    return ip_address

if __name__ == '__main__':
    """
    # 1. Automatically grab your computer's local IP address
    HOST = get_local_ip()
    PORT = 5000

    # 2. Print instructions in the console for easy copying
    print("\n" + "=" * 50)
    print(f"MOBILE ACCESS LINK: http://{HOST}:{PORT}")
    print("=" * 50 + "\n")

    # 3. Bind Flask to '0.0.0.0' so it listens to both localhost and the mobile network
    # We pass the HOST as a printed reminder, but '0.0.0.0' ensures all network cards accept the connection
    app.run(host="0.0.0.0", port=PORT, debug=True)
    """
    app.run(debug=True)