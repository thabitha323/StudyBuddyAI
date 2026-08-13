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

print("API key Loaded:", bool(api_key))


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
# AI QUIZ GENERATOR
# ==========================================

def generate_quiz(topic):

    prompt = f"""
You are StudyBuddy AI, a quiz generator.

Create 5 multiple-choice questions about:

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

- Generate exactly 5 questions.
- Each question must have exactly 4 options.
- "answer" must be a number from 0 to 3.
- 0 means first option is correct.
- 1 means second option is correct.
- 2 means third option is correct.
- 3 means fourth option is correct.
- Do not write A, B, C, D.
- Return JSON only.
"""

    try:

        result = ask_ai(prompt)

        # Remove markdown code fences
        result = result.replace("```json", "")
        result = result.replace("```", "")

        result = result.strip()

        questions = json.loads(result)

        return questions

    except Exception as e:

        print("Quiz Generation Error:", e)

        return []


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

        # Check PDF
        if "pdf" not in request.files:

            message = "No PDF Selected."

            return render_template(
                "upload.html",
                summary=summary,
                message=message
            )


        file = request.files["pdf"]


        # Check filename
        if file.filename == "":

            message = "Choose a PDF."

            return render_template(
                "upload.html",
                summary=summary,
                message=message
            )


        # Secure filename
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

            # Open PDF
            pdf = fitz.open(filepath)


            # Extract text
            for page in pdf:

                text += page.get_text()


            pdf.close()


            # Save PDF text
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
        # AI SUMMARY
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


            try:

                summary_text = ask_ai(prompt)


            except Exception as e:

                summary_text = (
                    f"AI Error: {e}"
                )


    return render_template(

        "summary.html",

        summary=summary_text

    )
# ==========================================
# AI QUIZ GENERATOR
# ==========================================

def generate_quiz(topic):

    prompt = f"""
You are StudyBuddy AI, an expert quiz generator.

Create exactly 10 multiple-choice questions
about the following topic:

{topic}

Return ONLY valid JSON.

The JSON must follow exactly this structure:

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
4. The answer value must be a number from 0 to 3.
5. 0 means the first option is correct.
6. 1 means the second option is correct.
7. 2 means the third option is correct.
8. 3 means the fourth option is correct.
9. Do NOT write A, B, C, or D before options.
10. Do NOT include explanations.
11. Do NOT include markdown.
12. Return ONLY JSON.
"""

    try:

        result = ask_ai(prompt)

        print("AI QUIZ RESPONSE:")
        print(result)

        # Remove markdown if AI adds it
        result = result.replace("```json", "")
        result = result.replace("```", "")

        result = result.strip()

        # Convert AI response to Python list
        questions = json.loads(result)

        # Make sure at least 10 questions exist
        if not isinstance(questions, list):
            print("Quiz response is not a list")
            return []

        if len(questions) < 10:
            print("AI generated less than 10 questions")
            return []

        # Keep only 10 questions
        questions = questions[:10]

        # Validate questions
        valid_questions = []

        for question in questions:

            if "question" not in question:
                continue

            if "options" not in question:
                continue

            if "answer" not in question:
                continue

            if len(question["options"]) != 4:
                continue

            try:
                answer = int(question["answer"])
            except:
                continue

            if answer < 0 or answer > 3:
                continue

            question["answer"] = answer

            valid_questions.append(question)

        if len(valid_questions) < 10:

            print(
                "Not enough valid questions:",
                len(valid_questions)
            )

            return []

        return valid_questions[:10]

    except Exception as e:

        print("Quiz Generation Error:", e)

        return []


# ==========================================
# QUIZ GENERATOR ROUTE
# ==========================================

@app.route("/quiz", methods=["GET", "POST"])
def quiz():

    # Login check
    if "user_id" not in session:

        return redirect("/login")


    # ======================================
    # GENERATE QUIZ
    # ======================================

    if (
        request.method == "POST"
        and "topic" in request.form
    ):

        topic = request.form.get(
            "topic",
            ""
        ).strip()


        # Check topic
        if not topic:

            flash(
                "Please enter a topic."
            )

            return redirect("/quiz")


        print("Generating quiz for:", topic)


        # Generate 10 AI questions
        questions = generate_quiz(topic)


        # Check generation
        if not questions:

            flash(
                "Quiz generation failed. "
                "Please try again."
            )

            return redirect("/quiz")


        # Save questions in session
        session["quiz_questions"] = questions

        session["quiz_topic"] = topic


        print(
            "Questions generated:",
            len(questions)
        )


        # Show questions
        return render_template(

            "quiz.html",

            questions=questions,

            score=None,

            total=len(questions),

            topic=topic

        )


    # ======================================
    # SUBMIT QUIZ
    # ======================================

    if (
        request.method == "POST"
        and "submit_quiz" in request.form
    ):

        # Get questions
        questions = session.get(
            "quiz_questions",
            []
        )


        # No questions
        if not questions:

            flash(
                "No quiz found. "
                "Please generate a quiz first."
            )

            return redirect("/quiz")


        score = 0


        # ==================================
        # CHECK EACH ANSWER
        # ==================================

        for i, question in enumerate(questions):

            selected = request.form.get(
                f"question_{i}"
            )


            # If student selected an option
            if selected is not None:

                try:

                    selected = int(selected)

                    correct_answer = int(
                        question["answer"]
                    )


                    if selected == correct_answer:

                        score += 1


                except Exception as e:

                    print(
                        "Answer checking error:",
                        e
                    )


        total = len(questions)


        # ==================================
        # SAVE SCORE
        # ==================================

        try:

            quiz_score = QuizScore(

                user_id=session["user_id"],

                score=score

            )

            db.session.add(quiz_score)

            db.session.commit()

            print(
                "Quiz score saved:",
                score,
                "/",
                total
            )


        except Exception as e:

            print(
                "Score Save Error:",
                e
            )

            db.session.rollback()


        # Save score in session
        session["quiz_score"] = score

        session["quiz_total"] = total


        # ==================================
        # SHOW SCORE
        # ==================================

        return render_template(

            "quiz.html",

            questions=questions,

            score=score,

            total=total,

            topic=session.get(
                "quiz_topic",
                ""
            )

        )


    # ======================================
    # OPEN QUIZ GENERATOR
    # ======================================

    return render_template(

        "quiz.html",

        questions=[],

        score=None,

        total=0,

        topic=""

    )


    # ======================================
    # SUBMIT QUIZ
    # ======================================

    if (
        request.method == "POST"
        and "submit_quiz" in request.form
    ):

        questions = session.get(

            "quiz_questions",

            []

        )


        score = 0


        # Check answers
        for i, question in enumerate(questions):

            selected = request.form.get(

                f"question_{i}"

            )


            if selected is not None:

                try:

                    selected = int(selected)


                    if selected == int(
                        question["answer"]
                    ):

                        score += 1


                except ValueError:

                    pass


        total = len(questions)


        # ==================================
        # SAVE SCORE TO DATABASE
        # ==================================

        try:

            quiz_score = QuizScore(

                user_id=session["user_id"],

                score=score

            )


            db.session.add(quiz_score)

            db.session.commit()


        except Exception as e:

            print(
                "Score Save Error:",
                e
            )

            db.session.rollback()


        # Save score in session
        session["quiz_score"] = score

        session["quiz_total"] = total


        return render_template(

            "quiz.html",

            questions=questions,

            score=score,

            total=total

        )


    # ======================================
    # OPEN QUIZ GENERATOR
    # ======================================

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
# FLASHCARDS GENERATOR
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


        try:

            text = ask_ai(prompt)


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
# RUN FLASK APP
# ==========================================

if __name__ == "__main__":

    app.run(

        debug=True,

        host="0.0.0.0",

        port=5000

    ) 
    