import os
from config import Config
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from dotenv import load_dotenv
from database import db
from flask_migrate import Migrate
from models import Chapter, Verse
from email_utils import mail
from deep_translator import GoogleTranslator

from auth import user, admin, routes

load_dotenv()

# mail = Mail()
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
migrate = Migrate()
migrate.init_app(app, db)

# Register blueprint
app.register_blueprint(user)
app.register_blueprint(admin)
app.register_blueprint(routes)


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    if 'user_id' not in session:
        return render_template('index.html',logged='no')
    else:
        return render_template('index.html', logged='yes')

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
        v_dict = {k: v for k, v in verse.__dict__.items()
                  if not k.startswith('_') and k not in cols_to_skip_in_verse}
        verses_list.append(c_dict | v_dict)
    return jsonify(verses_list)

@app.route('/api/translate', methods=['POST'])
def translate_text_stream():
    data = request.get_json() or {}
    text_to_translate = data.get('text', '').strip()
    target_language = data.get('lang', 'en').strip() # Defaults to English ('en')

    if not text_to_translate:
        return jsonify({"success": False, "message": "No text provided"}), 400

    try:
        # Built-in function call handles the text translation matrix locally
        translated_result = GoogleTranslator(source='auto', target=target_language).translate(text_to_translate)
        return jsonify({"success": True, "translated_text": translated_result})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

with app.app_context():
    db.create_all()
    # if Verse.query.count() == 0:
    #     db.session.add(Verse(chapter=1, verse_number=1, shloka="धर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः ।",
    #                          meaning="Dhritarashtra said: O Sanjaya...", youtube_url="https://youtube.com"))
    #     db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
    # app.run(host='0.0.0.0', port=5000, debug=True)