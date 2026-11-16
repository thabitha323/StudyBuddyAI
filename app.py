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

# Load environment variables
load_dotenv(override=True)

# Flask setup
app = Flask(__name__)
app.secret_key = "studybuddy_secret_key"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///studybuddy.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# PDF folder
UPLOAD_FOLDER = "pdf_files"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database setup
db.init_app(app)

with app.app_context():
    db.create_all()

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

MODEL_NAME = "gemini-3.5-flash-lite"
print("Gemini Model:", MODEL_NAME)


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
                    "503",
                    "429",
                    "500",
                    "502",
                    "504",
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

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        fullname = request.form["fullname"]
        email = request.form["email"]
        password = request.form["password"]

        existing = User.query.filter_by(email=email).first()

        if existing:
            flash("Email already exists")
            return redirect("/register")

        user = User(
            fullname=fullname,
            email=email,
            password=password
        )

        db.session.add(user)
        db.session.commit()

        flash("Registration Successful")
        return redirect("/login")

    return render_template("register.html")


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


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    return render_template(
        "dashboard.html",
        username=session["user_name"]
    )

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
        question = request.form.get("question", "").strip()

        if question:
            prompt = f"Answer this student question simply: {question}"
            answer = ask_ai(prompt)

            if not answer:
                answer = "AI could not generate an answer."

    return render_template(
        "chatbot.html",
        answer=answer
    )

def generate_quiz(topic):

    prompt = f"""
    Create exactly 10 multiple-choice questions about {topic}.

    Return only JSON in this format:
    [
        {{
            "question": "Question?",
            "options": ["One", "Two", "Three", "Four"],
            "answer": 0
        }}
    ]
    """

    try:
        result = ask_ai(prompt)

        if not result:
            return []

        result = result.replace("```json", "").replace("```", "").strip()
        questions = json.loads(result)

        valid_questions = []

        for q in questions[:10]:
            options = q["options"]
            answer = int(q["answer"])

            if len(options) != 4 or answer not in range(4):
                continue

            correct = options[answer]
            random.shuffle(options)

            q["answer"] = options.index(correct)
            valid_questions.append(q)

        return valid_questions if len(valid_questions) == 10 else []

    except Exception as e:
        print("Quiz Error:", e)
        return []


@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":

        if request.form.get("submit_quiz") == "yes":

            questions = session.get("quiz_data", [])
            score = 0

            for i, q in enumerate(questions):
                selected = request.form.get(f"question_{i}")

                if selected is not None:
                    if int(selected) == q["answer"]:
                        score += 1

            result = QuizScore(
                user_id=session["user_id"],
                score=score
            )

            db.session.add(result)
            db.session.commit()

            return render_template(
                "quiz.html",
                questions=questions,
                score=score,
                total=len(questions)
            )

        topic = request.form.get("topic", "").strip()

        if topic:
            questions = generate_quiz(topic)

            if questions:
                session["quiz_data"] = questions

                return render_template(
                    "quiz.html",
                    questions=questions,
                    score=None,
                    total=len(questions)
                )

        flash("Quiz could not be generated.")

    return render_template(
        "quiz.html",
        questions=[],
        score=None,
        total=0
    )


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


@app.route("/flashcards", methods=["GET", "POST"])
def flashcards():
    if "user_id" not in session:
        return redirect("/login")

    cards = []

    if request.method == "POST":
        topic = request.form.get("topic", "").strip()

        if topic:
            prompt = f"Explain {topic} in 10 simple study paragraphs."
            result = ask_ai(prompt)

            if result:
                cards = [
                    p.strip()
                    for p in result.split("\n\n")
                    if p.strip()
                ]

    return render_template(
        "flashcards.html",
        flashcards=cards
    )


if __name__ == "__main__":
    app.run(debug=True)