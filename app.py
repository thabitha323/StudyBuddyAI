from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    flash
)

from models import db, User, Upload, QuizScore
from werkzeug.utils import secure_filename
from openai import OpenAI
from dotenv import load_dotenv

import fitz
import os
import json
import random

load_dotenv()

# ==========================================
# Flask Configuration
# ==========================================

app = Flask(__name__)

app.secret_key = "studybuddy_secret_key"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///studybuddy.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# ==========================================
# Upload Folder
# ==========================================

UPLOAD_FOLDER = "pdf_files"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

db.init_app(app)

with app.app_context():
    db.create_all()

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


# ==========================================
# OpenRouter Configuration
# ==========================================

api_key = os.getenv("OPENROUTER_API_KEY")

if not api_key:
    raise ValueError(
        "OPENROUTER_API_KEY not found. "
        "Please check your .env file."
    )
print("API key Loaded:",bool(api_key))
client = OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1"
)

MODEL_NAME = "openai/gpt-oss-20b"


# ==========================================
# AI FUNCTION
# ==========================================

def ask_ai(prompt):

    try:

        response = client.chat.completions.create(
            model=MODEL_NAME,

            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            max_tokens=2000
        )

        return response.choices[0].message.content

    except Exception as e:

        print("AI Error:", e)

        return f"AI Error: {e}"


# ==========================================
# Home Page
# ==========================================

@app.route("/")
def home():

    return render_template("index.html")
# ==========================================
# Register
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        fullname = request.form["fullname"]
        email = request.form["email"]
        password = request.form["password"]

        existing = User.query.filter_by(
            email=email
        ).first()

        if existing:

            flash("Email already exists.")

            return redirect("/register")

        new_user = User(
            fullname=fullname,
            email=email,
            password=password
        )

        db.session.add(new_user)

        db.session.commit()

        flash("Registration Successful!")

        return redirect("/login")

    return render_template("register.html")


# ==========================================
# Login
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(
            email=email,
            password=password
        ).first()

        if user:

            session["user_id"] = user.id

            session["user_name"] = user.fullname

            return redirect("/dashboard")

        flash("Invalid Email or Password")

        return redirect("/login")

    return render_template("login.html")


# ==========================================
# Logout
# ==========================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# ==========================================
# Dashboard
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
# Upload PDF
# ==========================================

@app.route("/upload", methods=["GET", "POST"])
def upload():

    if "user_id" not in session:

        return redirect("/login")

    summary = ""

    message = ""

    if request.method == "POST":

        if "pdf" not in request.files:

            message = "No PDF Selected."

            return render_template(
                "upload.html",
                summary=summary,
                message=message
            )

        file = request.files["pdf"]

        if file.filename == "":

            message = "Choose a PDF."

            return render_template(
                "upload.html",
                summary=summary,
                message=message
            )

        filename = secure_filename(
            file.filename
        )

        filepath = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )

        file.save(filepath)

        text = ""

        try:

            pdf = fitz.open(filepath)

            for page in pdf:

                text += page.get_text()

            pdf.close()

            # Save PDF text in session
            session["pdf_text"] = text

            # Save upload history
            upload = Upload(
                filename=filename,
                user_id=session["user_id"]
            )

            db.session.add(upload)

            db.session.commit()

        except Exception as e:

            message = f"PDF Error: {e}"

            return render_template(
                "upload.html",
                summary="",
                message=message
            )

        # ==================================
        # Generate AI Summary
        # ==================================

        prompt = f"""
You are a study assistant.

Read the following PDF text and generate
a clean study summary.

Use simple English suitable for students.

PDF TEXT:

{text[:3000]}
"""

        summary = ask_ai(prompt)

        message = "PDF Uploaded Successfully."

    return render_template(
        "upload.html",
        summary=summary,
        message=message
    )
# ==========================================
# Ask AI Chatbot
# ==========================================

@app.route("/chatbot", methods=["GET", "POST"])
def chatbot():

    if "user_id" not in session:

        return redirect("/login")

    answer = ""

    if request.method == "POST":

        question = request.form.get(
            "question",
            ""
        )

        prompt = f"""
You are StudyBuddy AI.

Answer the student's question clearly
and simply.

Question:

{question}
"""

        answer = ask_ai(prompt)

    return render_template(
        "chatbot.html",
        answer=answer
    )


# ==========================================
# Quiz Generator
# ==========================================

@app.route("/quiz", methods=["GET", "POST"])
def quiz():

    if "user_id" not in session:
        return redirect("/login")

    quiz_data = []
    score = None

    if request.method == "POST":

        # ==========================================
        # Submit Quiz
        # ==========================================

        if "submit_quiz" in request.form:

            quiz_data = session.get("quiz_data", [])

            score = 0

            for i, question in enumerate(quiz_data):

                selected_answer = request.form.get(f"q{i}")

                correct_answer = question["answer"]

                if selected_answer == correct_answer:
                    score += 1

            # Save score
            quiz_score = QuizScore(
                user_id=session["user_id"],
                score=score
            )

            db.session.add(quiz_score)
            db.session.commit()

            return render_template(
                "quiz.html",
                quiz=quiz_data,
                score=score,
                submitted=True
            )
       # ==========================================
       # Generate Quiz
       # ==========================================

        topic = request.form.get("topic", "").strip()

        if not topic:

            flash("Please enter a topic.")

            return render_template(
                "quiz.html",
                quiz=[],
                score=None,
                submitted=False
            )

        prompt = f"""
Generate exactly 10 multiple-choice questions about:

{topic}

Return ONLY valid JSON.

Use exactly this format:

[
  {{
    "question": "Question text",
    "options": [
      "Option 1",
      "Option 2",
      "Option 3",
      "Option 4"
    ],
    "answer": "Option 1"
  }}
]

Important rules:

1. Generate exactly 10 questions.
2. Every question must have exactly 4 options.
3. The options must be different.
4. The "answer" must contain the EXACT text
   of the correct option.
5. Do NOT use A, B, C, or D in the answer field.
6. Only one option should be correct.
7. Return JSON only.
"""

        try:

            response = ask_ai(prompt)

            response = response.strip()

            # Remove markdown code block
            if response.startswith("```"):

                response = response.replace(
                    "```json", ""
                )

                response = response.replace(
                    "```", ""
                )

                response = response.strip()

            quiz_data = json.loads(response)

            # ==========================================
            # Randomize Options
            # ==========================================

            for question in quiz_data:

                correct_option = question["answer"]

                options = question["options"]

                # Shuffle options randomly
                random.shuffle(options)

                # Find correct option after shuffle
                correct_index = options.index(
                    correct_option
                )

                # Convert index to A/B/C/D
                question["answer"] = [
                    "A",
                    "B",
                    "C",
                    "D"
                ][correct_index]

            # Save quiz in session
            session["quiz_data"] = quiz_data

        except Exception as e:

            quiz_data = []

            flash(f"Quiz Error: {e}")

    return render_template(
        "quiz.html",
        quiz=quiz_data,
        score=score,
        submitted=False
    )
# ==========================================
# Ask AI API
# ==========================================

@app.route("/ask", methods=["POST"])
def ask():

    if "user_id" not in session:

        return {
            "answer": "Login Required"
        }

    question = request.form.get(
        "question",
        ""
    )

    if question.strip() == "":

        return {
            "answer": "Please enter a question."
        }

    answer = ask_ai(question)

    return {
        "answer": answer
    }
# ==========================================
# Flashcards Generator
# ==========================================

@app.route("/flashcards", methods=["GET", "POST"])
def flashcards():

    if "user_id" not in session:

        return redirect("/login")

    flashcards = []

    if request.method == "POST":

        topic = request.form.get(
            "topic",
            ""
        )

        prompt = f"""
Write 10 informative paragraphs
about the topic below.

Topic:
{topic}

Instructions:

- Each paragraph should explain
  one important concept.
- Each paragraph should contain
  4 to 6 simple sentences.
- Use easy English suitable for students.
- Number the paragraphs from 1 to 10.
- Do not use questions and answers.
"""

        try:

            text = ask_ai(prompt)

            # Convert AI response into paragraphs
            flashcards = [
                paragraph.strip()
                for paragraph in text.split("\n\n")
                if paragraph.strip()
            ]

        except Exception as e:

            flashcards = [
                f"AI Error: {e}"
            ]

    return render_template(
        "flashcards.html",
        flashcards=flashcards
    )


# ==========================================
# Summary
# ==========================================

@app.route("/summary", methods=["GET", "POST"])
def summary():

    if "user_id" not in session:

        return redirect("/login")

    summary_text = ""

    if request.method == "POST":

        pdf_text = session.get(
            "pdf_text",
            ""
        )

        if not pdf_text:

            summary_text = (
                "Please upload a PDF first."
            )

        else:

            prompt = f"""
Read the following PDF content and
generate a clear summary in paragraph form.

Instructions:

- Write 3 to 5 paragraphs.
- Each paragraph should contain
  4 to 6 sentences.
- Use simple and easy English.
- Explain the important concepts
  instead of listing bullet points.

PDF:

{pdf_text[:3000]}
"""

            try:

                summary_text = ask_ai(prompt)

            except Exception as e:

                summary_text = f"AI Error: {e}"

    return render_template(
        "summary.html",
        summary=summary_text
    )

#------------history-----------#

@app.route("/history")
def history():

    if "user_id" not in session:
        return redirect("/login")

    uploads = Upload.query.filter_by(
        user_id=session["user_id"]
    ).order_by(
        Upload.id.desc()
    ).all()

    return render_template(
        "history.html",
        uploads=uploads
    )
# ==========================================
# Run Flask App
# ==========================================

if __name__ == "__main__":

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )