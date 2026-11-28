import os, json, random, re, csv
from flask import Blueprint, jsonify, request, session, url_for
from database import db
from models import Student, Verse, Comment, AcharyaComment, QuizQuestion, QuizScore, QuizQuestionTamil, GlossaryFaq
from datetime import datetime, timezone
from translate import dynamic_sanskrit_transliterate, translate_api_groq, remove_non_printable_from_object #customized function
from zoneinfo import ZoneInfo
from .admin import read_json_from_drive, update_json_in_drive

routes = Blueprint("routes", __name__)

# Define path for the local cache file
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) #Current File Directory
BASE_DIR = os.path.dirname(CURRENT_DIR) #One Level Up to Next Directory
ACHARYA_DRIVE_FILE_ID = '13yHOQYEK7XNySo0nHE8zk0-d-csWxxQ8'
MEANING_DRIVE_FILE_ID = '10uBr8FZycvzmb3cAZzByToOq1IBt9nde'

def safe_translate_description_and_anvayam (cache_key, v_dict, lang):
    # cache_file = os.path.join(BASE_DIR, "json using codes", "mean_translations_cache.json")
    # with open(cache_file, 'r', encoding='utf-8') as f:
    #     local_cache = json.load(f)
    local_cache = read_json_from_drive(MEANING_DRIVE_FILE_ID)
    if cache_key in local_cache:
        v_dict["meaning"] = {lang: local_cache[cache_key]}
        v_dict["translated"] = "yes"
        print(f"⚡ Cache Hit! Shloka {cache_key} in {lang} loaded from disk.")
        return v_dict
    else:
        # CASE: Completely missing -> Perform Native Batch Translation
        # If requested not available skipping the translation route and loading default en content
        # v_dict["meaning"] = {'en': v_dict["meaning"]['en']}
        # v_dict["translated"] = "no"
        # return v_dict
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
            translated = translate_api_groq(strings_to_translate, lang)
            if isinstance(translated, str):
                print({"error": f"Translation pipeline failed: {translated}"})
                return v_dict

        # Step 2: Rebuild the nested dictionary mapping the translated items back safely
        string_iterator = iter(translated)

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
        for item in  translated_content.get('anvayam',[]):
            word = item.get('sa')
            item['sa'] = dynamic_sanskrit_transliterate(word,lang)

        # Save permanently to local JSON file cache
        local_cache[cache_key] = translated_content
        update_json_in_drive(MEANING_DRIVE_FILE_ID, local_cache)
        # with open(cache_file, 'w', encoding='utf-8') as f:
        #     json.dump(local_cache, f, ensure_ascii=False, indent=4)
        print(f"💾 Saved Shloka Translation: {cache_key} ({lang}) to cache.")

        # Format and return the filtered dictionary
        v_dict["meaning"] = {lang: translated_content}
        v_dict["translated"] = "yes"
        return v_dict

@routes.route('/api/singleverse', methods=['GET']) #Finalised & Working
def get_single_verse_user():
    if 'user_id' in session:
        chapter_number = request.args.get('chapter', type=int)
        verse_number = request.args.get('verse', type=int)

        lang = request.args.get('language', 'en')
        if not lang: return jsonify({"error": "Missing lang parameter"}), 400

        verse = (db.session.query(Verse)
                 .where(Verse.chapter_number == chapter_number, Verse.verse_number == verse_number)
                 .scalar())
        if not verse: return jsonify({"error": "Verse not found"}), 404

        v_dict = {k: v for k, v in verse.__dict__.items() if not k.startswith('_')}

        # shloka_sa = v_dict["shloka"]
        shloka = v_dict["shlok"].get('shloka')
        padached = v_dict["shlok"].get('padached', '')
        sandhi = v_dict["shlok"].get('sandhi','')
        anvayam = v_dict["shlok"].get('anvayam', '')
        indic_lang = 'devanagari' if lang == 'hi' else lang
        v_dict["shlok"] = [
            {'shloka': dynamic_sanskrit_transliterate(shloka, indic_lang)},
            {'padached': dynamic_sanskrit_transliterate(padached, indic_lang)},
            {'sandhi': dynamic_sanskrit_transliterate(sandhi, indic_lang)},
            {'anvayam': dynamic_sanskrit_transliterate(anvayam, indic_lang)}
        ]
        v_dict["audio_file"] = url_for('static', filename=f'audio/Ch{chapter_number}-{verse_number}.aac')

        # CASE A: Requested language is already available in the dictionary
        if lang in v_dict["meaning"]:
            # Keep ONLY the requested language inside the meaning dictionary
            v_dict["meaning"] = {lang: v_dict["meaning"][lang]}
            v_dict["translated"] = "no"
            return jsonify(v_dict)
        else:
            v_dict["meaning"] = {'en': v_dict["meaning"]['en']}
            v_dict["translated"] = "no"
            return v_dict

        # CASE B: Check local JSON file cache and if not Perform Tranlsation
        cache_key = f"{chapter_number}_{verse_number}_{lang}"
        translated_dict = safe_translate_description_and_anvayam(cache_key, v_dict, lang)
        return jsonify(translated_dict)
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

def safe_translate_acharya_comments(temp_dict, target_lang, ch, vs):
    ch_str = str(ch)
    vs_str = str(vs)
    # Reading Translation JSON File from Google Drive
    cache = read_json_from_drive(ACHARYA_DRIVE_FILE_ID)
    is_cache_changed = False

    for key in temp_dict.keys():
        text_str = temp_dict[key].strip()
        if (ch_str in cache and
                vs_str in cache[ch_str] and
                key in cache[ch_str][vs_str] and
                target_lang in cache[ch_str][vs_str][key]):
            print(f"⚡ Cache Hit! Chapter {ch} Verse {vs} ({key}) in {target_lang} loaded from disk.")
            temp_dict[key] = {}
            temp_dict[key] = {'author': f'Sri {key.capitalize()}'}
            if cache[ch_str][vs_str][key][target_lang].strip() == '':
                cache[ch_str][vs_str][key].pop(target_lang)
                is_cache_changed = True
                temp_dict[key][target_lang] = text_str
            else:
                temp_dict[key][target_lang] = cache[ch_str][vs_str][key][target_lang]
            temp_dict[key]['lang status'] = 'Translated From Sanskrit'
            continue
        if len(text_str) > 1000:
            translated = f"Large Text Characters (>1000) Cannot be Translated"
        else:
            translated = translate_api_groq([text_str], target_lang)
        if isinstance(translated, str) or len(translated) == 0:
            temp_dict[key] = {}
            temp_dict[key] = {'author': f'Sri {key.capitalize()}'}
            temp_dict[key][target_lang] = text_str
            temp_dict[key]['lang status'] = f'Translation Failed: {translated}'
        else:
            temp_dict[key] = {}
            temp_dict[key] = {'author': f'Sri {key.capitalize()}'}
            temp_dict[key][target_lang] = " ".join(remove_non_printable_from_object(translated))
            temp_dict[key]['lang status'] = 'Translated From Sanskrit'
            final_result = temp_dict[key][target_lang]
            if final_result != text_str:
                # Create empty parent objects on the fly if they don't exist yet
                if ch_str not in cache: cache[ch_str] = {}
                if vs_str not in cache[ch_str]: cache[ch_str][vs_str] = {}
                if key not in cache[ch_str][vs_str]: cache[ch_str][vs_str][key] = {}
                cache[ch_str][vs_str][key][target_lang] = final_result
                is_cache_changed = True
                print(f"💾 Saved Translation: Ch {ch} Vs {vs} [{key}] ({target_lang}) to cache.")

    #Updating Translation JSON File in Google Drive
    if is_cache_changed:
        update_json_in_drive(ACHARYA_DRIVE_FILE_ID, cache)

    return temp_dict

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
    temp_dict = {}
    acharya_dict = {}
    acharyas = ['ramanuja', 'sankara', 'madhava', 'desika', 'siva']

    for name in acharyas:
        source_data = row_dict.get(name) or {}
        acharya_dict[name] = {'author': f'Sri {name.capitalize()}'}
        text_in_requested_lang = source_data.get(lang)
        sanskrit_source_text = source_data.get('sa')

        if text_in_requested_lang:
            acharya_dict[name][lang] = text_in_requested_lang
            acharya_dict[name]['lang status'] = 'Default Content'
        elif sanskrit_source_text:
            acharya_dict[name][lang] = sanskrit_source_text
            acharya_dict[name]['lang status'] = 'Sanskrit Content'
            temp_dict[name] = sanskrit_source_text
        else:
            acharya_dict[name][lang] = source_data.get('en', '')
            acharya_dict[name]['lang status'] = 'No Translation'

    # processed_dict = safe_translate_acharya_comments(temp_dict, lang, chapter_number, verse_number)
    # for key in processed_dict.keys():
    #     acharya_dict[key] = processed_dict[key]
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

@routes.route('/api/student/glossary', methods=['GET'])
def get_glossary():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401
    lang = request.args.get('lang', 'en')
    chapter = request.args.get('chapter', type=int)
    table = GlossaryFaq
    glossary = db.session.query(table).where(table.chapter == chapter, db.func.json_type(table.answer, f'$.{lang}').is_not(None),
                                     table.type == 'glossary').order_by(table.id).all()
    if not glossary:
        return jsonify([])
    glossary_list = [{
        k: v for k, v in q.__dict__.items() if not k.startswith('_')
    } for q in glossary]
    for item in glossary_list:
        if item['question'].get('sa'):
            item['transliterated'] = dynamic_sanskrit_transliterate(item['question']['sa'], lang)
        else:
            item['transliterated'] = dynamic_sanskrit_transliterate(item['question']['en'], lang)
    return jsonify(glossary_list)

@routes.route('/api/student/faq', methods=['GET'])
def get_faq():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401
    lang = request.args.get('lang', 'en')
    chapter = request.args.get('chapter', type=int)
    table = GlossaryFaq
    faq = db.session.query(table).where(table.chapter == chapter, db.func.json_type(table.question, f'$.{lang}').is_not(None),
                                     table.type == 'faq').order_by(table.verse).all()
    if not faq:
        return jsonify([])
    faq_list = [{
        k: v for k, v in q.__dict__.items() if not k.startswith('_')
    } for q in faq]
    return jsonify(faq_list)

@routes.route('/api/student/other_glossary', methods=['GET'])
def get_other_glossary():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401
    input_file = os.path.join(BASE_DIR, "json using codes", "BG_Global_Glossary.json")
    with open(input_file, mode='r', encoding='utf-8') as infile:
        rows = json.load(infile)
    return jsonify(rows)