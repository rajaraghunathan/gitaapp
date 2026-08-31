# Inject the YouTube link to Data Base
import os, csv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from models import Verse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def list_files():
    csv_path = os.path.join(BASE_DIR, "static", "csv_files")
    files = os.listdir(csv_path)
    return files

def yt_inject_db(lang):
    files = list_files()
    for file in files:
        csv_path = os.path.join(BASE_DIR, "static", "csv_files", file)
        if not os.path.exists(csv_path):
            print(f'{csv_path} does not exist')
            continue
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        print(f'Writing YouTube Urls for {file} to database for {lang}')
        print('='*30)

        for index, row in enumerate(rows):
            chapter_num = int(row['Chapter'])
            verse_num = int(row['Verse'])
            url = row['URL']
            author = row['Author']

            verse = db.query(Verse).where(
                Verse.chapter_number == chapter_num, Verse.verse_number == verse_num).scalar()

            database_url = verse.youtube_url
            dict_ta = database_url.get(lang)
            if dict_ta:
                if dict_ta.get(author):
                    print(f'{author} exists for {chapter_num}-{verse_num} and Skipped for language {lang}')
                else:
                    dict_ta.update({author: url})
                    print(f'youtube Url for {author} updated for {chapter_num}-{verse_num} for language {lang}')
            else:
                dict_ta[lang] ={author: url}
                print(f'youtube Url updated for {chapter_num}-{verse_num} for language {lang}')
            database_url[lang] = dict_ta
        db.commit()
    return None

if __name__ == '__main__':
    db_path = os.path.join(BASE_DIR, 'gita.db')
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yt_inject_db('ta')
    except Exception as e:
        db.rollback()
        print(f"Error occurred, rolling back: {e}")
        raise e
    finally:
        db.close()  # Always terminate the session to release file locks
        print('Database Closed Successfully')