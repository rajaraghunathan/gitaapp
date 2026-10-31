# Helper File to Inject the YouTube link
import os, csv, ast, re
from sqlalchemy import create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker
from models import Verse, GlossaryFaq, Chapter

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
    sumary = {'num': 2,
               'ta': 'இந்த அத்தியாயத்திற்கு <b>ஸாங்க்யயோகம்</b> என்று பெயர்‌ கூறப்படுகிறது. <b>‘ஸங்க்யை’</b> என்பது <b>‘புத்தி’</b>. புத்தியால் அறியப்படும்‌ நித்யமான ஆத்மதத்துவம்‌ ஸாங்க்யம் எனப்படுகிறது. <b>“யோக₃ ஸநநஹநோபாய”</b> என்கிற நிகண்டுவின் படி <b>யோக₃ ஶப்தம் உபாயத்தைக்‌ குறிக்கிறது</b>. இங்கு முதலில் ஸாங்க்யம் எனப்பட்ட நித்யமான ஆத்மதத்துவத்தை அடையும்‌ வழியான கர்மயோகம்‌ கூறப்படுகிறது. பற்று வைக்காமல்‌ செய்யப்படும் கர்மாநுஷ்டானமாகிற இக்கர்மயோக₃த்தைப் பற்றிய அறிவும்‌, ஸாங்க்யம்‌ எனப்படும்‌, ஆத்மதத்வத்தைப் பற்றிய அறிவும்‌ இவ்வத்தியாயத்தில்‌ கூறப்படுகின்றன. <b>“ஏஷா தே பி₄ஹிதா ஸாங்க்₂யே பு₄த்₃தி₄ர்யோகே₃, த்விமாம்‌ ச்ருணு” [கீதை 2-39]</b> [ஸாங்க்யமாகிற ஆத்மதத்துவத்தைப் பற்றிச்‌ சொல்ல வேண்டியதைச்‌ சொல்ல விட்டேன்‌? யோக விஷயத்தில்‌ இனிவரும்‌ வார்த்தைகளைக்‌ கேட்பாயாக] என்கிற சலோகத்திற்கு முன்‌ பல சுலோகங்களில்‌ ஆத்மதத்துவத்தைப் பற்றிய அறிவும்‌, பின்‌ சுலோகங்கள்‌ பலவற்றில்‌ கர்மயோகத்தைப் பற்றிய அறிவும்‌ கூறப்படுகின்றன. அதற்குப்பின்‌ இக்‌கர்மயோக அநுஷ்டானத்தால் இச்சேதனனுக்கு <b>ஸ்தி₂தப்ரஜ்ஞை</b> நிலையொன்று ஏற்படுகிறது (இதுவே ஜ்ஞாநயோகம்‌ எனப்படுகிறது) என்பதும்‌ இந்த ஜ்ஞாநயோகத்தால்‌ ஆத்ம ஸாக்ஷாத்காரம்‌ ஏற்படுகிறது என்பதும், இவ்வத்தியாயத்தில்‌ அர்ஐுனனின்‌ மயக்கம்‌ தெளிவதற்காகக்‌ கூறப்படுகின்‌றன.'
                }
    cleaned_text = sumary.get('ta').replace('\u200c', '')
    chapter = db.query(Chapter).filter(Chapter.num == sumary.get('num')).scalar()
    chapter.summary['ta'] = cleaned_text
    db.commit()
    print ('Data added Successfully')
    chapter = db.query(Chapter).filter(Chapter.num == sumary.get('num')).scalar()
    print(chapter.summary['ta'])

if __name__ == '__main__':
    db_path = os.path.join(BASE_DIR, 'gita.db')
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db_operations()
        # yt_inject_db()
    except Exception as e:
        db.rollback()
        print(f"Error occurred, rolling back: {e}")
        raise e
    finally:
        db.close()  # Always terminate the session to release file locks
        print('Database Closed Successfully')