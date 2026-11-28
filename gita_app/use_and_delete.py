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

def some_function():
    # record = db.query(Verse).where(Verse.chapter_number==5).all()[0]
    # db_data = {
    #     k: v for k, v in record.__dict__.items() if not k.startswith('_')
    # }
    # print(db_data)
    cache_file = os.path.join(BASE_DIR, "json using codes", "acharya_translations_cache.json")
    with open(cache_file, 'r', encoding='utf-8') as f:
        local_cache = json.load(f)
    new_dict = {}
    for key1, val1 in local_cache.items():
        for key2, val2 in val1.items():
            new_dict.update({f'{key1}_{key2}': val2})
    output_file = os.path.join(BASE_DIR, "json using codes", "acharya_translations_cache_new.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(new_dict, f, ensure_ascii=False, indent=4)

if __name__ == '__main__':
    some_function()

    # db_path = os.path.join(BASE_DIR, 'gita.db')
    # engine = create_engine(f"sqlite:///{db_path}", echo=False)
    # SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # metadata = MetaData()
    # Base = declarative_base()
    # Base.metadata.create_all(bind=engine)
    #
    # with SessionLocal() as db:
    #     try:
    #
    #         # db_operations()
    #         # yt_inject_db()
    #         # export_data()
    #         # merge_data()
    #     except Exception as e:
    #         db.rollback()
    #         print(f"Error occurred, rolling back: {e}")
    #         raise e