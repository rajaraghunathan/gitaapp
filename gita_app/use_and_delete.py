# Helper File to Inject the YouTube link
import os, csv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from models import Verse

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
            print(f'Writing Pada, Sandhi and Anvayam for {file} to database')
            print('=='*30)

            for index, row in enumerate(rows):
                chapter_num = int(row['Chapter'])
                verse_num = int(row['Verse'])
                pada = row['Pada']
                sandhi = row['Sandhi']
                anvayam = row['Anvayam']

                verse = db.query(Verse).where(
                    Verse.chapter_number == chapter_num, Verse.verse_number == verse_num).scalar()

                shloka = verse.shlok
                if shloka.get("padached"):
                    print(f'Anvayam details Exist for Shloka {chapter_num}-{verse_num}')
                else:
                    shloka['padached'] = pada
                    shloka['sandhi'] = sandhi
                    shloka['anvayam'] = anvayam
                    print(f'Anvayam details Created for Shloka {chapter_num}-{verse_num}')
            db.commit()
            print('**' * 30)

if __name__ == '__main__':
    db_path = os.path.join(BASE_DIR, 'gita.db')
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yt_inject_db()
    except Exception as e:
        db.rollback()
        print(f"Error occurred, rolling back: {e}")
        raise e
    finally:
        db.close()  # Always terminate the session to release file locks
        print('Database Closed Successfully')