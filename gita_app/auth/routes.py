import os, json, translate, random, re
from flask import Blueprint, jsonify, request, session
from database import db
from models import Student, Verse, Comment, AcharyaComment, QuizQuestion, QuizScore, QuizQuestionTamil
from datetime import datetime, timezone
from auth.admin import safe_translate_large_text #customized function
from deep_translator import GoogleTranslator
from translate import dynamic_sanskrit_transliterate #customized function
from zoneinfo import ZoneInfo

routes = Blueprint("routes", __name__)

# Define path for the local cache file
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) #Current File Directory
BASE_DIR = os.path.dirname(CURRENT_DIR) #One Level Up to Next Directory
CACHE_FILE = os.path.join(BASE_DIR, "json using codes", "mean_translations_cache.json")
# Helper function to load cache from JSON file safely
def load_translation_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}  # Return empty dict if file is corrupted
    return {}

# Helper function to save a new entry to the JSON file safely
def save_to_translation_cache(key, value):
    cache = load_translation_cache()
    cache[key] = value
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Failed to write cache to file: {e}")

@routes.route('/api/singleverse', methods=['GET']) #Finalised & Working
def get_single_verse_user():
    if 'user_id' in session:
        chapter_number = request.args.get('chapter', type=int)
        verse_number = request.args.get('verse', type=int)

        lang = request.args.get('language', type=str)
        if not lang: return jsonify({"error": "Missing lang parameter"}), 400

        verse = (db.session.query(Verse)
                 .where(Verse.chapter_number == chapter_number, Verse.verse_number == verse_number)
                 .scalar())
        if not verse: return jsonify({"error": "Verse not found"}), 404

        v_dict = {k: v for k, v in verse.__dict__.items() if not k.startswith('_')}

        shloka_sa = v_dict["shloka"]
        v_dict["shloka"] = {
            'sa': shloka_sa,
            'ta': dynamic_sanskrit_transliterate(shloka_sa, 'ta'),
            'te': dynamic_sanskrit_transliterate(shloka_sa, 'te'),
            'en': dynamic_sanskrit_transliterate(shloka_sa, 'en')
        }

        # CASE A: Requested language is already available in the dictionary
        if lang in v_dict["meaning"]:
            # Keep ONLY the requested language inside the meaning dictionary
            v_dict["meaning"] = {lang: v_dict["meaning"][lang]}
            v_dict["translated"] = "no"
            return jsonify(v_dict)

        # CASE B: Check local JSON file cache
        cache_key = f"{chapter_number}_{verse_number}_{lang}"
        local_cache = load_translation_cache()

        if cache_key in local_cache:
            v_dict["meaning"] = {lang: local_cache[cache_key]}
            v_dict["translated"] = "yes"
            print(f"⚡ Cache Hit! Shloka Chapter {chapter_number} Verse {verse_number} in {lang} loaded from disk.")
            return jsonify(v_dict)

        # CASE C: Completely missing -> Perform Native Batch Translation
        else:
            # If requested not available skipping the translation route and loading default en content
            v_dict["meaning"] = {'en': v_dict["meaning"]['en']}
            v_dict["translated"] = "no"
            return jsonify(v_dict)

            english_content = v_dict["meaning"].get('en', {})
            strings_to_translate = []

            # Step 1: Collect all English strings into an ordered list
            def collect_strings(data):
                if isinstance(data, dict):
                    for v in data.values(): collect_strings(v)
                elif isinstance(data, list):
                    for item in data: collect_strings(item)
                elif isinstance(data, str) and re.search(r'[a-zA-Z]', data):
                    strings_to_translate.append(data)

            collect_strings(english_content)

            translated_strings = []
            if strings_to_translate:
                try:
                    # FIX: Use translate_batch() instead of " ||| ".join()
                    # This guarantees Google Translate never eats or mangles your structure
                    translator = GoogleTranslator(source='en', target=lang)
                    translated_strings = translator.translate_batch(strings_to_translate)
                except Exception as e:
                    return jsonify({"error": f"Translation pipeline failed: {str(e)}"}), 500

            # Step 2: Rebuild the nested dictionary mapping the translated items back safely
            string_iterator = iter(translated_strings)

            def rebuild_nested(data):
                if isinstance(data, dict):
                    return {k: rebuild_nested(v) for k, v in data.items()}
                elif isinstance(data, list):
                    return [rebuild_nested(item) for item in data]
                elif isinstance(data, str):
                    if re.search(r'[a-zA-Z]', data):
                        # Pop the next translated string from the clean list
                        return next(string_iterator, data)
                    return data
                return data

            translated_content = rebuild_nested(english_content)

            # Save permanently to your local JSON file cache
            save_to_translation_cache(cache_key, translated_content)
            print(f"💾 Saved Shloka Translation: Ch {chapter_number} Vs {verse_number} ({lang}) to cache.")

            # Format and return the filtered dictionary
            v_dict["meaning"] = {lang: translated_content}
            v_dict["translated"] = "yes"
            return jsonify(v_dict)
    else:
        return jsonify({"error": "Unauthorized"}), 403

@routes.route('/api/student_comments/<int:vid>', methods=['GET'])
def get_student_comments(vid):
    if 'user_id' not in session: return jsonify({"error": "Unauthorized"}), 401
    user_tz_name = request.headers.get('X-User-Timezone', 'UTC')
    language = request.headers.get('lang', 'en')
    session['language'] = language
    try:
        user_zone = ZoneInfo(user_tz_name)
    except Exception:
        user_zone = ZoneInfo('UTC')  # Fallback if timezone name is unrecognized

    v = Verse.query.get_or_404(vid)
    if 'user_id' in session:
        student = Student.query.get_or_404(session['user_id']) #Student.query.get(session['user_id'])
        if student:
            student.last_verse_id = v.id
            db.session.commit()

    comments_data = []
    sorted_comments = Comment.query.filter_by(verse_id=vid).order_by(Comment.timestamp.desc()).all()

    if sorted_comments:
        for c in sorted_comments:
            # Safe inline check: Use formatting if timestamp is valid, otherwise provide a fallback string
            # formatted_time = c.timestamp.strftime('%d-%b-%Y %I:%M %p') if c.timestamp else 'Just now'
            formatted_time = c.timestamp.astimezone(user_zone).strftime('%d-%b-%Y %I:%M %p') if c.timestamp else 'Just now'
            comments_data.append({
                "id": c.id,
                "text": c.text,
                "student_name": c.student.name,
                "student_id": c.student_id,
                "timestamp": formatted_time
            })

    return jsonify({
        "comments": comments_data, "current_user_id": session.get('user_id')
    })

@routes.route('/api/acharya/student', methods=['GET'])
def get_acharya_comment_student():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 403

    chapter_number = request.args.get('chapter', type=int)
    verse_number = request.args.get('verse', type=int)
    lang = request.args.get('language')

    result = (db.session.query(AcharyaComment).where(
        AcharyaComment.chapter_number == chapter_number,
        AcharyaComment.verse_number == verse_number)
              .scalar())

    if result is None:
        return jsonify({"error": "Database Value Does Not Exist"}), 403

    row_dict = {c.name: getattr(result, c.name) for c in result.__table__.columns}

    # Build base template dictionary cleanly
    acharya_dict = {}
    acharyas = ['ramanuja', 'sankara', 'madhava', 'desika', 'siva']

    for name in acharyas:
        # Prevent server crashes if an entire acharya column key is missing in row_dict
        source_data = row_dict.get(name) or {}

        # Initialize internal schema dynamic assignments
        acharya_dict[name] = {
            'author': source_data.get('author')
        }

        text_in_requested_lang = source_data.get(lang)
        sanskrit_source_text = source_data.get('sa')
        english_source_text = source_data.get('en')

        # Scenario 1: Language copy already exists locally in DB
        if text_in_requested_lang:
            acharya_dict[name][lang] = text_in_requested_lang
            acharya_dict[name]['lang status'] = 'Default Content'

        # Scenario 2: Translate on-the-fly from available Sanskrit source
        elif sanskrit_source_text:
            # translated = safe_translate_large_text(sanskrit_source_text, lang, chapter_number, verse_number, name)
            translated = None
            if translated:
                acharya_dict[name][lang] = translated
                acharya_dict[name]['lang status'] = 'Translated From Sanskrit'
            elif translated is None:
                # Caught an active network block; handle natively without crashing route
                acharya_dict[name][lang] = sanskrit_source_text
                acharya_dict[name]['lang status'] = '(Showing Sanskrit Source)'
            else:
                acharya_dict[name]['lang status'] = 'Translation Failed/Empty'

        # Scenario 3: Fallback workflows if neither condition is satisfied
        else:
            if name in ['siva']:
                acharya_dict[name][lang] = source_data.get('en', '')
                acharya_dict[name]['lang status'] = 'No Translation'
            else:
                # Safe dictionary navigation fallback via .get()
                acharya_dict[name][lang] = source_data.get('en', '')
                acharya_dict[name]['lang status'] = 'No Translation'

    return jsonify(acharya_dict)

@routes.route('/api/quiz/<int:chapter_num>//<lang>', methods=['GET'])
def get_randomized_quiz(chapter_num, lang):
    if 'user_id' not in session: return jsonify({"error": "Login required"}), 401
    if lang == 'en':
        questions = QuizQuestion.query.filter_by(chapter=chapter_num).all()
    else:
        questions = QuizQuestionTamil.query.filter_by(chapter=chapter_num).all()

    if not questions:
        return jsonify({"error": "No questions found for this chapter"}), 404

    # 2. Pick 10 questions at random in one step
    random_10_questions = random.sample(questions, 10)

    options_keys = ["option_a", "option_b", "option_c", "option_d"]
    randomized_quiz_data = []

    for q in random_10_questions:
        # Extract unique options
        unique_texts = []
        for k in options_keys:
            val = getattr(q, k)
            if val and (val not in unique_texts):
                unique_texts.append(val)

        while len(unique_texts) < 4:
            unique_texts.append(f"[Alternative Option {len(unique_texts)+1}]")

        # Shuffle the options in memory
        random.shuffle(unique_texts)

        # Build payload without exposing 'correct_answer'
        shuffled_question_dict = {
            "id": q.id,
            "chapter": q.chapter,
            "question": q.question,
            "A": unique_texts[0],
            "B": unique_texts[1],
            "C": unique_texts[2],
            "D": unique_texts[3],
        }
        randomized_quiz_data.append(shuffled_question_dict)
    # random.shuffle(randomized_quiz_data)
    return jsonify(randomized_quiz_data)


@routes.route('/api/quiz/submit', methods=['POST'])
def submit_quiz_score():
    if 'user_id' not in session: return jsonify({"error": "Login required"}), 401

    data = request.get_json() or {}
    chapter = int(data.get('chapter', 1))
    lang = data.get('lang', 'en').strip()
    answers = data.get('answers', {})  # Expected format: {"question_id": "text"}

    # Updating the DB with Current Score
    current_score = 'No answers provided'
    cur_total = len(answers)
    if cur_total != 0:
        question_ids = [int(q_id) for q_id in answers.keys()]
        if lang == 'en':
            questions = QuizQuestion.query.filter(QuizQuestion.id.in_(question_ids)).all()
        else:
            questions = QuizQuestionTamil.query.filter(QuizQuestionTamil.id.in_(question_ids)).all()
        total_questions = len(questions)
        cur_score = 0
        for q in questions:
            # 1. Identify the actual correct text from the static DB setup
            current_correct_letter = q.correct_answer.lower()
            current_correct_key = f"option_{current_correct_letter}"
            correct_text = getattr(q, current_correct_key)

            # 2. Get the specific text value submitted by the user for this ID
            submitted_text = answers.get(str(q.id))

            # 3. Grade the answer based on option text comparison
            if submitted_text == correct_text:
                answers[str(q.id)] = 'correct'
                cur_score += 1
            else:
                answers[str(q.id)] = 'incorrect'

        row = QuizScore.query.filter_by(student_id=session['user_id'], chapter=chapter).scalar()
        if row:
            row.total_questions += cur_total
            row.score += cur_score
            row.timestamp = datetime.now(timezone.utc)
        else:
            new_score = QuizScore(
                student_id=session['user_id'],
                chapter=chapter,
                score=cur_score,
                total_questions=cur_total
            )
            db.session.add(new_score)

        db.session.commit()
        current_score = f'{float(cur_score / cur_total * 100):.0f} %'

    # Get all quiz attempts
    student = QuizScore.query.filter_by(student_id=session['user_id'], chapter=chapter).scalar()
    if student:
        total_questions = student.total_questions
        score = student.score
        all_score_percentage = f'{float(score / total_questions * 100):.0f} %'
    else:
        all_score_percentage = 'No Attempts'

    return jsonify(
        {"success": True,
         "current_score": current_score,
         "overall_score": all_score_percentage,
         "correct_answers": answers
         })

@routes.route('/api/student/progress', methods=['GET'])
def get_student_progress():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401

    chapter_num = request.args.get('chapter', type=int)
    verse_num = request.args.get('verse', type=int)

    # Count total comments posted by this student
    total_comments = Comment.query.filter_by(student_id=session['user_id'], verse_id=verse_num).count()

    # Get all quiz attempts
    scores = QuizScore.query.filter_by(student_id=session['user_id'], chapter=chapter_num).order_by(QuizScore.timestamp.desc()).all()
    attended = 0
    score = 0
    for s in scores:
        attended += s.total_questions
        score += s.score
    if attended == 0:
        score_percentage = 'No Attempts'
    else:
        score_percentage = f'{float(score / attended * 100):.2f}%'
    return jsonify({
        "success": True,
        "total_comments": total_comments,
        "score_percentage": score_percentage

    })