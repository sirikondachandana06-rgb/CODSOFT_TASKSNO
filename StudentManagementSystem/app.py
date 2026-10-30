


from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from pathlib import Path

app = Flask(__name__)
app.secret_key = "student-management-demo-secret-key"

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database.db"


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        course TEXT DEFAULT '',
        year TEXT DEFAULT '',
        phone TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS teachers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        subject TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        status TEXT NOT NULL,
        marked_by INTEGER
    );

    CREATE TABLE IF NOT EXISTS exams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        marks REAL NOT NULL,
        total REAL NOT NULL,
        exam_date TEXT
    );

    CREATE TABLE IF NOT EXISTS fees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        status TEXT NOT NULL,
        due_date TEXT
    );
    """)

    admin = db.execute(
        "SELECT id FROM users WHERE email=?",
        ("admin@school.com",)
    ).fetchone()

    if not admin:
        db.execute(
            "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
            ("Administrator", "admin@school.com",
             generate_password_hash("admin123"), "admin")
        )

    db.commit()
    db.close()


def login_required(role=None):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))

            if role and session.get("role") != role:
                flash("You are not authorized to access that page.", "error")
                return redirect(url_for("dashboard"))

            return function(*args, **kwargs)
        return wrapper
    return decorator


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "").strip()

        if not name or not email or not password:
            flash("Please complete all fields.", "error")
            return redirect(url_for("register"))

        if role not in ("student", "teacher"):
            flash("Please select a valid role.", "error")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "error")
            return redirect(url_for("register"))

        db = get_db()
        try:
            cursor = db.execute(
                "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                (name, email, generate_password_hash(password), role)
            )
            user_id = cursor.lastrowid

            if role == "student":
                db.execute(
                    "INSERT INTO students(user_id,name,email) VALUES(?,?,?)",
                    (user_id, name, email)
                )
            else:
                db.execute(
                    "INSERT INTO teachers(user_id,name,email) VALUES(?,?,?)",
                    (user_id, name, email)
                )

            db.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("This email is already registered.", "error")
        finally:
            db.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email=?", (email,)
        ).fetchone()
        db.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["email"] = user["email"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have logged out successfully.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required()
def dashboard():
    role = session["role"]

    if role == "admin":
        db = get_db()
        stats = {
            "students": db.execute("SELECT COUNT(*) FROM students").fetchone()[0],
            "teachers": db.execute("SELECT COUNT(*) FROM teachers").fetchone()[0],
            "attendance": db.execute("SELECT COUNT(*) FROM attendance").fetchone()[0],
            "exams": db.execute("SELECT COUNT(*) FROM exams").fetchone()[0]
        }
        students = db.execute(
            "SELECT * FROM students ORDER BY id DESC LIMIT 5"
        ).fetchall()
        db.close()
        return render_template("dashboard.html", stats=stats, students=students)

    if role == "student":
        return redirect(url_for("student_portal"))

    if role == "teacher":
        return redirect(url_for("teacher_portal"))

    session.clear()
    return redirect(url_for("login"))


# ADMIN: STUDENTS

@app.route("/students", methods=["GET", "POST"])
@login_required("admin")
def students():
    db = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        course = request.form.get("course", "").strip()
        year = request.form.get("year", "").strip()
        phone = request.form.get("phone", "").strip()

        if not name or not email:
            flash("Student name and email are required.", "error")
        else:
            try:
                db.execute(
                    """INSERT INTO students(name,email,course,year,phone)
                    VALUES(?,?,?,?,?)""",
                    (name, email, course, year, phone)
                )
                db.commit()
                flash("Student added successfully.", "success")
            except sqlite3.IntegrityError:
                flash("Could not add student.", "error")

    records = db.execute("SELECT * FROM students ORDER BY id DESC").fetchall()
    db.close()
    return render_template("students.html", students=records)


@app.route("/students/edit/<int:student_id>", methods=["GET", "POST"])
@login_required("admin")
def edit_student(student_id):
    db = get_db()
    student = db.execute(
        "SELECT * FROM students WHERE id=?", (student_id,)
    ).fetchone()

    if not student:
        db.close()
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    if request.method == "POST":
        db.execute(
            """UPDATE students SET name=?,email=?,course=?,year=?,phone=?
            WHERE id=?""",
            (
                request.form.get("name", "").strip(),
                request.form.get("email", "").strip().lower(),
                request.form.get("course", "").strip(),
                request.form.get("year", "").strip(),
                request.form.get("phone", "").strip(),
                student_id
            )
        )
        db.commit()
        db.close()
        flash("Student updated successfully.", "success")
        return redirect(url_for("students"))

    db.close()
    return render_template("edit_student.html", student=student)


@app.route("/students/delete/<int:student_id>", methods=["POST"])
@login_required("admin")
def delete_student(student_id):
    db = get_db()
    student = db.execute(
        "SELECT user_id FROM students WHERE id=?", (student_id,)
    ).fetchone()

    db.execute("DELETE FROM attendance WHERE student_id=?", (student_id,))
    db.execute("DELETE FROM exams WHERE student_id=?", (student_id,))
    db.execute("DELETE FROM fees WHERE student_id=?", (student_id,))
    db.execute("DELETE FROM students WHERE id=?", (student_id,))

    if student and student["user_id"]:
        db.execute("DELETE FROM users WHERE id=?", (student["user_id"],))

    db.commit()
    db.close()
    flash("Student deleted.", "success")
    return redirect(url_for("students"))


# ADMIN: TEACHERS

@app.route("/teachers", methods=["GET", "POST"])
@login_required("admin")
def teachers():
    db = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        subject = request.form.get("subject", "").strip()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 6:
            flash("Enter all details and a password of at least 6 characters.", "error")
        else:
            try:
                cursor = db.execute(
                    "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                    (name, email, generate_password_hash(password), "teacher")
                )
                db.execute(
                    "INSERT INTO teachers(user_id,name,email,subject) VALUES(?,?,?,?)",
                    (cursor.lastrowid, name, email, subject)
                )
                db.commit()
                flash("Teacher added. They can now log in.", "success")
            except sqlite3.IntegrityError:
                flash("Email already exists.", "error")

    records = db.execute("SELECT * FROM teachers ORDER BY id DESC").fetchall()
    db.close()
    return render_template("teachers.html", teachers=records)


@app.route("/teachers/delete/<int:teacher_id>", methods=["POST"])
@login_required("admin")
def delete_teacher(teacher_id):
    db = get_db()
    teacher = db.execute(
        "SELECT user_id FROM teachers WHERE id=?", (teacher_id,)
    ).fetchone()

    db.execute("DELETE FROM teachers WHERE id=?", (teacher_id,))
    if teacher and teacher["user_id"]:
        db.execute("DELETE FROM users WHERE id=?", (teacher["user_id"],))

    db.commit()
    db.close()
    flash("Teacher deleted.", "success")
    return redirect(url_for("teachers"))


# ATTENDANCE: ADMIN AND TEACHER

@app.route("/attendance", methods=["GET", "POST"])
@login_required()
def attendance():
    if session["role"] not in ("admin", "teacher"):
        return redirect(url_for("student_portal"))

    db = get_db()

    if request.method == "POST":
        try:
            student_id = int(request.form.get("student_id"))
            date = request.form.get("date", "")
            status = request.form.get("status", "")

            student = db.execute(
                "SELECT id FROM students WHERE id=?", (student_id,)
            ).fetchone()

            if not student or status not in ("Present", "Absent", "Late") or not date:
                flash("Please enter valid attendance details.", "error")
            else:
                db.execute(
                    """INSERT INTO attendance(student_id,date,status,marked_by)
                    VALUES(?,?,?,?)""",
                    (student_id, date, status, session["user_id"])
                )
                db.commit()
                flash("Attendance saved.", "success")
        except (ValueError, TypeError):
            flash("Please select a valid student.", "error")

    student_list = db.execute("SELECT * FROM students ORDER BY name").fetchall()
    records = db.execute(
        """SELECT attendance.*, students.name AS student_name
        FROM attendance JOIN students ON students.id=attendance.student_id
        ORDER BY attendance.date DESC, attendance.id DESC"""
    ).fetchall()

    db.close()
    return render_template(
        "attendance.html", students=student_list, records=records
    )


# EXAMS: ADMIN AND TEACHER

@app.route("/exams", methods=["GET", "POST"])
@login_required()
def exams():
    if session["role"] not in ("admin", "teacher"):
        return redirect(url_for("student_portal"))

    db = get_db()

    if request.method == "POST":
        try:
            student_id = int(request.form.get("student_id"))
            subject = request.form.get("subject", "").strip()
            marks = float(request.form.get("marks"))
            total = float(request.form.get("total"))
            exam_date = request.form.get("exam_date", "")

            if (
                not subject or total <= 0 or marks < 0
                or marks > total
                or not db.execute(
                    "SELECT id FROM students WHERE id=?", (student_id,)
                ).fetchone()
            ):
                flash("Please enter valid exam details.", "error")
            else:
                db.execute(
                    """INSERT INTO exams(student_id,subject,marks,total,exam_date)
                    VALUES(?,?,?,?,?)""",
                    (student_id, subject, marks, total, exam_date)
                )
                db.commit()
                flash("Exam result saved.", "success")
        except (ValueError, TypeError):
            flash("Please enter valid marks and select a student.", "error")

    student_list = db.execute("SELECT * FROM students ORDER BY name").fetchall()
    records = db.execute(
        """SELECT exams.*, students.name AS student_name
        FROM exams JOIN students ON students.id=exams.student_id
        ORDER BY exams.id DESC"""
    ).fetchall()

    db.close()
    return render_template("exams.html", students=student_list, records=records)


# FEES: ADMIN

@app.route("/fees", methods=["GET", "POST"])
@login_required("admin")
def fees():
    db = get_db()

    if request.method == "POST":
        try:
            student_id = int(request.form.get("student_id"))
            amount = float(request.form.get("amount"))
            status = request.form.get("status", "")
            due_date = request.form.get("due_date", "")

            if (
                amount < 0 or status not in ("Paid", "Pending")
                or not db.execute(
                    "SELECT id FROM students WHERE id=?", (student_id,)
                ).fetchone()
            ):
                flash("Please enter valid fee details.", "error")
            else:
                db.execute(
                    """INSERT INTO fees(student_id,amount,status,due_date)
                    VALUES(?,?,?,?)""",
                    (student_id, amount, status, due_date)
                )
                db.commit()
                flash("Fee record saved.", "success")
        except (ValueError, TypeError):
            flash("Please enter a valid amount and student.", "error")

    student_list = db.execute("SELECT * FROM students ORDER BY name").fetchall()
    records = db.execute(
        """SELECT fees.*, students.name AS student_name
        FROM fees JOIN students ON students.id=fees.student_id
        ORDER BY fees.id DESC"""
    ).fetchall()

    db.close()
    return render_template("fees.html", students=student_list, records=records)


# REPORTS: ADMIN AND TEACHER

@app.route("/reports")
@login_required()
def reports():
    if session["role"] not in ("admin", "teacher"):
        return redirect(url_for("student_portal"))

    db = get_db()
    attendance_count = db.execute(
        "SELECT COUNT(*) FROM attendance"
    ).fetchone()[0]
    exam_count = db.execute(
        "SELECT COUNT(*) FROM exams"
    ).fetchone()[0]
    fee_count = db.execute(
        "SELECT COUNT(*) FROM fees"
    ).fetchone()[0]

    db.close()
    return render_template(
        "reports.html",
        attendance_count=attendance_count,
        exam_count=exam_count,
        fee_count=fee_count
    )


# STUDENT PORTAL

@app.route("/student")
@login_required("student")
def student_portal():
    db = get_db()
    student = db.execute(
        "SELECT * FROM students WHERE user_id=?",
        (session["user_id"],)
    ).fetchone()

    if not student:
        db.close()
        flash("Student profile not found. Contact the administrator.", "error")
        return redirect(url_for("logout"))

    attendance_records = db.execute(
        "SELECT * FROM attendance WHERE student_id=? ORDER BY date DESC",
        (student["id"],)
    ).fetchall()

    exam_records = db.execute(
        "SELECT * FROM exams WHERE student_id=? ORDER BY id DESC",
        (student["id"],)
    ).fetchall()

    fee_records = db.execute(
        "SELECT * FROM fees WHERE student_id=? ORDER BY id DESC",
        (student["id"],)
    ).fetchall()

    db.close()
    return render_template(
        "student_portal.html",
        student=student,
        attendance=attendance_records,
        exams=exam_records,
        fees=fee_records
    )


# TEACHER PORTAL

@app.route("/teacher")
@login_required("teacher")
def teacher_portal():
    db = get_db()
    teacher = db.execute(
        "SELECT * FROM teachers WHERE user_id=?",
        (session["user_id"],)
    ).fetchone()

    student_count = db.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    attendance_count = db.execute(
        "SELECT COUNT(*) FROM attendance WHERE marked_by=?",
        (session["user_id"],)
    ).fetchone()[0]

    exam_count = db.execute(
        "SELECT COUNT(*) FROM exams"
    ).fetchone()[0]

    db.close()

    return render_template(
        "teacher_portal.html",
        teacher=teacher,
        student_count=student_count,
        attendance_count=attendance_count,
        exam_count=exam_count
    )


@app.errorhandler(404)
def not_found(error):
    return "Page not found. Please return to the dashboard.", 404


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
