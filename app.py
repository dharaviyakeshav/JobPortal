from flask import Flask, render_template, redirect, url_for, request, session, g
import mysql.connector
import random
import smtplib
from email.mime.text import MIMEText
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "secret123")

UPLOAD_FOLDER = "static/uploads/blogs"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ---------------- SAFE DATABASE CONNECTION SETUP ----------------
def get_db():
    if 'db' not in g or not g.db.is_connected():
        g.db = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            port=int(os.getenv('DB_PORT', 4000)),
            database=os.getenv('DB_NAME', 'jobportal'),
            ssl_ca="/etc/ssl/certs/ca-certificates.crt" if os.path.exists("/etc/ssl/certs/ca-certificates.crt") else None
        )
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None and db.is_connected():
        db.close()

def get_cursor(dictionary=True):
    db = get_db()
    return db.cursor(dictionary=dictionary)

# ---------------- CONTEXT ----------------
@app.context_processor
def inject_user():
    return dict(
        logged_in='user_id' in session,
        user_name=session.get('name')
    )

@app.context_processor
def inject_footer_links():
    try:
        cur = get_cursor(dictionary=True)
        cur.execute("""
            SELECT section, title, url
            FROM footer_links
            WHERE status = 1
            ORDER BY section, id
        """)
        rows = cur.fetchall()
        cur.close()

        footer = {"Quick Links": [], "Company": [], "Support": []}
        for row in rows:
            footer.setdefault(row["section"], []).append(row)
        return dict(footer=footer)
    except Exception as e:
        print("Footer error:", e)
        return dict(footer={})

# ---------------- HELPER FUNCTIONS ----------------
def send_otp_email(email, otp):
    sender = "narotamdharaviya65@gmail.com"
    password = "voeb nvlt zfjh ucmn".replace(" ", "")

    msg = MIMEText(f"Your OTP for verification is: {otp}")
    msg["Subject"] = "OTP Verification - Job Portal"
    msg["From"] = f"Job Portal <{sender}>"
    msg["To"] = email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print("SMTP Error details:", str(e))
        return False

def check_subscription():
    if 'user_id' not in session: return False
    cur = get_cursor(dictionary=True)
    cur.execute("SELECT is_subscribed FROM users WHERE id=%s", (session['user_id'],))
    user = cur.fetchone()
    cur.close()
    return user and user.get('is_subscribed') == 1

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def admin_required():
    return 'admin_id' in session and session.get('admin_status') == 'approved'

def super_admin_required():
    return admin_required() and session.get('admin_role') == 'super_admin'

# =====================================================
# ================= USER SECTION ======================
# =====================================================

@app.route("/")
def index():
    cur = get_cursor(dictionary=True)

    if 'user_id' in session:
        cur.execute("""
            SELECT j.*, IF(a.id IS NULL,0,1) AS applied
            FROM jobs j
            LEFT JOIN job_applications a
            ON j.id=a.job_id AND a.user_id=%s
            ORDER BY j.id DESC LIMIT 4
        """, (session['user_id'],))
    else:
        cur.execute("SELECT *,0 AS applied FROM jobs ORDER BY id DESC LIMIT 4")
    jobs = cur.fetchall()

    cur.execute("""
        SELECT category, COUNT(*) AS total
        FROM jobs
        GROUP BY category
    """)
    categories = cur.fetchall()

    icon_map = {
        "Development": "bi-code-slash", "Design": "bi-brush",
        "Marketing": "bi-bar-chart", "Customer Service": "bi-headset",
        "Finance": "bi-currency-rupee", "HR": "bi-people",
        "Sales": "bi-graph-up-arrow", "IT Support": "bi-pc-display"
    }
    for c in categories:
        c["icon"] = icon_map.get(c["category"], "bi-briefcase")

    cur.execute("SELECT COUNT(*) AS total_jobs FROM jobs")
    total_jobs = cur.fetchone()["total_jobs"]

    cur.execute("SELECT COUNT(DISTINCT company) AS total_companies FROM jobs")
    total_companies = cur.fetchone()["total_companies"]

    cur.execute("SELECT COUNT(*) AS total_candidates FROM users")
    total_candidates = cur.fetchone()["total_candidates"]

    cur.execute("""
        SELECT COUNT(*) AS new_jobs 
        FROM jobs 
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    """)
    new_jobs = cur.fetchone()["new_jobs"]

    cur.execute("SELECT COUNT(*) AS total_applications FROM job_applications")
    total_placements = cur.fetchone()["total_applications"]

    cur.execute("SELECT DISTINCT location FROM jobs")
    locations = cur.fetchall()

    cur.execute("SELECT DISTINCT category FROM jobs")
    hero_categories = cur.fetchall()

    cur.execute("SELECT * FROM blogs ORDER BY created_at DESC LIMIT 3")
    recent_blogs = cur.fetchall()

    cur.execute("SELECT AVG(rating) AS avg_rating, COUNT(*) AS total_reviews FROM reviews")
    rating_data = cur.fetchone()

    cur.execute("""
        SELECT reviews.*, users.name 
        FROM reviews 
        JOIN users ON reviews.user_id = users.id
        ORDER BY reviews.id DESC
    """)
    all_reviews = cur.fetchall()
    cur.close()

    return render_template(
        "index.html", jobs=jobs, categories=categories, blogs=recent_blogs,
        total_jobs=total_jobs, total_companies=total_companies,
        total_candidates=total_candidates, new_jobs=new_jobs,
        total_placements=total_placements, locations=locations,
        hero_categories=hero_categories, reviews=all_reviews[:3],
        all_reviews=all_reviews, rating_data=rating_data
    )

@app.route("/submit-review", methods=["POST"])
def submit_review():
    if "user_id" not in session: return redirect(url_for("login"))
    rating = request.form.get("rating")
    review = request.form.get("review")
    user_id = session["user_id"]

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT id FROM reviews WHERE user_id=%s", (user_id,))
    if cur.fetchone():
        cur.execute("UPDATE reviews SET rating=%s, review=%s WHERE user_id=%s", (rating, review, user_id))
    else:
        cur.execute("INSERT INTO reviews (user_id, rating, review) VALUES (%s,%s,%s)", (user_id, rating, review))
    db.commit()
    cur.close()
    return redirect(url_for("index"))

@app.route("/delete-review")
def delete_review():
    if "user_id" not in session: return redirect(url_for("login"))
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM reviews WHERE user_id=%s", (session["user_id"],))
    db.commit()
    cur.close()
    return redirect(url_for("index"))

@app.route("/blogs")
def blog_list():
    cur = get_cursor(dictionary=True)
    cur.execute("SELECT * FROM blogs ORDER BY created_at DESC")
    blogs = cur.fetchall()
    cur.close()
    return render_template("blog_list.html", blogs=blogs)

@app.route("/blog/<int:blog_id>")
def blog_detail(blog_id):
    cur = get_cursor(dictionary=True)
    cur.execute("SELECT * FROM blogs WHERE id = %s", (blog_id,))
    blog = cur.fetchone()
    cur.close()
    if not blog: return "Blog Not Found", 404
    return render_template("blog_detail.html", blog=blog)

@app.route("/pricing")
def pricing():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template("pricing.html")

@app.route("/process-payment", methods=["POST"])
def process_payment():
    if 'user_id' in session:
        db = get_db()
        cur = db.cursor()
        cur.execute("UPDATE users SET is_subscribed=1 WHERE id=%s", (session['user_id'],))
        db.commit()
        cur.close()
        return {"status": "success"}
    return {"status": "error"}, 403

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if "otp" in request.form:
            user = session.get("temp_user")
            if not user: return render_template("register.html", error="Session expired. Please try again.")

            if str(request.form.get("otp")).strip() == str(user.get("otp")):
                db = get_db()
                cur = db.cursor()
                cur.execute(
                    "INSERT INTO users (name,email,password,verified,role) VALUES (%s,%s,%s,1,%s)",
                    (user["name"], user["email"], user["password"], user["role"])
                )
                db.commit()
                cur.close()
                session.pop("temp_user", None)
                return render_template("register.html", success=True)
            else:
                return render_template("register.html", show_otp=True, otp_error=True)

        email = request.form.get("email")
        if not email: return render_template("register.html", error="Invalid form request.")

        cur = get_cursor(dictionary=True)
        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        existing = cur.fetchone()
        cur.close()

        if existing:
            return render_template("register.html", error="This email is already registered. Please login.")

        role = request.form.get("role", "user")
        hashed = generate_password_hash(request.form["password"])
        otp = random.randint(100000, 999999)

        session["temp_user"] = {
            "name": request.form.get("name"), "email": email,
            "password": hashed, "role": role, "otp": otp
        }

        if send_otp_email(email, otp):
            return render_template("register.html", show_otp=True)
        else:
            session.pop("temp_user", None)
            return render_template("register.html", error="Failed to send OTP.")

    return render_template("register.html")

@app.route("/verify-otp", methods=["GET","POST"])
def verify_otp():
    if request.method == "POST":
        user = session.get("temp_user")
        if user and request.form["otp"] == str(user["otp"]):
            db = get_db()
            cur = db.cursor()
            cur.execute(
                "INSERT INTO users (name,email,password,verified) VALUES (%s,%s,%s,1)",
                (user["name"], user["email"], user["password"])
            )
            db.commit()
            cur.close()
            session.clear()
            return redirect("/login")
    return render_template("verify_otp.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form['email']
        password = request.form['password']

        cur = get_cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()

        if user and check_password_hash(user["password"], password):
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['role'] = user['role']
            session['email'] = user['email']
            return redirect(url_for('profile'))
        else:
            return render_template("login.html", error="Invalid email or password")

    return render_template("login.html")

@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    email = request.form.get("email")
    cur = get_cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cur.fetchone()
    cur.close()

    if user:
        otp = random.randint(100000, 999999)
        session["reset_email"] = email
        session["reset_otp"] = str(otp)
        send_otp_email(email, otp)
        return {"status": "success", "message": "OTP sent to your email"}
    return {"status": "error", "message": "Email not found!"}

@app.route("/reset-password", methods=["POST"])
def reset_password():
    otp_input = request.form.get("otp")
    new_password = request.form.get("password")
    confirm_password = request.form.get("confirm_password")
    
    stored_otp = session.get("reset_otp")
    reset_email = session.get("reset_email")

    if not stored_otp or otp_input != stored_otp:
        return {"status": "error", "message": "Invalid or expired OTP!"}
    if len(new_password) < 6:
        return {"status": "error", "message": "Password too short!"}
    if new_password != confirm_password:
        return {"status": "error", "message": "Passwords do not match!"}

    hashed_password = generate_password_hash(new_password)
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("UPDATE users SET password=%s WHERE email=%s", (hashed_password, reset_email))
        db.commit()
        cur.close()
        session.pop("reset_otp", None)
        session.pop("reset_email", None)
        return {"status": "success", "message": "Password reset successful!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin/login")

@app.route("/company-info", methods=["GET", "POST"])
def company_info():
    if 'user_id' not in session or session.get('role') != 'company':
        return redirect(url_for('login'))

    user_id = session['user_id']
    cur = get_cursor(dictionary=True)

    if request.method == "POST":
        c_name = request.form['company_name']
        website = request.form['website']
        industry = request.form['industry']
        desc = request.form['description']
        email = request.form['contact_email']

        cur.execute("SELECT id FROM company_profiles WHERE user_id = %s", (user_id,))
        profile = cur.fetchone()

        db = get_db()
        save_cur = db.cursor()
        if profile:
            save_cur.execute("""
                UPDATE company_profiles 
                SET company_name=%s, website=%s, industry=%s, description=%s, contact_email=%s 
                WHERE user_id=%s""", (c_name, website, industry, desc, email, user_id))
        else:
            save_cur.execute("""
                INSERT INTO company_profiles (user_id, company_name, website, industry, description, contact_email) 
                VALUES (%s, %s, %s, %s, %s, %s)""", (user_id, c_name, website, industry, desc, email))
        db.commit()
        save_cur.close()
        cur.close()
        return redirect(url_for('profile'))

    cur.execute("SELECT * FROM company_profiles WHERE user_id = %s", (user_id,))
    company_data = cur.fetchone()
    cur.close()
    return render_template("company_info.html", company=company_data)

@app.route("/profile")
def profile():
    if "user_id" not in session: return redirect(url_for("login"))

    cur = get_cursor(dictionary=True)
    user_id = session["user_id"]
    role = session.get("role", "user")

    cur.execute("SELECT id, name, email, role, plan_type, is_subscribed FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()

    profile_data = None
    jobs_data = []

    if role == "company":
        cur.execute("SELECT * FROM company_profiles WHERE user_id=%s", (user_id,))
        profile_data = cur.fetchone()

        cur.execute("""
            SELECT j.id, j.title, j.company, j.location, COUNT(a.id) AS total_applications
            FROM jobs j
            LEFT JOIN job_applications a ON j.id = a.job_id
            WHERE j.company_id = %s
            GROUP BY j.id ORDER BY j.id DESC
            """, (user_id,))
        jobs_data = cur.fetchall()
    else:
        cur.execute("SELECT * FROM user_profiles WHERE user_id=%s", (user_id,))
        profile_data = cur.fetchone()

        cur.execute("""
            SELECT j.* FROM jobs j
            JOIN job_applications a ON j.id = a.job_id
            WHERE a.user_id = %s ORDER BY j.id DESC
        """, (user_id,))
        jobs_data = cur.fetchall()

    cur.close()
    return render_template("profile.html", user=user, profile=profile_data, jobs=jobs_data, role=role)

@app.route("/job/<int:job_id>/applicants")
def job_applicants(job_id):
    if "user_id" not in session or session.get("role") != "company":
        return redirect(url_for("login"))

    cur = get_cursor(dictionary=True)
    cur.execute("""
        SELECT u.id, u.name, u.email, up.phone, up.location, a.status, a.id AS application_id, up.experience_level
        FROM job_applications a
        JOIN users u ON a.user_id = u.id
        LEFT JOIN user_profiles up ON up.user_id = u.id
        WHERE a.job_id = %s
    """, (job_id,))
    applicants = cur.fetchall()
    cur.close()
    return render_template("applicants.html", applicants=applicants)

@app.route("/user/<int:user_id>")
def view_user_profile(user_id):
    if "user_id" not in session or session.get("role") != "company":
        return redirect(url_for("login"))

    cur = get_cursor(dictionary=True)
    cur.execute("SELECT id, name, email FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()

    cur.execute("SELECT * FROM user_profiles WHERE user_id=%s", (user_id,))
    profile = cur.fetchone()
    cur.close()
    return render_template("view_user_profile.html", user=user, profile=profile)

RESUME_FOLDER = "static/resumes"
os.makedirs(RESUME_FOLDER, exist_ok=True)

@app.route("/personal-info", methods=["GET", "POST"])
def personal_info():
    if "user_id" not in session: return redirect(url_for("login"))

    cur = get_cursor(dictionary=True)
    cur.execute("SELECT * FROM user_profiles WHERE user_id=%s", (session["user_id"],))
    profile = cur.fetchone()

    if request.method == "POST":
        phone = request.form["phone"]
        gender = request.form["gender"]
        dob = request.form["dob"]
        location = request.form["location"]
        experience = request.form["experience"]
        job_title = request.form["job_title"]
        salary = request.form["salary"]
        skills = request.form["skills"]
        linkedin = request.form["linkedin"]
        portfolio = request.form["portfolio"]

        resume_file = request.files.get("resume")
        resume_filename = None

        if resume_file and resume_file.filename != "":
            filename = secure_filename(resume_file.filename)
            resume_path = os.path.join(RESUME_FOLDER, filename)
            resume_file.save(resume_path)
            resume_filename = filename

        db = get_db()
        save_cur = db.cursor()
        if profile:
            if resume_filename:
                save_cur.execute("""
                    UPDATE user_profiles SET phone=%s, gender=%s, date_of_birth=%s, location=%s,
                    experience_level=%s, current_job_title=%s, expected_salary=%s, skills=%s,
                    linkedin=%s, portfolio=%s, resume=%s WHERE user_id=%s
                """, (phone, gender, dob, location, experience, job_title, salary, skills, linkedin, portfolio, resume_filename, session["user_id"]))
            else:
                save_cur.execute("""
                    UPDATE user_profiles SET phone=%s, gender=%s, date_of_birth=%s, location=%s,
                    experience_level=%s, current_job_title=%s, expected_salary=%s, skills=%s,
                    linkedin=%s, portfolio=%s WHERE user_id=%s
                """, (phone, gender, dob, location, experience, job_title, salary, skills, linkedin, portfolio, session["user_id"]))
        else:
            save_cur.execute("""
                INSERT INTO user_profiles (user_id, phone, gender, date_of_birth, location, experience_level, current_job_title, expected_salary, skills, linkedin, portfolio, resume)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (session["user_id"], phone, gender, dob, location, experience, job_title, salary, skills, linkedin, portfolio, resume_filename))

        db.commit()
        save_cur.close()
        cur.close()
        return redirect(url_for("profile"))

    cur.close()
    return render_template("personal_info.html", profile=profile)

@app.route("/withdraw/<int:job_id>")
def withdraw_job(job_id):
    if "user_id" not in session: return redirect(url_for("login"))
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM job_applications WHERE user_id=%s AND job_id=%s", (session["user_id"], job_id))
    db.commit()
    cur.close()
    return redirect(request.referrer or "/")

@app.route('/update-profile', methods=['GET', 'POST'])
def update_profile():
    if 'user_id' not in session: return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        db = get_db()
        cur = db.cursor()
        if password:
            hashed_pass = generate_password_hash(password)
            cur.execute("UPDATE users SET name=%s, email=%s, password=%s WHERE id=%s", (name, email, hashed_pass, session['user_id']))
        else:
            cur.execute("UPDATE users SET name=%s, email=%s WHERE id=%s", (name, email, session['user_id']))
        db.commit()
        cur.close()

        session['name'] = name
        session['email'] = email
        return redirect(url_for('profile'))

    cur = get_cursor(dictionary=True)
    cur.execute("SELECT name, email FROM users WHERE id=%s", (session['user_id'],))
    user = cur.fetchone()
    cur.close()

    return render_template("update_profile.html", name=user['name'], email=user['email'])

@app.route('/deactivate-account')
def deactivate_account():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE users SET status='deactivated' WHERE id=%s", (session['user_id'],))
    db.commit()
    cur.close()
    session.clear()
    return redirect(url_for('login'))

@app.route('/delete-account')
def delete_account():
    if 'user_id' not in session: return redirect(url_for('login'))
    user_id = session['user_id']
    role = session.get('role')

    db = get_db()
    cur = db.cursor()
    if role == "company":
        cur.execute("DELETE FROM jobs WHERE company_id=%s", (user_id,))
    cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
    db.commit()
    cur.close()
    session.clear()
    return redirect(url_for('register'))

@app.route("/jobs")
def jobs():
    keyword = request.args.get("keyword")
    category = request.args.get("category")
    job_type = request.args.get("type")
    location = request.args.get("location")

    all_categories = ["Development", "Design", "Marketing", "Customer Service", "Finance", "HR", "Sales", "IT Support"]
    cur = get_cursor(dictionary=True)

    cur.execute("SELECT company, COUNT(*) as job_count FROM jobs GROUP BY company ORDER BY job_count DESC LIMIT 4")
    top_companies = cur.fetchall()

    query = """
        SELECT j.*, IF(a.id IS NULL, 0, 1) AS applied
        FROM jobs j
        LEFT JOIN job_applications a ON j.id = a.job_id AND a.user_id = %s
        WHERE 1=1
    """
    params = [session.get("user_id", 0)]

    if keyword:
        query += " AND j.title LIKE %s"
        params.append(f"%{keyword}%")
    if category and category in all_categories:
        query += " AND j.category = %s"
        params.append(category)
    if job_type:
        query += " AND j.job_type = %s"
        params.append(job_type)
    if location:
        query += " AND j.location = %s"
        params.append(location)

    query += " ORDER BY j.id DESC"
    cur.execute(query, tuple(params))
    jobs_data = cur.fetchall()
    cur.close()

    return render_template("job.html", jobs=jobs_data, categories=all_categories, top_companies=top_companies)

@app.route("/job/<int:job_id>")
def job_detail(job_id):
    cur = get_cursor(dictionary=True)
    cur.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
    job = cur.fetchone()
    if not job: return "Job Not Found", 404

    applied = False
    if 'user_id' in session:
        cur.execute("SELECT id FROM job_applications WHERE user_id = %s AND job_id = %s", (session['user_id'], job_id))
        if cur.fetchone(): applied = True

    cur.execute("""
        SELECT * FROM jobs
        WHERE (category = %s OR company_id = %s) AND id != %s
        ORDER BY created_at DESC LIMIT 4
    """, (job['category'], job['company_id'], job_id))
    related_jobs = cur.fetchall()
    cur.close()

    return render_template("job_detail.html", job=job, applied=applied, related_jobs=related_jobs)

@app.route("/apply/<int:job_id>")
def apply_job(job_id):
    if "user_id" not in session: return redirect(url_for("login"))
    if session.get("role") == "company": return redirect(url_for("job_detail", job_id=job_id))
    if not check_subscription(): return redirect(url_for("pricing"))

    cur = get_cursor(dictionary=True)
    cur.execute("SELECT phone, gender, date_of_birth, location, experience_level FROM user_profiles WHERE user_id=%s", (session["user_id"],))
    profile = cur.fetchone()

    if not profile or any(value is None or value == "" for value in profile.values()):
        cur.close()
        return redirect(url_for("profile", incomplete=1))

    try:
        db = get_db()
        save_cur = db.cursor()
        save_cur.execute("INSERT INTO job_applications (user_id, job_id) VALUES (%s,%s)", (session["user_id"], job_id))
        db.commit()
        save_cur.close()

        cur.execute("""
            SELECT j.title, j.company, u.email AS company_email
            FROM jobs j JOIN users u ON j.company_id = u.id
            WHERE j.id = %s
        """, (job_id,))
        job = cur.fetchone()

        send_job_apply_email(session["email"], session["name"], job["title"], job["company"])
        send_company_application_email(job["company_email"], job["company"], session["name"], job["title"])
    except Exception as e:
        print("Apply Error:", e)

    cur.close()
    return redirect(request.referrer or "/")

def send_job_apply_email(email, name, job_title, company):
    sender_email = "narotamdharaviya65@gmail.com"
    password = "wckt cxmm xvdu vulf"
    body = f"Hello {name},\n\nYour job application for {job_title} at {company} was successful!\n\nBest of luck!"
    msg = MIMEText(body)
    msg["Subject"] = "Job Application Successful"
    msg["From"] = f"Job Portal <{sender_email}>"
    msg["To"] = email
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, email, msg.as_string())
    except Exception as e: print(e)

def send_company_application_email(company_email, company, candidate, job_title):
    sender_email = "narotamdharaviya65@gmail.com"
    password = "wckt cxmm xvdu vulf"
    body = f"Hello {company},\n\nYou received a new application from {candidate} for {job_title}."
    msg = MIMEText(body)
    msg["Subject"] = "New Job Application Received"
    msg["From"] = f"Job Portal <{sender_email}>"
    msg["To"] = company_email
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, company_email, msg.as_string())
    except Exception as e: print(e)

@app.route("/application/<int:app_id>/accept")
def accept_application(app_id):
    if session.get("role") != "company": return redirect("/")
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("UPDATE job_applications SET status='accepted' WHERE id=%s", (app_id,))
    db.commit()

    cur.execute("""
        SELECT u.email, u.name, j.title, j.company
        FROM job_applications a
        JOIN users u ON a.user_id = u.id
        JOIN jobs j ON a.job_id = j.id
        WHERE a.id=%s
    """, (app_id,))
    data = cur.fetchone()
    send_application_status_email(data["email"], data["name"], data["title"], data["company"], "accepted")
    cur.close()
    return redirect(request.referrer or "/profile")

@app.route("/application/<int:app_id>/reject")
def reject_application(app_id):
    if session.get("role") != "company": return redirect("/")
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("UPDATE job_applications SET status='rejected' WHERE id=%s", (app_id,))
    db.commit()

    cur.execute("""
        SELECT u.email, u.name, j.title, j.company
        FROM job_applications a
        JOIN users u ON a.user_id = u.id
        JOIN jobs j ON a.job_id = j.id
        WHERE a.id=%s
    """, (app_id,))
    data = cur.fetchone()
    send_application_status_email(data["email"], data["name"], data["title"], data["company"], "rejected")
    cur.close()
    return redirect(request.referrer or "/profile")

def send_application_status_email(to_email, user_name, job_title, company, status):
    msg = MIMEText(f"Hello {user_name},\n\nYour application status for {job_title} at {company} has been updated to: {status}.")
    msg["Subject"] = f"Application {status.capitalize()} - {job_title}"
    msg["From"] = "Job Portal <narotamdharaviya65@gmail.com>"
    msg["To"] = to_email
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login("narotamdharaviya65@gmail.com", "wckt cxmm xvdu vulf")
        server.send_message(msg)
        server.quit()
    except Exception as e: print(e)

# =====================================================
# ================= ADMIN SECTION =====================
# =====================================================

@app.route("/admin")
def admin_index():
    if admin_required(): return redirect("/admin/dashboard")
    return redirect("/admin/login")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        cur = get_cursor(dictionary=True)
        cur.execute("SELECT * FROM admins WHERE email=%s AND password=%s", (email, password))
        admin = cur.fetchone()
        cur.close()

        if not admin: return render_template("admin/login.html", error="Invalid Email or Password")
        if admin["status"] != "approved": return render_template("admin/login.html", error="Account not approved!")

        session["admin_id"] = admin["id"]
        session["admin_name"] = admin["name"]
        session["admin_role"] = admin["role"]
        session["admin_status"] = admin["status"]
        return redirect("/admin/dashboard")

    return render_template("admin/login.html")

@app.route('/admin/reviews')
def admin_reviews():
    if not admin_required(): return redirect("/admin/login")
    cur = get_cursor(dictionary=True)
    cur.execute("""
        SELECT reviews.id, reviews.rating, reviews.review, reviews.created_at, users.name
        FROM reviews JOIN users ON reviews.user_id = users.id
        ORDER BY reviews.id DESC
    """)
    reviews = cur.fetchall()
    cur.close()
    return render_template("admin/review.html", reviews=reviews)

@app.route('/admin/delete-review/<int:id>', methods=['POST'])
def admin_delete_review(id):
    if not admin_required(): return redirect("/admin/login")
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM reviews WHERE id=%s", (id,))
    db.commit()
    cur.close()
    return redirect(url_for('admin_reviews'))

@app.route("/admin/dashboard")
def admin_dashboard():
    if not admin_required(): return redirect("/admin/login")
    cur = get_cursor(dictionary=False)

    cur.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM feedback")
    total_feedback = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM blogs")
    total_blogs = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM job_applications")
    total_applications = cur.fetchone()[0]
    cur.close()

    return render_template("admin/dashboard.html", total_jobs=total_jobs, total_feedback=total_feedback, total_blogs=total_blogs, total_users=total_users, total_applications=total_applications)

@app.route("/admin/user")
def admin_users():
    if not admin_required(): return redirect("/admin/login")
    cur = get_cursor(dictionary=True)
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()
    cur.close()
    return render_template("admin/users.html", users=users)

@app.route("/admin/blogs")
def admin_blogs():
    if not admin_required(): return redirect("/admin/login")
    cur = get_cursor(dictionary=True)
    cur.execute("SELECT * FROM blogs ORDER BY created_at DESC")
    blogs = cur.fetchall()
    cur.close()
    return render_template("admin/blogs.html", blogs=blogs)

@app.route("/admin/blog/add", methods=["GET", "POST"])
def admin_add_blog():
    if not admin_required(): return redirect("/admin/login")

    if request.method == "POST":
        image_file = request.files.get("image")
        image_path = None
        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
            image_path = f"uploads/blogs/{filename}"
            image_file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO blogs (title, content, author, category, image_url)
            VALUES (%s, %s, %s, %s, %s)
        """, (request.form["title"], request.form["content"], request.form["author"], request.form["category"], image_path))
        db.commit()
        cur.close()
        return redirect("/admin/blogs")

    return render_template("admin/blog_form.html", title="Add New Blog")

@app.route("/admin/blog/delete/<int:id>")
def admin_delete_blog(id):
    if not admin_required(): return redirect("/admin/login")
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM blogs WHERE id = %s", (id,))
    db.commit()
    cur.close()
    return redirect("/admin/blogs")

@app.route("/admin/jobs")
def admin_jobs():
    if not admin_required(): return redirect("/admin/login")
    cur = get_cursor(dictionary=True)
    cur.execute("SELECT * FROM jobs ORDER BY id DESC")
    jobs = cur.fetchall()
    cur.close()
    return render_template("admin/jobs.html", jobs=jobs)

@app.route("/job/add", methods=["GET","POST"])
def admin_add_job():
    if "user_id" not in session: return redirect(url_for("login"))
    if not check_subscription(): return redirect(url_for('pricing'))

    if request.method == "POST":
        try:
            c_id = session.get("user_id")
            title = request.form.get("title")
            company = request.form.get("company")
            location = request.form.get("location")
            salary = request.form.get("salary")
            category = request.form.get("category")
            job_type = request.form.get("job_type")
            description = request.form.get("description")

            db = get_db()
            cur = db.cursor()
            cur.execute("""
                INSERT INTO jobs (title, company, company_id, location, salary, category, job_type, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (title, company, c_id, location, salary, category, job_type, description))
            db.commit()
            cur.close()
            return redirect(url_for("profile", success="Job added successfully!"))
        except Exception as e:
            return f"Error: {e}"

    return render_template("job_form.html", title="Add Job", job=None)

@app.route("/admin/job/edit/<int:id>", methods=["GET","POST"])
def admin_edit_job(id):
    if "user_id" not in session: return redirect("/login")
    if not check_subscription(): return redirect(url_for('pricing'))

    db = get_db()
    if request.method == "POST":
        cur = db.cursor()
        cur.execute("""
            UPDATE jobs SET title=%s, company=%s, location=%s,
            salary=%s, category=%s, job_type=%s, description=%s WHERE id=%s
        """, (request.form["title"], request.form["company"], request.form["location"], request.form["salary"], request.form["category"], request.form["job_type"], request.form["description"], id))
        db.commit()
        cur.close()
        return redirect("/profile")

    cur = get_cursor(dictionary=True)
    cur.execute("SELECT * FROM jobs WHERE id=%s", (id,))
    job = cur.fetchone()
    cur.close()
    return render_template("job_form.html", title="Edit Job", job=job)

@app.route("/admin/job/delete/<int:id>")
def admin_delete_job(id):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM jobs WHERE id=%s", (id,))
    db.commit()
    cur.close()
    return redirect("/profile")

@app.route("/admin/manage-admins")
def manage_admins():
    if not super_admin_required(): return redirect("/admin/login")
    cur = get_cursor(dictionary=True)
    cur.execute("SELECT * FROM admins")
    admins = cur.fetchall()
    cur.close()
    return render_template("admin/admins.html", admins=admins)

@app.route("/admin/approve-admin/<int:id>")
def approve_admin(id):
    if not super_admin_required(): return redirect("/admin/login")
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE admins SET status='approved' WHERE id=%s", (id,))
    db.commit()
    cur.close()
    return redirect("/admin/manage-admins")

@app.route("/admin/feedback")
def admin_feedback():
    if not admin_required(): return redirect("/admin/login")
    cur = get_cursor(dictionary=True)
    cur.execute("SELECT * FROM feedback ORDER BY created_at DESC")
    feedbacks = cur.fetchall()
    cur.close()
    return render_template("admin/feedback.html", feedbacks=feedbacks)

@app.route("/admin/feedback/delete/<int:id>")
def delete_feedback(id):
    if not admin_required(): return redirect("/admin/login")
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM feedback WHERE id=%s", (id,))
    db.commit()
    cur.close()
    return redirect("/admin/feedback")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/admin/applications")
def admin_applications():
    if "admin_id" not in session: return redirect(url_for("admin_login"))
    cur = get_cursor(dictionary=True)
    cur.execute("""
        SELECT ja.id AS application_id, u.id AS user_id, u.email, j.id AS job_id, j.title, ja.applied_at, ja.status
        FROM job_applications ja
        JOIN users u ON ja.user_id = u.id
        JOIN jobs j ON ja.job_id = j.id
        ORDER BY ja.applied_at DESC
    """)
    applications = cur.fetchall()
    cur.close()
    return render_template("admin/admin_applications.html", applications=applications)

@app.route("/admin/user/delete/<int:id>", methods=["POST"])
def admin_delete_user(id):
    if not admin_required(): return redirect("/admin/login")
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM jobs WHERE company_id=%s", (id,))
        cur.execute("DELETE FROM job_applications WHERE user_id=%s", (id,))
        cur.execute("DELETE FROM user_profiles WHERE user_id=%s", (id,))
        cur.execute("DELETE FROM users WHERE id=%s", (id,))
        db.commit()
    except Exception as e:
        db.rollback()
    finally:
        cur.close()
    return redirect("/admin/user")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        name = f"{first_name} {last_name}".strip()
        email = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        try:
            db = get_db()
            cur = db.cursor()
            cur.execute("INSERT INTO feedback (name, email, subject, message) VALUES (%s,%s,%s,%s)", (name, email, subject, message))
            db.commit()
            cur.close()
        except Exception as db_err:
            print("DATABASE ERROR", db_err)

        SENDER_EMAIL = "narotamdharaviya65@gmail.com"
        APP_PASSWORD = "voeb nvlt zfjh ucmn".replace(" ", "") 
        ADMIN_EMAIL = "narotamdharaviya65@gmail.com"

        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(SENDER_EMAIL, APP_PASSWORD)

            admin_body = f"New Contact Request 📩\n\nName: {name}\nEmail: {email}\nSubject: {subject}\n\nMessage:\n{message}"
            admin_msg = MIMEText(admin_body)
            admin_msg["Subject"] = f"New Contact: {subject}"
            admin_msg["From"] = SENDER_EMAIL
            admin_msg["To"] = ADMIN_EMAIL
            admin_msg["Reply-To"] = email
            server.sendmail(SENDER_EMAIL, ADMIN_EMAIL, admin_msg.as_string())

            user_body = f"Hi {name},\n\nThank you for contacting Job Portal! We received your message regarding: '{subject}'.\n\nBest regards,\nJob Portal Support Team"
            user_msg = MIMEText(user_body)
            user_msg["Subject"] = "We received your request – Job Portal"
            user_msg["From"] = SENDER_EMAIL
            user_msg["To"] = email
            server.sendmail(SENDER_EMAIL, email, user_msg.as_string())
            server.quit()
        except Exception as e:
            print("EMAIL ERROR:", str(e))

        return render_template("contact.html", success=True)

    return render_template("contact.html")

@app.route("/privacy-policy")
def privacy_policy():
    return render_template("privacy_policy.html")

@app.route("/terms")
def terms_conditions():
    return render_template("terms_conditions.html")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
