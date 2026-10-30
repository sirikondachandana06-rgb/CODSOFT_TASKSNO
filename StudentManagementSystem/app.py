

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from functools import wraps

app = Flask(__name__)
app.secret_key = "change-this-secret-key-before-deployment"

DATABASE = "database.db"


# ---------------- DATABASE CONNECTION ----------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            course TEXT,
            year TEXT,
            phone TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            subject TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            date TEXT,
            status TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            subject TEXT,
            marks INTEGER,
            total INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            amount REAL,
            status TEXT
        )
    """)

    # Create default administrator account
    admin = cur.execute(
        "SELECT id FROM users WHERE email=?",
        ("admin@school.com",)
    ).fetchone()

    if not admin:
        cur.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, ?)
        """, (
            "Administrator",
            "admin@school.com",
            generate_password_hash("admin123"),
            "admin"
        ))

    conn.commit()
    conn.close()


# ---------------- LOGIN PROTECTION ----------------

def login_required(roles=None):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))

            if roles and session.get("role") not in roles:
                flash("You are not authorized to access this page.")
                return redirect(url_for("dashboard"))

            return function(*args, **kwargs)

        return wrapper
    return decorator


# ---------------- HOME ----------------

@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# ---------------- REGISTRATION ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")

        if not name or not email or not password:
            flash("Please complete all required fields.")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.")
            return redirect(url_for("register"))

        if role not in ("student", "teacher"):
            flash("Please select a valid account type.")
            return redirect(url_for("register"))

        conn = get_db()

        try:
            existing_user = conn.execute(
                "SELECT id FROM users WHERE email=?",
                (email,)
            ).fetchone()

            if existing_user:
                flash("This email already has an account.")
                return redirect(url_for("register"))

            conn.execute("""
                INSERT INTO users (name, email, password, role)
                VALUES (?, ?, ?, ?)
            """, (
                name,
                email,
                generate_password_hash(password),
                role
            ))

            if role == "student":
                existing_student = conn.execute(
                    "SELECT id FROM students WHERE email=?",
                    (email,)
                ).fetchone()

                if existing_student:
                    conn.execute("""
                        UPDATE students SET name=? WHERE email=?
                    """, (name, email))
                else:
                    conn.execute("""
                        INSERT INTO students (name, email)
                        VALUES (?, ?)
                    """, (name, email))

            elif role == "teacher":
                conn.execute("""
                    INSERT INTO teachers (name, email)
                    VALUES (?, ?)
                """, (name, email))

            conn.commit()
            flash("Registration successful. Please log in.")

        except sqlite3.IntegrityError:
            conn.rollback()
            flash("Registration could not be completed. Check the email.")

        finally:
            conn.close()

        return redirect(url_for("login"))

    return render_template("register.html")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()

        user = conn.execute(
            "SELECT * FROM users WHERE email=?",
            (email,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["email"] = user["email"]
            session["role"] = user["role"]

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
@login_required()
def dashboard():
    role = session["role"]

    if role == "student":
        return redirect(url_for("student_portal"))

    if role == "teacher":
        return redirect(url_for("teacher_portal"))

    conn = get_db()

    counts = {
        "students": conn.execute(
            "SELECT COUNT(*) FROM students"
        ).fetchone()[0],

        "teachers": conn.execute(
            "SELECT COUNT(*) FROM teachers"
        ).fetchone()[0],

        "attendance": conn.execute(
            "SELECT COUNT(*) FROM attendance"
        ).fetchone()[0],

        "fees": conn.execute(
            "SELECT COUNT(*) FROM fees"
        ).fetchone()[0]
    }

    recent_students = conn.execute("""
        SELECT * FROM students
        ORDER BY id DESC LIMIT 5
    """).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        counts=counts,
        students=recent_students
    )


# ---------------- STUDENT MANAGEMENT ----------------

@app.route("/students")
@login_required(["admin"])
def students():
    conn = get_db()

    records = conn.execute("""
        SELECT * FROM students ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template("students.html", students=records)


@app.route("/students/add", methods=["POST"])
@login_required(["admin"])
def add_student():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    course = request.form.get("course", "")
    year = request.form.get("year", "")
    phone = request.form.get("phone", "")

    if not name or not email:
        flash("Name and email are required.")
        return redirect(url_for("students"))

    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO students (name, email, course, year, phone)
            VALUES (?, ?, ?, ?, ?)
        """, (name, email, course, year, phone))

        conn.commit()
        flash("Student added successfully.")

    except sqlite3.IntegrityError:
        flash("A student with this email already exists.")

    finally:
        conn.close()

    return redirect(url_for("students"))


@app.route("/students/edit/<int:student_id>", methods=["GET", "POST"])
@login_required(["admin"])
def edit_student(student_id):
    conn = get_db()

    student = conn.execute(
        "SELECT * FROM students WHERE id=?",
        (student_id,)
    ).fetchone()

    if not student:
        conn.close()
        flash("Student not found.")
        return redirect(url_for("students"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        course = request.form.get("course", "")
        year = request.form.get("year", "")
        phone = request.form.get("phone", "")

        if not name or not email:
            flash("Name and email are required.")
            conn.close()
            return redirect(url_for("edit_student", student_id=student_id))

        try:
            conn.execute("""
                UPDATE students
                SET name=?, email=?, course=?, year=?, phone=?
                WHERE id=?
            """, (name, email, course, year, phone, student_id))

            conn.execute("""
                UPDATE users SET name=?, email=?
                WHERE email=? AND role='student'
            """, (name, email, student["email"]))

            conn.commit()
            flash("Student details updated successfully.")

        except sqlite3.IntegrityError:
            conn.rollback()
            flash("This email is already in use.")

        finally:
            conn.close()

        return redirect(url_for("students"))

    conn.close()

    return render_template("edit_student.html", student=student)


@app.route("/students/delete/<int:student_id>", methods=["POST"])
@login_required(["admin"])
def delete_student(student_id):
    conn = get_db()

    student = conn.execute(
        "SELECT email FROM students WHERE id=?",
        (student_id,)
    ).fetchone()

    if student:
        conn.execute(
            "DELETE FROM attendance WHERE student_id=?",
            (student_id,)
        )
        conn.execute(
            "DELETE FROM exams WHERE student_id=?",
            (student_id,)
        )
        conn.execute(
            "DELETE FROM fees WHERE student_id=?",
            (student_id,)
        )
        conn.execute(
            "DELETE FROM students WHERE id=?",
            (student_id,)
        )
        conn.execute("""
            DELETE FROM users
            WHERE email=? AND role='student'
        """, (student["email"],))

        conn.commit()
        flash("Student deleted successfully.")

    conn.close()

    return redirect(url_for("students"))


# ---------------- TEACHER MANAGEMENT ----------------

@app.route("/teachers")
@login_required(["admin"])
def teachers():
    conn = get_db()

    records = conn.execute("""
        SELECT * FROM teachers ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template("teachers.html", teachers=records)


@app.route("/teachers/add", methods=["POST"])
@login_required(["admin"])
def add_teacher():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    subject = request.form.get("subject", "")
    password = request.form.get("password", "")

    if not name or not email or len(password) < 6:
        flash("Enter valid details and a password of at least 6 characters.")
        return redirect(url_for("teachers"))

    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, 'teacher')
        """, (
            name,
            email,
            generate_password_hash(password)
        ))

        conn.execute("""
            INSERT INTO teachers (name, email, subject)
            VALUES (?, ?, ?)
        """, (name, email, subject))

        conn.commit()
        flash("Teacher account created successfully.")

    except sqlite3.IntegrityError:
        conn.rollback()
        flash("This email is already registered.")

    finally:
        conn.close()

    return redirect(url_for("teachers"))


@app.route("/teachers/delete/<int:teacher_id>", methods=["POST"])
@login_required(["admin"])
def delete_teacher(teacher_id):
    conn = get_db()

    teacher = conn.execute(
        "SELECT email FROM teachers WHERE id=?",
        (teacher_id,)
    ).fetchone()

    if teacher:
        conn.execute(
            "DELETE FROM teachers WHERE id=?",
            (teacher_id,)
        )
        conn.execute("""
            DELETE FROM users
            WHERE email=? AND role='teacher'
        """, (teacher["email"],))

        conn.commit()
        flash("Teacher deleted successfully.")

    conn.close()

    return redirect(url_for("teachers"))


# ---------------- ATTENDANCE ----------------

@app.route("/attendance", methods=["GET", "POST"])
@login_required(["admin", "teacher"])
def attendance():
    conn = get_db()

    if request.method == "POST":
        student_id = request.form.get("student_id")
        date = request.form.get("date")
        status = request.form.get("status")

        student = conn.execute(
            "SELECT id FROM students WHERE id=?",
            (student_id,)
        ).fetchone()

        if student and date and status in ("Present", "Absent"):
            conn.execute("""
                INSERT INTO attendance (student_id, date, status)
                VALUES (?, ?, ?)
            """, (student_id, date, status))

            conn.commit()
            flash("Attendance saved successfully.")
        else:
            flash("Please enter valid attendance details.")

    student_list = conn.execute("""
        SELECT * FROM students ORDER BY name
    """).fetchall()

    records = conn.execute("""
        SELECT attendance.*, students.name
        FROM attendance
        JOIN students ON students.id=attendance.student_id
        ORDER BY attendance.date DESC, attendance.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "attendance.html",
        students=student_list,
        records=records
    )


# ---------------- EXAMINATIONS ----------------

@app.route("/exams", methods=["GET", "POST"])
@login_required(["admin", "teacher"])
def exams():
    conn = get_db()

    if request.method == "POST":
        student_id = request.form.get("student_id")
        subject = request.form.get("subject", "").strip()

        try:
            marks = int(request.form.get("marks", ""))
            total = int(request.form.get("total", ""))

            student = conn.execute(
                "SELECT id FROM students WHERE id=?",
                (student_id,)
            ).fetchone()

            if not student or not subject or total <= 0 or marks < 0 or marks > total:
                raise ValueError

            conn.execute("""
                INSERT INTO exams (student_id, subject, marks, total)
                VALUES (?, ?, ?, ?)
            """, (student_id, subject, marks, total))

            conn.commit()
            flash("Examination marks saved successfully.")

        except (ValueError, TypeError):
            flash("Please enter valid examination details.")

    student_list = conn.execute("""
        SELECT * FROM students ORDER BY name
    """).fetchall()

    records = conn.execute("""
        SELECT exams.*, students.name
        FROM exams
        JOIN students ON students.id=exams.student_id
        ORDER BY exams.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "exams.html",
        students=student_list,
        records=records
    )


# ---------------- FEE MANAGEMENT ----------------

@app.route("/fees", methods=["GET", "POST"])
@login_required(["admin"])
def fees():
    conn = get_db()

    if request.method == "POST":
        student_id = request.form.get("student_id")
        status = request.form.get("status")

        try:
            amount = float(request.form.get("amount", ""))

            student = conn.execute(
                "SELECT id FROM students WHERE id=?",
                (student_id,)
            ).fetchone()

            if not student or amount < 0 or status not in ("Paid", "Pending"):
                raise ValueError

            conn.execute("""
                INSERT INTO fees (student_id, amount, status)
                VALUES (?, ?, ?)
            """, (student_id, amount, status))

            conn.commit()
            flash("Fee record saved successfully.")

        except (ValueError, TypeError):
            flash("Please enter valid fee details.")

    student_list = conn.execute("""
        SELECT * FROM students ORDER BY name
    """).fetchall()

    records = conn.execute("""
        SELECT fees.*, students.name
        FROM fees
        JOIN students ON students.id=fees.student_id
        ORDER BY fees.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "fees.html",
        students=student_list,
        records=records
    )


# ---------------- ACADEMIC REPORTS ----------------

@app.route("/reports")
@login_required(["admin", "teacher"])
def reports():
    conn = get_db()

    attendance_report = conn.execute("""
        SELECT
            students.name,
            COUNT(attendance.id) AS total_days,
            SUM(
                CASE WHEN attendance.status='Present'
                THEN 1 ELSE 0 END
            ) AS present_days
        FROM students
        LEFT JOIN attendance
        ON students.id=attendance.student_id
        GROUP BY students.id
    """).fetchall()

    exam_report = conn.execute("""
        SELECT
            students.name,
            exams.subject,
            exams.marks,
            exams.total
        FROM exams
        JOIN students ON students.id=exams.student_id
        ORDER BY students.name
    """).fetchall()

    conn.close()

    return render_template(
        "reports.html",
        attendance_report=attendance_report,
        exam_report=exam_report
    )


# ---------------- STUDENT DASHBOARD ----------------

@app.route("/student")
@login_required(["student"])
def student_portal():
    conn = get_db()

    student = conn.execute(
        "SELECT * FROM students WHERE email=?",
        (session["email"],)
    ).fetchone()

    attendance_records = []
    exam_records = []
    fee_records = []

    if student:
        attendance_records = conn.execute("""
            SELECT * FROM attendance
            WHERE student_id=?
            ORDER BY date DESC
        """, (student["id"],)).fetchall()

        exam_records = conn.execute("""
            SELECT * FROM exams
            WHERE student_id=?
            ORDER BY id DESC
        """, (student["id"],)).fetchall()

        fee_records = conn.execute("""
            SELECT * FROM fees
            WHERE student_id=?
            ORDER BY id DESC
        """, (student["id"],)).fetchall()

    conn.close()

    return render_template(
        "student_portal.html",
        student=student,
        attendance=attendance_records,
        exams=exam_records,
        fees=fee_records
    )


# ---------------- TEACHER DASHBOARD ----------------

@app.route("/teacher")
@login_required(["teacher"])
def teacher_portal():
    return render_template("teacher_portal.html")


# ---------------- RUN APPLICATION ----------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
