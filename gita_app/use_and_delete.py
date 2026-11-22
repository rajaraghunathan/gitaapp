# Helper File to Inject the YouTube link
import os, csv, ast, json, requests
from sqlalchemy import create_engine, text, Table, MetaData, func
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from models import Chapter, Student, Verse, AcharyaComment, Comment, QuizQuestion, QuizQuestionTamil, GlossaryFaq
from testing import batch_translate_mymemory
from translate import batch_translate_list_azure

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def yt_inject_db():
    csv_folder = os.path.join(BASE_DIR, "static", "csv_files")
    files = os.listdir(csv_folder)
    for file in files:
        if file.startswith("BG_"):
            csv_path = os.path.join(csv_folder, file)
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            print(f'Writing Glossary for {file} to database')
            print('=='*30)
            chapter_ini = 1
            for index, row in enumerate(rows):
                ch = int(row.get('Chapter'))
                ver = int(row.get('Verse'))
                new_glossary = GlossaryFaq(
                    chapter = ch,
                    verse = ver,
                    type = row.get('type'),
                    question = ast.literal_eval(row.get('question')),
                    answer = ast.literal_eval(row.get('answer'))
                )
                db.add(new_glossary)
                if ch != chapter_ini:
                    print(f'data added for Chapter - {chapter_ini}')
                    chapter_ini = chapter_ini + 1

            db.commit()
            print('**' * 30)

def db_operations ():
    table = GlossaryFaq
    chapter_num = 18
    glossary = db.query(table).where(table.chapter == chapter_num,
                                             table.type == 'glossary').order_by(table.id).all()
    db_data = [{
        k: v for k, v in q.__dict__.items() if not k.startswith('_')
    } for q in glossary]
    print(len(glossary), db_data[:2])

    ids = []
    answers = []
    for g in glossary:
        ids.append(g.id)
        answers.append(g.answer.get('en', ''))

    ans_ta, is_true = batch_translate_list_azure(answers, 'en', 'ta')
    # ans_ta = batch_translate_mymemory(answers)
    if len(ans_ta) == 0:
        print('Translation Error')
        return None
    glossary_map = {item.id: item for item in glossary}
    updated_ids = []
    for idx, ta in enumerate(ans_ta):
        record = glossary_map.get(ids[idx])
        if record:
            record.answer['ta'] = ta
            flag_modified(record,'answer')
            if isinstance(record.question, dict) and 'en' in record.question:
                updated_q = dict(record.question)
                updated_q['sa'] = updated_q.pop('en')
                record.question = updated_q
            updated_ids.append(ids[idx])
        else:
            print(f"ID not found in DB: {ids[idx]}")
    if updated_ids:
        print(f"Updated {len(updated_ids)} records:")
        db.commit()

    return True

def export_data ():
    table = GlossaryFaq
    col_name = 'chapter'
    filter_criteria = '3'
    try:
        criteria = int(filter_criteria)
    except ValueError:
        criteria = filter_criteria
    print(criteria)
    # if hasattr(table, col_name):
    #     verse = db.query(table).where(getattr(table, col_name) == filter_criteria).all()
    # else:
    #     print(f"Error: {col_name} is not a valid column name on {table.__name__}")
    #     verse = []
    # table_name = table.__tablename__
    # data = {'table_name': table_name, 'col_name': col_name, 'filter_criteria': filter_criteria, 'table_data':[]}
    # for v in verse:
    #     temp_data = {k: v for k, v in v.__dict__.items() if not k.startswith('_')}
    #     data['table_data'].append(temp_data)
    # today_date = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    # file_name_construct = f"local_db_{col_name}_{filter_criteria}_{table_name}_{today_date}.json"
    # json_path = os.path.join(BASE_DIR, "static", "json_files", file_name_construct)
    #
    # with open(json_path, "w", encoding="utf-8") as f:
    #     json.dump(data, f, indent=2, ensure_ascii=False)

def merge_data ():
    # flag_modified(verse, 'meaning')
    file_id = '1viadTOf88mAKmYdCLWYwLNjDO1lqFben'
    # data = download_public_json(file_id)
    json_path = os.path.join(BASE_DIR, "json using codes", f"CH2_verse_data.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    table_class = {'chapter': Chapter, 'verse': Verse,
                   'acharya_comment': AcharyaComment, 'quiz_question': QuizQuestion,
                   'quiz_question-tamil': QuizQuestionTamil, 'glossary_faq': GlossaryFaq}
    db_table = table_class.get(data.get('table_name'))
    incoming_table = data.get('table_data', [])
    incoming_col = data.get('col_name')
    incoming_filter = data.get('filter_criteria')

    # 1. Map the incoming records by their unique ID
    incoming_records_map = {row['id']: row for row in incoming_table}
    incoming_ids = set(incoming_records_map.keys())

    # 2. Fetch all current records from the main DB for this scope (e.g., Chapter 2)
    # Fetching them all at once avoids running a slow query inside a loop
    existing_records = db.query(db_table).where(getattr(db_table, incoming_col) == incoming_filter).all()
    existing_records_map = {record.id: record for record in existing_records}
    existing_ids = set(existing_records_map.keys())
    ids_to_delete = existing_ids - incoming_ids
    ids_to_update = existing_ids & incoming_ids
    ids_to_insert = incoming_ids - existing_ids

    print(f'ids_to_insert: {len(ids_to_insert)}')
    print(f'ids_to_delete: {len(ids_to_delete)}')
    print(f'ids_to_update: {len(ids_to_update)}')

    record_same = []
    record_diff = []
    record_new = []
    record_deleted = []

    # --- PHASE 1: HANDLE DELETIONS ---
    for record_id in ids_to_delete:
        print(existing_records_map[record_id])
        # db.delete(existing_records_map[record_id])
        record_deleted.append(record_id)
    # db.flush()
    # --- PHASE 2: HANDLE UPDATES ---
    for record_id in ids_to_update:
        current_record = existing_records_map[record_id]
        new_data = incoming_records_map[record_id]

        for key, value in new_data.items():
            if key != 'id' and getattr(current_record, key) != value:
                # setattr(current_record, key, value)
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
        # db.add(new_record)
        record_new.append(record_id)

    print('Merging Data to DB')
    print(f'{len(existing_records)} records found')
    print(f'{len(record_same)} records are same')
    print(f'{len(record_diff)} records are updated. Updated ids are {record_diff}')
    print(f'{len(record_new)} records are inserted. Inserted ids are {record_new}')
    print(f'{len(record_deleted)} number of records are deleted. Deleted ids are {record_deleted}')

    # if len(record_diff) + len(record_new) + len(record_deleted) > 0:
    #     db.commit()
    #     print("Successfully synced all inserts, updates, and deletes! in Data Base")

def download_public_json(file_id):
    """Downloads a publicly shared file from Google Drive without authentication."""
    print("Downloading JSON from Google Drive...")
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(url, timeout=30)
    # response.raise_for_status()
    if response.status_code == 200:
        data = response.json()
        return data
    else:
        raise Exception(f"Failed to download file. Status code: {response.status_code}")

if __name__ == '__main__':
    db_path = os.path.join(BASE_DIR, 'gita.db')
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    metadata = MetaData()
    Base = declarative_base()
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        try:
            # db_operations()
            # yt_inject_db()
            export_data()
            # merge_data()
        except Exception as e:
            db.rollback()
            print(f"Error occurred, rolling back: {e}")
            raise e