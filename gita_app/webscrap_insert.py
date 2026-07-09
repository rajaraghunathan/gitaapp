import re, pprint, os, json
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import declarative_base, sessionmaker
from models.gitamodels import Verse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_INPUT_PATH = os.path.join(BASE_DIR, "json using codes", "chapter6_webscrap.json")

with open(JSON_INPUT_PATH, "r", encoding="utf-8") as f:
    original_list = json.load(f)

parsed_data = []

for idx, dict_item in enumerate(original_list):
    verse_text = dict_item.get('words')
    chapter = dict_item.get('chapter')
    verse = dict_item.get('verse')
    meaning = dict_item.get('translation')
    dash_pairs = verse_text.count('---')
    comma_pairs = verse_text.count(';')

    if comma_pairs != dash_pairs-1:
        print(f'dash: {dash_pairs-1} semicolon: {comma_pairs} ---- Mismatch at Ch{chapter}.Ver{verse}.')
        # print(f"Mismatch at Ch{chapter}.Ver{verse}. Executing next list.")
        continue  # This safely skips the rest of this loop iteration

    # 3. Split the text blob by commas into individual word pairs
    raw_word_pairs = verse_text.split(';')

    anvayam = []
    for item in raw_word_pairs:
        item = item.strip()
        if not item:
            continue

        # 4. Split each specific word pair into Sanskrit and Tamil by the hyphen
        if '---' in item:
            # split(..., 1) ensures we only split on the first hyphen found
            parts = item.split('---')
            sanskrit_word = parts[0].strip()
            tamil_meaning = parts[1].strip()
            # Append everything into our structured list
            anvayam.append({
                "en": tamil_meaning,
                "sa": sanskrit_word
            })

    # print(f'text length: {dash_pairs} anvayam length: {len(anvayam)}')
    # proceed = input('Continue to append ?')
    parsed_data.append({
        "chapter": chapter,
        "verse": verse,
        "anvayam": anvayam,
        "meaning": meaning.strip()
    })

# Print out results to see the clean dictionary mapping
pprint.pprint(parsed_data[:2])  # Displays first 5 structured items


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, 'gita.db')
engine = create_engine(f"sqlite:///{db_path}", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
Base.metadata.create_all(bind=engine)
db = SessionLocal()

try:
    for row in parsed_data:
        chapter_num = row['chapter']
        verse_num = row['verse']
        anvayam = row['anvayam']
        meaning = row['meaning']

        verse = db.query(Verse).where(Verse.chapter_number == chapter_num, Verse.verse_number == verse_num).scalar()
        database_meaning = verse.meaning
        if not database_meaning.get('ta'):
            verse.meaning['ta'] = {
                'anvayam': anvayam,
                'description': meaning,
                'footnotes': {}
            }
            print(f'data loaded for {chapter_num}-{verse_num}')
    db.commit()
except Exception as e:
        db.rollback()
        print(f"Error occurred, rolling back: {e}")
        raise e
finally:
    db.close()  # Always terminate the session to release file locks



# app = app
# with ((app.app_context())):
#     for row in parsed_data:
#         chapter_num = row['chapter']
#         verse_num = row['verse']
#         anvayam = row['anvayam']
#         meaning = row['meaning']
#
#         verse = db.session.execute(
#             db.select(Verse).where(Verse.chapter_number == chapter_num, Verse.verse_number == verse_num)
#         ).scalar()
#
#         database_meaning = verse.meaning
#         if not database_meaning.get('ta'):
#             verse.meaning['ta'] = {
#                 'anvayam': anvayam,
#                 'description': meaning,
#                 'footnotes':{}
#             }
#             print(f'data loaded for {chapter_num}-{verse_num}')
#     db.session.commit()
#         # pprint.pprint(database_meaning)



