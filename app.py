from flask import Flask, render_template, request
import pdfplumber
import pymysql
from groq import Groq
import json
import os
fimport os
try:
    from config import GROQ_API_KEY, DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
except ImportError:
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    DB_HOST = os.environ.get('DB_HOST')
    DB_USER = os.environ.get('DB_USER')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')
    DB_NAME = os.environ.get('DB_NAME')

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

def get_db():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

def extract_text_from_pdf(filepath):
    text = ""
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

def analyze_with_groq(resume_text, job_description):
    client = Groq(api_key=GROQ_API_KEY)
    prompt = f"""
You are an expert ATS resume coach and career advisor. Analyze this resume against the job description.

RESUME:
{resume_text[:3000]}

JOB DESCRIPTION:
{job_description[:2000]}

Reply ONLY with a valid JSON object, no extra text, no markdown backticks:
{{
  "score": <number 0-100>,
  "summary": "<2-3 sentence overall assessment>",
  "matched_skills": ["skill1", "skill2"],
  "missing_skills": ["skill1", "skill2"],
  "strengths": ["strength1", "strength2", "strength3"],
  "suggestions": ["suggestion1", "suggestion2", "suggestion3", "suggestion4", "suggestion5"],
  "ats_tips": ["tip1", "tip2", "tip3"],
  "interview_questions": ["question1", "question2", "question3", "question4", "question5", "question6", "question7", "question8", "question9", "question10"],
  "red_flags": ["flag1", "flag2", "flag3"],
  "job_roles": ["role1", "role2", "role3", "role4", "role5"],
  "top_companies": ["company1", "company2", "company3", "company4", "company5"]
}}
"""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        pdf_file = request.files.get("resume")
        job_desc = request.form.get("job_description", "")

        if not pdf_file or not job_desc:
            return render_template("index.html", error="Please upload a resume and paste a job description.")

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], pdf_file.filename)
        pdf_file.save(filepath)

        resume_text = extract_text_from_pdf(filepath)
        result = analyze_with_groq(resume_text, job_desc)

        db = get_db()
        with db.cursor() as cursor:
            cursor.execute("""
                INSERT INTO analyses (resume_text, job_description, score, matched_skills, missing_skills, suggestions)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                resume_text, job_desc,
                result["score"],
                json.dumps(result["matched_skills"]),
                json.dumps(result["missing_skills"]),
                json.dumps(result["suggestions"])
            ))
        db.commit()
        db.close()

        return render_template("result.html", result=result)

    return render_template("index.html")

@app.route("/history")
def history():
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT id, score, created_at FROM analyses ORDER BY created_at DESC")
        rows = cursor.fetchall()
    db.close()
    return render_template("history.html", rows=rows)

if __name__ == "__main__":
    app.run(debug=True)