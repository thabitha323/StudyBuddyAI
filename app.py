from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

from models import db, User, Upload, QuizScore
from werkzeug.utils import secure_filename
from openai import OpenAI

import fitz
import os

# ==========================================
# Flask Configuration
# ==========================================

app = Flask(__name__)

app.secret_key = "studybuddy_secret_key"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///studybuddy.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

MODEL_NAME = "openai/gpt-oss-20b"

# ==========================================
# Helper Function
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
            max_tokens=500
        )

        return response.choices[0].message.content

    except Exception as e:

        return f"AI Error : {e}"
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

        existing = User.query.filter_by(email=email).first()

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

        filename = secure_filename(file.filename)

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

            # Save upload history in database
            upload = Upload(
                filename=filename,
                user_id=session["user_id"]
            )

            db.session.add(upload)
            db.session.commit()

        except Exception as e:

            message = f"PDF Error : {e}"

            return render_template(
                "upload.html",
                summary="",
                message=message
            )

        prompt = f"""
You are a study assistant.

Read the following PDF text and generate
a clean study summary.

PDF:

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

        question = request.form["question"]

        prompt = f"""
You are StudyBuddy AI.

Answer the student's question clearly and simply.

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

    quiz = ""

    if request.method == "POST":

        topic = request.form.get("topic", "")

        prompt = f"""
Generate a multiple choice quiz.

Topic:
{topic}

Instructions:

- Generate exactly 10 questions.
- Each question should have 4 options.
- Mention the correct answer after every question.

Format:

Q1.
A)
B)
C)
D)

Answer:
"""

        quiz = ask_ai(prompt)

    return render_template(
        "quiz.html",
        quiz=quiz
    )


# ==========================================
# Ask AI API (Optional AJAX)
# ==========================================

@app.route("/ask", methods=["POST"])
def ask():

    if "user_id" not in session:
        return {"answer": "Login Required"}

    question = request.form.get("question", "")

    if question.strip() == "":
        return {"answer": "Please enter a question."}

    answer = ask_ai(question)

    return {"answer": answer}
# ==========================================
# Flashcards Generator
# ==========================================

@app.route("/flashcards", methods=["GET", "POST"])
def flashcards():

    if "user_id" not in session:
        return redirect("/login")

    flashcards = []

    if request.method == "POST":

        topic = request.form.get("topic", "")

        prompt = f"""
Write 10 informative paragraphs about the topic below.

Topic:
{topic}

Instructions:
- Each paragraph should explain one important concept.
- Each paragraph should contain 4 to 6 simple sentences.
- Use easy English suitable for students.
- Number the paragraphs from 1 to 10.
- Do not use questions and answers.
"""

        try:
            text = ask_ai(prompt)
            flashcards = text.split("\n\n")
        except Exception as e:
            flashcards = [f"AI Error: {e}"]

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

    summary = ""

    if request.method == "POST":

        pdf_text = session.get("pdf_text", "")

        if not pdf_text:
            summary = "Please upload a PDF first."

        else:

            prompt = f"""
Read the following PDF content and generate a clear summary in paragraph form.

Instructions:
- Write 3 to 5 paragraphs.
- Each paragraph should contain 4 to 6 sentences.
- Use simple and easy English.
- Explain the important concepts instead of listing bullet points.

PDF:
{pdf_text[:3000]}
"""

            try:
                summary = ask_ai(prompt)
            except Exception as e:
                summary = f"AI Error: {e}"

    return render_template(
        "summary.html",
        summary=summary
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