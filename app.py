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


# ==========================================
# LOAD ENVIRONMENT
# ==========================================

load_dotenv()


# ==========================================
# FLASK CONFIGURATION
# ==========================================

app = Flask(__name__)

app.secret_key = "studybuddy_secret_key"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///studybuddy.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# ==========================================
# UPLOAD FOLDER
# ==========================================

UPLOAD_FOLDER = "pdf_files"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


# ==========================================
# DATABASE
# ==========================================

db.init_app(app)

with app.app_context():
    db.create_all()


# ==========================================
# OPENROUTER CONFIGURATION
# ==========================================

api_key = os.getenv("OPENROUTER_API_KEY")

if not api_key:
    raise ValueError(
        "OPENROUTER_API_KEY not found. "
        "Please check your .env file."
    )

print("API key Loaded:", bool(api_key))


client = OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1"
)


MODEL_NAME = "openai/gpt-4.1-mini"


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
            temperature=0.7,
            max_tokens=4000
        )

        if not response:
            return None

        if not response.choices:
            return None

        content = response.choices[0].message.content

        if not content:
            return None

        return content.strip()

    except Exception as e:
        print("AI ERROR:", e)
        return None
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
# LOGIN
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
# LOGOUT
# ==========================================

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
# UPLOAD PDF
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

        try:

            file.save(filepath)

            text = ""

            pdf = fitz.open(filepath)

            for page in pdf:

                text += page.get_text()

            pdf.close()

            session["pdf_text"] = text

            upload_record = Upload(
                filename=filename,
                user_id=session["user_id"]
            )

            db.session.add(upload_record)

            db.session.commit()

        except Exception as e:

            message = f"PDF Error: {e}"

            return render_template(
                "upload.html",
                summary="",
                message=message
            )

        # ==================================
        # AI SUMMARY
        # ==================================

        prompt = f"""
You are a study assistant.

Read the following PDF text and generate
a clear study summary.

Use simple English suitable for students.

PDF TEXT:

{text[:3000]}
"""

        summary = ask_ai(prompt)

        if not summary:

            summary = "AI could not generate a summary."

        message = "PDF Uploaded Successfully."

    return render_template(
        "upload.html",
        summary=summary,
        message=message
    )


# ==========================================
# ASK AI CHATBOT
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
        ).strip()

        if question:

            prompt = f"""
You are StudyBuddy AI.

Answer the student's question clearly
and simply.

Question:

{question}
"""

            answer = ask_ai(prompt)

            if not answer:

                answer = (
                    "AI could not generate an answer. "
                    "Please try again."
                )

    return render_template(
        "chatbot.html",
        answer=answer
    )


# ==========================================
# SUMMARY
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
- Explain important concepts
  instead of listing bullet points.

PDF:

{pdf_text[:3000]}
"""

            summary_text = ask_ai(prompt)

            if not summary_text:

                summary_text = (
                    "AI could not generate the summary. "
                    "Please try again."
                )

    return render_template(
        "summary.html",
        summary=summary_text
    )


# ==========================================
# QUIZ GENERATOR
# ==========================================

def generate_quiz(topic):

    prompt = f"""
You are StudyBuddy AI, an expert quiz generator.

Create exactly 10 multiple-choice questions
about this topic:

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
        "answer": 0
    }}
]

Rules:

1. Generate exactly 10 questions.
2. Every question must have exactly 4 options.
3. Only ONE option must be correct.
4. The answer must be a number from 0 to 3.
5. 0 = first option is correct.
6. 1 = second option is correct.
7. 2 = third option is correct.
8. 3 = fourth option is correct.
9. Do NOT write A, B, C or D in the option text.
10. Do NOT include explanations.
11. Do NOT use markdown.
12. Return ONLY JSON.
"""

    try:

        result = ask_ai(prompt)

        print("AI QUIZ RESPONSE:")
        print(result)

        # ==================================
        # IMPORTANT: PREVENT NONE ERROR
        # ==================================

        if not result:

            print("AI returned None.")

            return []

        result = result.strip()

        # Remove markdown if AI adds it

        if result.startswith("```json"):

            result = result[7:]

        if result.startswith("```"):

            result = result[3:]

        if result.endswith("```"):

            result = result[:-3]

        result = result.strip()

        # ==================================
        # JSON CONVERSION
        # ==================================

        questions = json.loads(result)

        if not isinstance(questions, list):

            print("Quiz response is not a list.")

            return []

        if len(questions) < 10:

            print(
                "AI generated less than 10 questions:",
                len(questions)
            )

            return []

        questions = questions[:10]

        valid_questions = []

        # ==================================
        # VALIDATE + RANDOMIZE OPTIONS
        # ==================================

        for question in questions:

            if not isinstance(question, dict):

                continue

            question_text = question.get(
                "question"
            )

            options = question.get(
                "options"
            )

            answer = question.get(
                "answer"
            )

            if not question_text:

                continue

            if not isinstance(options, list):

                continue

            if len(options) != 4:

                continue

            try:

                answer = int(answer)

            except:

                continue

            if answer < 0 or answer > 3:

                continue

            # Save correct answer text
            correct_text = options[answer]

            # Randomly shuffle options
            random.shuffle(options)

            # Find new correct position
            new_answer = options.index(
                correct_text
            )

            question["question"] = question_text
            question["options"] = options
            question["answer"] = new_answer

            valid_questions.append(question)

        if len(valid_questions) < 10:

            print(
                "Not enough valid questions:",
                len(valid_questions)
            )

            return []

        return valid_questions[:10]

    except Exception as e:

        print(
            "Quiz Generation Error:",
            e
        )

        return []


# ==========================================
# QUIZ
# ==========================================

@app.route("/quiz", methods=["GET", "POST"])
def quiz():

    if "user_id" not in session:

        return redirect("/login")

    # ==================================
    # SUBMIT QUIZ
    # ==================================

    if (
        request.method == "POST"
        and request.form.get("submit_quiz") == "yes"
    ):

        quiz_data = session.get(
            "quiz_data",
            []
        )

        if not quiz_data:

            flash(
                "Quiz expired. Please generate a new quiz."
            )

            return redirect("/quiz")

        score = 0

        for i, question in enumerate(
            quiz_data
        ):

            selected = request.form.get(
                f"question_{i}"
            )

            if selected is None:

                continue

            try:

                selected = int(selected)

            except:

                continue

            correct_answer = int(
                question["answer"]
            )

            if selected == correct_answer:

                score += 1

        # Save score
        session["quiz_score"] = score

        session["quiz_submitted"] = True

        # Save database score
        try:

            quiz_score = QuizScore(
                user_id=session["user_id"],
                score=score
            )

            db.session.add(quiz_score)

            db.session.commit()

        except Exception as e:

            print(
                "Quiz score save error:",
                e
            )

            db.session.rollback()

        return render_template(
            "quiz.html",
            questions=quiz_data,
            score=score,
            total=len(quiz_data)
        )

    # ==================================
    # GENERATE QUIZ
    # ==================================

    if request.method == "POST":

        topic = request.form.get(
            "topic",
            ""
        ).strip()

        if not topic:

            flash(
                "Please enter a quiz topic."
            )

            return redirect("/quiz")

        print(
            "Generating quiz for:",
            topic
        )

        questions = generate_quiz(topic)

        if not questions:

            flash(
                "Quiz could not be generated. "
                "Please try again."
            )

            return redirect("/quiz")

        # Save quiz
        session["quiz_data"] = questions

        session["quiz_submitted"] = False

        session["quiz_score"] = 0

        return render_template(
            "quiz.html",
            questions=questions,
            score=None,
            total=len(questions)
        )

    # ==================================
    # OPEN QUIZ PAGE
    # ==================================

    questions = session.get(
        "quiz_data",
        []
    )

    submitted = session.get(
        "quiz_submitted",
        False
    )

    if submitted and questions:

        return render_template(
            "quiz.html",
            questions=questions,
            score=session.get(
                "quiz_score",
                0
            ),
            total=len(questions)
        )

    return render_template(
        "quiz.html",
        questions=[],
        score=None,
        total=0
    )


# ==========================================
# UPLOAD HISTORY
# ==========================================

@app.route("/history", methods=["GET"])
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

    flashcards_data = []

    if request.method == "POST":

        topic = request.form.get(
            "topic",
            ""
        ).strip()

        if not topic:

            flash(
                "Please enter a topic."
            )

            return redirect("/flashcards")

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

        text = ask_ai(prompt)

        if text:

            flashcards_data = [
                paragraph.strip()
                for paragraph in text.split("\n\n")
                if paragraph.strip()
            ]

        else:

            flashcards_data = [
                "AI could not generate flashcards. "
                "Please try again."
            ]

    return render_template(
        "flashcards.html",
        flashcards=flashcards_data
    )


# ==========================================
# RUN FLASK APP
# ==========================================

if __name__ == "__main__":

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )