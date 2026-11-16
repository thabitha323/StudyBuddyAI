
from flask import Flask, render_template, request, redirect, session, flash
from models import db, User, Upload, QuizScore
from werkzeug.utils import secure_filename
from google import genai
from dotenv import load_dotenv

import os
import pymupdf
import json
import random
import time

# Load Environment Variables
load_dotenv(override=True)

# Flask Setup
app = Flask(__name__)
app.secret_key = "studybuddy_secret_key"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///studybuddy.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# PDF Folder
UPLOAD_FOLDER = "pdf_files"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database Setup
db.init_app(app)

with app.app_context():
    db.create_all()

# GOOGLE GEMINI CONFIGURATION
# ==========================================

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found in .env file")

print("Gemini API Key Loaded:", bool(api_key))

client = genai.Client(api_key=api_key)

MODEL_NAME = "gemini-3.5-flash-lite"
print("Gemini Model:", MODEL_NAME)


# ==========================================
# COMMON AI FUNCTION
# ==========================================

def ask_ai(prompt):
    max_attempts = 2

    for attempt in range(max_attempts):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt
            )

            if response and response.text:
                return response.text.strip()

            print("Gemini returned empty response.")

        except Exception as e:
            error_message = str(e).upper()
            print("Gemini AI ERROR:", type(e).__name__, e)

            retryable = any(
                error in error_message
                for error in [
                    "503", "429", "500",
                    "502", "504",
                    "UNAVAILABLE",
                    "RESOURCE_EXHAUSTED"
                ]
            )

            if not retryable or attempt == max_attempts - 1:
                return None

            print("Retrying Gemini API...")
            time.sleep(2)

    return None
    

# ==========================================
# HOME PAGE
# ==========================================

# ==========================================
# HOME PAGE
# ==========================================

@app.route("/")
def home():
    return render_template("index.html")


# ==========================================
# REGISTER
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        fullname = request.form["fullname"]
        email = request.form["email"]
        password = request.form["password"]

        existing = User.query.filter_by(email=email).first()

        if existing:
            flash("Email already exists.")
            return redirect("/register")

        user = User(
            fullname=fullname,
            email=email,
            password=password
        )

        db.session.add(user)
        db.session.commit()

        flash("Registration Successful!")
        return redirect("/login")

    return render_template("register.html")


# ==========================================
# LOGIN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and user.password == password:
            session["user_id"] = user.id
            session["user_name"] = user.fullname
            print("LOGIN SUCCESS")
            return redirect("/dashboard")

        print("LOGIN FAILED - USER OR PASSWORD NOT MATCHED")
        flash("Invalid Email or Password")
        return render_template("login.html")

    return render_template("login.html")

@app.route("/logout")
def logout():

    session.clear()
    return redirect("/")


# ==========================================
# DASHBOARD
# ==========================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect("/login")

    return render_template(
        "dashboard.html",
        username=session["user_name"]
    )


# ==========================================
# PDF UPLOAD AND AI SUMMARY
# ==========================================

@app.route("/upload", methods=["GET", "POST"])
def upload():

    if "user_id" not in session:
        return redirect("/login")

    message = ""

    if request.method == "POST":
        file = request.files.get("pdf")

        if not file or file.filename == "":
            message = "Please select a PDF."

        elif not file.filename.lower().endswith(".pdf"):
            message = "Please upload a PDF file."

        else:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)

            try:
                file.save(filepath)

                with pymupdf.open(filepath) as pdf:
                    pdf_text = "\n".join(
                        page.get_text() for page in pdf
                    )

                if not pdf_text.strip():
                    message = "No readable text found in this PDF."

                else:
                    session["pdf_text"] = pdf_text[:2500]

                    record = Upload(
                        filename=filename,
                        user_id=session["user_id"]
                    )

                    db.session.add(record)
                    db.session.commit()

                    message = "PDF Uploaded Successfully! Go to AI Summary."

            except Exception as e:
                db.session.rollback()
                print("PDF ERROR:", e)
                message = f"PDF Error: {e}"

    return render_template(
        "upload.html",
        summary="",
        message=message
    )
@app.route("/summary", methods=["GET", "POST"])
def summary():

    if "user_id" not in session:
        return redirect("/login")

    summary_text = ""

    if request.method == "POST":

        pdf_text = session.get("pdf_text", "")

        if not pdf_text:
            summary_text = "Please upload a PDF first."
        else:
            prompt = (
                "Generate a simple, clear study summary "
                "with important points and headings:\n"
                + pdf_text[:3000]
            )

            summary_text = ask_ai(prompt)

            if not summary_text:
                summary_text = (
                    "Gemini AI could not generate the summary. "
                    "Please check your API quota and try again later."
                )

        else:
            prompt = f"""
            Read this PDF content and generate
            a clear study summary.

            Use simple English.
            Explain the important concepts.

            PDF CONTENT:
            {pdf_text}
            """

            summary_text = ask_ai(prompt)

            if not summary_text:
                summary_text = "AI could not generate the summary."

    return render_template(
        "summary.html",
        summary=summary_text
    )

@app.route("/chatbot", methods=["GET", "POST"])
def chatbot():

    if "user_id" not in session:
        return redirect("/login")

    answer = ""

    if request.method == "POST":

        question = request.form.get(
            "question", ""
        ).strip()

        if question:

            prompt = f"""
            You are StudyBuddy AI.

            Answer the student's question
            clearly and in simple English.

            QUESTION:
            {question}
            """

            answer = ask_ai(prompt)

            if not answer:
                answer = "AI could not generate an answer. Please try again."

    return render_template(
        "chatbot.html",
        answer=answer
    )


# ==========================================
# QUIZ GENERATOR
# ==========================================

def generate_quiz(topic):

    prompt = f"""
    You are StudyBuddy AI.

    Create exactly 10 multiple-choice questions
    about this topic:

    {topic}

    Return ONLY valid JSON.

    Format:
    [
        {{
            "question": "Question text?",
            "options": [
                "Option 1",
                "Option 2",
                "Option 3",
                "Option 4"
            ],
            "answer": 0
        }}
    ]

    Rules:
    - Generate exactly 10 questions.
    - Each question must have 4 options.
    - Answer must be a number from 0 to 3.
    - Return JSON only.
    """

    try:
        result = ask_ai(prompt)

        if not result:
            return []

        result = result.strip()

        if result.startswith("```"):
            result = result.split("\n", 1)[-1]

        if result.endswith("```"):
            result = result[:-3].strip()

        questions = json.loads(result)

        if not isinstance(questions, list):
            return []

        valid_questions = []

        for q in questions[:10]:

            if not isinstance(q, dict):
                continue

            options = q.get("options")
            answer = q.get("answer")
            question_text = q.get("question")

            if not isinstance(options, list) or len(options) != 4:
                continue

            if not question_text:
                continue

            try:
                answer = int(answer)
            except (TypeError, ValueError):
                continue

            if answer not in range(4):
                continue

            options = list(options)
            correct_answer = options[answer]

            random.shuffle(options)

            q["options"] = options
            q["answer"] = options.index(correct_answer)

            valid_questions.append(q)

        return valid_questions if len(valid_questions) == 10 else []

    except Exception as e:
        print("QUIZ ERROR:", e)
        return []


# ==========================================
# QUIZ PAGE
# ==========================================

@app.route("/quiz", methods=["GET", "POST"])
def quiz():

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":

        if request.form.get("submit_quiz") == "yes":

            questions = session.get("quiz_data", [])

            if not questions:
                flash("Please generate a new quiz.")
                return redirect("/quiz")

            score = 0

            for i, q in enumerate(questions):

                selected = request.form.get(f"question_{i}")

                if selected is not None:
                    try:
                        if int(selected) == q["answer"]:
                            score += 1
                    except (ValueError, TypeError):
                        continue

            try:
                result = QuizScore(
                    user_id=session["user_id"],
                    score=score
                )

                db.session.add(result)
                db.session.commit()

            except Exception as e:
                db.session.rollback()
                print("QUIZ SCORE ERROR:", e)

            session["quiz_submitted"] = True
            session["quiz_score"] = score

            return render_template(
                "quiz.html",
                questions=questions,
                score=score,
                total=len(questions)
            )

        topic = request.form.get("topic", "").strip()

        if not topic:
            flash("Please enter a quiz topic.")
            return redirect("/quiz")

        questions = generate_quiz(topic)

        if questions:

            session["quiz_data"] = questions
            session["quiz_submitted"] = False

            return render_template(
                "quiz.html",
                questions=questions,
                score=None,
                total=len(questions)
            )

        flash("Quiz could not be generated. Please try again.")

    return render_template(
        "quiz.html",
        questions=[],
        score=None,
        total=0
    )


# ==========================================
# UPLOAD HISTORY
# ==========================================

@app.route("/history")
def history():

    if "user_id" not in session:
        return redirect("/login")

    uploads = Upload.query.filter_by(
        user_id=session["user_id"]
    ).all()

    return render_template(
        "history.html",
        uploads=uploads
    )


# ==========================================
# FLASHCARDS
# ==========================================

@app.route("/flashcards", methods=["GET", "POST"])
def flashcards():

    if "user_id" not in session:
        return redirect("/login")

    cards = []

    if request.method == "POST":

        topic = request.form.get("topic", "").strip()

        if not topic:
            flash("Please enter a topic.")
            return redirect("/flashcards")

        prompt = f"""
        You are StudyBuddy AI.

        Explain {topic} using 10 informative
        study paragraphs.

        Use simple English.
        Each paragraph should explain
        one important concept.
        """

        result = ask_ai(prompt)

        if result:
            cards = [
                paragraph.strip()
                for paragraph in result.split("\n\n")
                if paragraph.strip()
            ]
        else:
            cards = ["AI could not generate flashcards. Please try again."]

    return render_template(
        "flashcards.html",
        flashcards=cards
    )


# ==========================================
# RUN FLASK APPLICATION
# ==========================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
