from database import db
from datetime import datetime, timedelta, timezone
from sqlalchemy import JSON
# ADD THIS LINE HERE:
from sqlalchemy.ext.mutable import MutableDict
import sqlalchemy as sa



class SQLiteAwareDateTime(sa.TypeDecorator):
    """Forces SQLite to handle datetimes as explicit UTC objects."""
    impl = sa.DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            # Force conversion to UTC and strip tzinfo so SQLite saves raw text safely
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            # When reading from the DB, append the UTC timezone info back
            return value.replace(tzinfo=timezone.utc)
        return value

# --- DATABASE MODELS ---
# 1. Structural Shloka Matrix Table
class Chapter(db.Model):
    __tablename__ = 'chapter'
    id = db.Column(db.Integer, primary_key=True) # Auto-incrementing PK
    num = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    summary = db.Column(MutableDict.as_mutable(JSON), nullable=True)

class Verse(db.Model):
    __tablename__ = 'verse'
    id = db.Column(db.Integer, primary_key=True) # Auto-incrementing PK
    chapter_number = db.Column(db.Integer, db.ForeignKey('chapter.num'), nullable=False)
    verse_number = db.Column(db.Integer, nullable=False)
    shloka = db.Column(db.Text, nullable=False) #In Original Devanagari
    meaning = db.Column(MutableDict.as_mutable(JSON), nullable=False)
    youtube_url = db.Column(MutableDict.as_mutable(JSON), nullable=True)
    # Connects verses to their respective student comments
    comments = db.relationship('Comment', backref='verse', lazy=True, cascade="all, delete-orphan")
    # CRITICAL: This makes the pair unique so BgComment can target it
    __table_args__ = (
        db.UniqueConstraint('chapter_number', 'verse_number', name='uq_chapter_verse'),
    )

class AcharyaComment(db.Model):
    __tablename__ = 'acharya_comment'
    id = db.Column(db.Integer, primary_key=True)  # Auto-incrementing PK
    ramanuja = db.Column(MutableDict.as_mutable(JSON), nullable=True)
    sankara = db.Column(MutableDict.as_mutable(JSON), nullable=True)
    madhava = db.Column(MutableDict.as_mutable(JSON), nullable=True)
    desika = db.Column(MutableDict.as_mutable(JSON), nullable=True)
    siva = db.Column(MutableDict.as_mutable(JSON), nullable=True)


    # Composite fields for the relationship
    chapter_number = db.Column(db.Integer, nullable=False)
    verse_number = db.Column(db.Integer, nullable=False)

    # Link the fields to the unique pair in verse
    __table_args__ = (
        db.ForeignKeyConstraint(
            ['chapter_number', 'verse_number'],
            ['verse.chapter_number', 'verse.verse_number']
        ),
    )

    # SQLAlchemy relationship works exactly the same way
    verse = db.relationship('Verse', backref='acharya_commentaries')


# 2. General User Identity Table
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # Plain text storage as requested
    # New Extended Profile Data Attributes
    age = db.Column(db.Integer, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    photo = db.Column(db.String(255), nullable=True, default='default_avatar.png')
    # State tracking: Stores the ID of the last viewed verse
    last_verse_id = db.Column(db.Integer, nullable=True)
    comments = db.relationship('Comment', backref='student', cascade='all, delete-orphan', lazy=True)

# 3. Community Commentary Table
class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    # FIX: Replaced datetime.utcnow with datetime.now(timezone.utc)
    # Note: Do not include parentheses () at the end of timezone.utc here,
    # as SQLAlchemy needs the function reference to call it when a new row is created.
    # timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    timestamp = db.Column(SQLiteAwareDateTime, default=lambda: datetime.now(timezone.utc),onupdate=lambda: datetime.now(timezone.utc))
    verse_id = db.Column(db.Integer, db.ForeignKey('verse.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)


class QuizQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chapter = db.Column(db.Integer, nullable=False)
    question = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(200), nullable=False)
    option_b = db.Column(db.String(200), nullable=False)
    option_c = db.Column(db.String(200), nullable=False)
    option_d = db.Column(db.String(200), nullable=False)
    correct_answer = db.Column(db.String(10), nullable=False)  # 'a', 'B', 'C', or 'D'

class QuizQuestionTamil(db.Model):
    __tablename__ = 'quiz_question-tamil'
    id = db.Column(db.Integer, primary_key=True)
    chapter = db.Column(db.Integer, nullable=False)
    question = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(200), nullable=False)
    option_b = db.Column(db.String(200), nullable=False)
    option_c = db.Column(db.String(200), nullable=False)
    option_d = db.Column(db.String(200), nullable=False)
    correct_answer = db.Column(db.String(10), nullable=False)  # 'a', 'B', 'C', or 'D'

class QuizScore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    chapter = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    # Establish relationship to access student details easily
    student = db.relationship('Student', backref=db.backref('scores', lazy=True))
