from flask import Flask, render_template, redirect, url_for, request, session
import mysql.connector
import random
import smtplib
from email.mime.text import MIMEText
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash




app = Flask(__name__)
app.secret_key = "secret123"

# ---------------- DATABASE ----------------
import os
import mysql.connector

# Environment Variables માંથી વિગતો વાંચશે
db = mysql.connector.connect(
    host=os.getenv('DB_HOST'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    port=int(os.getenv('DB_PORT', 4000)),
    database=os.getenv('DB_NAME', 'test'),
    ssl_ca="/etc/ssl/certs/ca-certificates.crt"  # TiDB SSL કનેક્શન માટે
)
cursor = db.cursor(dictionary=True)

# ---------------- CONTEXT ----------------
@app.context_processor
def inject_user():
    return dict(
        logged_in='user_id' in session,
        user_name=session.get('name')
    )

# ---------------- OTP EMAIL ----------------
import smtplib
from email.mime.text import MIMEText

# ---------------- OTP EMAIL (FIXED) ----------------
def send_otp_email(email, otp):
    sender = "narotamdharaviya65@gmail.com"
    # સ્પેશ (Spaces) દૂર કરીને પાસવર્ડ લખ્યો છે
    password = "voeb nvlt zfjh ucmn" 

    msg = MIMEText(f"Your OTP for verification is: {otp}")
    msg["Subject"] = "OTP Verification - Job Portal"
    msg["From"] = f"Job Portal <{sender}>"
    msg["To"] = email

    try:
        # Port 587 (TLS) વાપરવાથી બ્લોકિંગ અને ટાઈમઆઉટની તકલીફ નહી રહે
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, email, msg.as_string())
        server.quit()
        print(f"OTP Sent successfully to {email}")
        return True
    except Exception as e:
        print("SMTP Error details:", str(e))
        return False



# =====================================================
# ================= USER SECTION ======================
# =====================================================

def get_cursor(dict_mode=True):
    return db.cursor(dictionary=dict_mode)


# ---------------- HOME ----------------
@app.route("/")
def index():
    cur = db.cursor(dictionary=True)

    # ---------------- RECENT JOBS ----------------
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

    # ---------------- CATEGORIES ----------------
    cur.execute("""
        SELECT category, COUNT(*) AS total
        FROM jobs
        GROUP BY category
    """)
    categories = cur.fetchall()

    icon_map = {
        "Development": "bi-code-slash",
        "Design": "bi-brush",
        "Marketing": "bi-bar-chart",
        "Customer Service": "bi-headset",
        "Finance": "bi-currency-rupee",
        "HR": "bi-people",
        "Sales": "bi-graph-up-arrow",
        "IT Support": "bi-pc-display"
    }

    for c in categories:
        c["icon"] = icon_map.get(c["category"], "bi-briefcase")

    # ---------------- HERO STATS ----------------
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

    # ---------------- HERO DROPDOWNS ----------------
    cur.execute("SELECT DISTINCT location FROM jobs ")
    locations = cur.fetchall()

    cur.execute("SELECT DISTINCT category FROM jobs")
    hero_categories = cur.fetchall()

    # ---------------- BLOGS ----------------
    cur.execute("SELECT * FROM blogs ORDER BY created_at DESC LIMIT 3")
    recent_blogs = cur.fetchall()
    # -------- REVIEWS --------
    cur.execute("""
    SELECT r.*, u.name
    FROM reviews r
    JOIN users u ON r.user_id = u.id
    ORDER BY r.created_at DESC
    LIMIT 5
    """)
    reviews = cur.fetchall()

    cur.execute("SELECT AVG(rating) AS avg_rating, COUNT(*) AS total_reviews FROM reviews")
    rating_data = cur.fetchone()
    # All reviews (modal ke liye)
    cur.execute("""
        SELECT reviews.*, users.name 
        FROM reviews 
        JOIN users ON reviews.user_id = users.id
        ORDER BY reviews.id DESC
    """)
    all_reviews = cur.fetchall()

    cur.close()

    return render_template(
    "index.html",
    jobs=jobs,
    categories=categories,
    blogs=recent_blogs,

    total_jobs=total_jobs,
    total_companies=total_companies,
    total_candidates=total_candidates,
    new_jobs=new_jobs,
    total_placements=total_placements,

    locations=locations,
    hero_categories=hero_categories,

    # ⭐ NEW
    reviews=all_reviews[:3],
    all_reviews=all_reviews,   # modal ke liye sab
    rating_data=rating_data
)


#----------review -----------
@app.route("/submit-review", methods=["POST"])
def submit_review():
    if "user_id" not in session:
        return redirect(url_for("login"))

    rating = request.form.get("rating")
    review = request.form.get("review")
    user_id = session["user_id"]

    cur = db.cursor(dictionary=True)

    # check existing review
    cur.execute("SELECT id FROM reviews WHERE user_id=%s", (user_id,))
    existing = cur.fetchone()

    if existing:
        # update
        cur.execute(
            "UPDATE reviews SET rating=%s, review=%s WHERE user_id=%s",
            (rating, review, user_id)
        )
    else:
        # insert
        cur.execute(
            "INSERT INTO reviews (user_id, rating, review) VALUES (%s,%s,%s)",
            (user_id, rating, review)
        )

    db.commit()
    cur.close()

    return redirect(url_for("index"))

#---------delete review--------
@app.route("/delete-review")
def delete_review():
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = db.cursor()
    cur.execute("DELETE FROM reviews WHERE user_id=%s", (session["user_id"],))
    db.commit()
    cur.close()

    return redirect(url_for("index"))


#----------- blogs --------------
@app.route("/blogs")
def blog_list():
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM blogs ORDER BY created_at DESC")
    blogs = cur.fetchall()
    cur.close()
    return render_template("blog_list.html", blogs=blogs)


# --- BLOG DETAIL PAGE ------
@app.route("/blog/<int:blog_id>")
def blog_detail(blog_id):
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM blogs WHERE id = %s", (blog_id,))
    blog = cur.fetchone()
    cur.close()
    if not blog:
        return "Blog Not Found", 404
    return render_template("blog_detail.html", blog=blog)




# --- Pricing Page ---
@app.route("/pricing")
def pricing():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template("pricing.html")


# --- Process Payment (Simulated) ---
@app.route("/process-payment", methods=["POST"])
def process_payment():
    if 'user_id' in session:
        cur = db.cursor()
        cur.execute("UPDATE users SET is_subscribed=1 WHERE id=%s", (session['user_id'],))
        db.commit()
        cur.close()
        return {"status": "success"}
    return {"status": "error"}, 403


@app.context_processor
def inject_footer_links():
    cur = db.cursor(dictionary=True)

    cur.execute("""
        SELECT section, title, url
        FROM footer_links
        WHERE status = 1
        ORDER BY section, id
    """)

    rows = cur.fetchall()
    cur.close()

    footer = {
        "Quick Links": [],
        "Company": [],
        "Support": []
    }

    for row in rows:
        footer.setdefault(row["section"], []).append(row)

    return dict(footer=footer)
# ---------------- REGISTER ROUTE (FIXED) ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        # ૧. OTP Submitting Logic
        if "otp" in request.form:
            user = session.get("temp_user")
            
            if not user:
                return render_template("register.html", error="Session expired. Please try again.")

            if str(request.form.get("otp")).strip() == str(user.get("otp")):
                cur = get_cursor(False)
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

        # ૨. Registered Check (નવું ફોર્મ સબમિટ થાય ત્યારે જ ચાલશે)
        email = request.form.get("email")
        if not email:
            return render_template("register.html", error="Invalid form request.")

        cur = get_cursor(True)
        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        existing = cur.fetchone()
        cur.close()

        if existing:
            return render_template("register.html", error="This email is already registered. Please login.")

        # ૩. Normal Registration & Send OTP
        role = request.form.get("role", "user")
        hashed = generate_password_hash(request.form["password"])
        otp = random.randint(100000, 999999)

        session["temp_user"] = {
            "name": request.form.get("name"),
            "email": email,
            "password": hashed,
            "role": role,
            "otp": otp
        }

        # Email મોકલવાની ચકાસણી
        email_sent = send_otp_email(email, otp)
        
        if email_sent:
            return render_template("register.html", show_otp=True)
        else:
            session.pop("temp_user", None)
            return render_template("register.html", error="Failed to send OTP. Please check your email address or SMTP setup.")

    return render_template("register.html")

def check_subscription():
    if 'user_id' not in session: return False
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT is_subscribed FROM users WHERE id=%s", (session['user_id'],))
    user = cur.fetchone()
    return user['is_subscribed'] == 1



#------------verify otp------------------
@app.route("/verify-otp", methods=["GET","POST"])
def verify_otp():
    if request.method == "POST":
        user = session.get("temp_user")
        if user and request.form["otp"] == str(user["otp"]):
            cursor.execute(
                "INSERT INTO users (name,email,password,verified) VALUES (%s,%s,%s,1)",
                (user["name"], user["email"], user["password"])
            )
            db.commit()
            session.clear()
            return redirect("/login")

    return render_template("verify_otp.html")


# ---------------- Login ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form['email']
        password = request.form['password']

        cur = db.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()   # ✅ cursor close
    
        # ✅ Password hash check
        if user and check_password_hash(user["password"], password):
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['role'] = user['role']
            session['email'] = user['email']

            # ✅ Role based redirect
            if user['role'] == "company":
                return redirect(url_for('profile'))
            else:
                return redirect(url_for('profile'))

        else:
            return render_template("login.html", error="Invalid email or password")

    return render_template("login.html")

# ---------------- PASSWORD RESET ----------------
@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    email = request.form.get("email")
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cur.fetchone()

    if user:
        otp = random.randint(100000, 999999)
        session["reset_email"] = email
        session["reset_otp"] = str(otp)
        
        # Reuse your existing email function
        send_otp_email(email, otp)
        return {"status": "success", "message": "OTP sent to your email"}
    
    return {"status": "error", "message": "Email not found!"}

@app.route("/reset-password", methods=["POST"])
def reset_password():
    otp_input = request.form.get("otp")
    new_password = request.form.get("password")
    confirm_password = request.form.get("confirm_password")
    
    # Session data check
    stored_otp = session.get("reset_otp")
    reset_email = session.get("reset_email")

    if not stored_otp or otp_input != stored_otp:
        return {"status": "error", "message": "Invalid or expired OTP!"}
    
    # Server-side validation
    if len(new_password) < 6:
        return {"status": "error", "message": "Password too short!"}
        
    if new_password != confirm_password:
        return {"status": "error", "message": "Passwords do not match!"}

    try:
        cur = db.cursor()
        cur.execute("UPDATE users SET password=%s WHERE email=%s", (new_password, reset_email))
        db.commit()
        cur.close()
        
        # Cleanup
        session.pop("reset_otp", None)
        session.pop("reset_email", None)
        return {"status": "success", "message": "Password reset successful! You can now login."}
    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error", "message": "Something went wrong on the server."}
    
    
#-------logout--------------
@app.route("/logout")
def logout():
        session.clear()
        return redirect("/login")


@app.route("/admin/logout")
def admin_logout():
        session.clear()
        return redirect("/admin/login")
#-----------Company INFO -------------------

@app.route("/company-info", methods=["GET", "POST"])
def company_info():
    if 'user_id' not in session or session.get('role') != 'company':
        return redirect(url_for('login'))

    user_id = session['user_id']
    cur = db.cursor(dictionary=True)

    if request.method == "POST":
        c_name = request.form['company_name']
        website = request.form['website']
        industry = request.form['industry']
        desc = request.form['description']
        email = request.form['contact_email']

        # Check agar profile pehle se hai
        cur.execute("SELECT id FROM company_profiles WHERE user_id = %s", (user_id,))
        profile = cur.fetchone()

        if profile:
            cur.execute("""
                UPDATE company_profiles 
                SET company_name=%s, website=%s, industry=%s, description=%s, contact_email=%s 
                WHERE user_id=%s""", (c_name, website, industry, desc, email, user_id))
        else:
            cur.execute("""
                INSERT INTO company_profiles (user_id, company_name, website, industry, description, contact_email) 
                VALUES (%s, %s, %s, %s, %s, %s)""", (user_id, c_name, website, industry, desc, email))
        
        db.commit()
        return redirect(url_for('profile'))

    cur.execute("SELECT * FROM company_profiles WHERE user_id = %s", (user_id,))
    company_data = cur.fetchone()
    return render_template("company_info.html", company=company_data)



@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = db.cursor(dictionary=True)
    user_id = session["user_id"]
    role = session.get("role", "user")

    cur.execute("SELECT id, name, email, role, plan_type, is_subscribed FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()

    profile_data = None
    jobs_data = []

    if role == "company":

        # company profile
        cur.execute("SELECT * FROM company_profiles WHERE user_id=%s", (user_id,))
        profile_data = cur.fetchone()

        # 🔥 company ki jobs + applied users + unka profile
        cur.execute("""
            SELECT 
            j.id,
            j.title,
            j.company,
            j.location,
            COUNT(a.id) AS total_applications
            FROM jobs j
            LEFT JOIN job_applications a ON j.id = a.job_id
            WHERE j.company_id = %s
            GROUP BY j.id
            ORDER BY j.id DESC
            """, (user_id,))
        jobs_data = cur.fetchall()

    else:
        # user profile
        cur.execute("SELECT * FROM user_profiles WHERE user_id=%s", (user_id,))
        profile_data = cur.fetchone()

        # applied jobs
        cur.execute("""
            SELECT j.* FROM jobs j
            JOIN job_applications a ON j.id = a.job_id
            WHERE a.user_id = %s
            ORDER BY j.id DESC
        """, (user_id,))
        jobs_data = cur.fetchall()

    cur.close()

    return render_template(
        "profile.html",
        user=user,
        profile=profile_data,
        jobs=jobs_data,
        role=role
    )
@app.route("/job/<int:job_id>/applicants")
def job_applicants(job_id):
    if "user_id" not in session or session.get("role") != "company":
        return redirect(url_for("login"))

    cur = db.cursor(dictionary=True)

    cur.execute("""
        SELECT 
            u.id,
            u.name,
            u.email,
            up.phone,
            up.location,
            a.status,
            a.id AS application_id,  -- ⭐ IMPORTANT LINE
            up.experience_level
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

    cur = db.cursor(dictionary=True)

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
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = db.cursor(dictionary=True)

    # Existing personal info fetch
    cur.execute(
        "SELECT * FROM user_profiles WHERE user_id=%s",
        (session["user_id"],)
    )
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

        # 🔥 RESUME UPLOAD LOGIC (NEW)
        resume_file = request.files.get("resume")
        resume_filename = None

        if resume_file and resume_file.filename != "":
            filename = secure_filename(resume_file.filename)
            resume_path = os.path.join(RESUME_FOLDER, filename)
            resume_file.save(resume_path)
            resume_filename = filename

        if profile:
            # UPDATE
            if resume_filename:
                cur.execute("""
                    UPDATE user_profiles SET
                    phone=%s, gender=%s, date_of_birth=%s, location=%s,
                    experience_level=%s, current_job_title=%s,
                    expected_salary=%s, skills=%s,
                    linkedin=%s, portfolio=%s,
                    resume=%s
                    WHERE user_id=%s
                """, (
                    phone, gender, dob, location,
                    experience, job_title, salary,
                    skills, linkedin, portfolio,
                    resume_filename,
                    session["user_id"]
                ))
            else:
                cur.execute("""
                    UPDATE user_profiles SET
                    phone=%s, gender=%s, date_of_birth=%s, location=%s,
                    experience_level=%s, current_job_title=%s,
                    expected_salary=%s, skills=%s,
                    linkedin=%s, portfolio=%s
                    WHERE user_id=%s
                """, (
                    phone, gender, dob, location,
                    experience, job_title, salary,
                    skills, linkedin, portfolio,
                    session["user_id"]
                ))
        else:
            # INSERT
            cur.execute("""
                INSERT INTO user_profiles
                (user_id, phone, gender, date_of_birth, location,
                 experience_level, current_job_title, expected_salary,
                 skills, linkedin, portfolio, resume)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                session["user_id"], phone, gender, dob, location,
                experience, job_title, salary,
                skills, linkedin, portfolio,
                resume_filename
            ))

        db.commit()
        return redirect(url_for("profile"))

    return render_template("personal_info.html", profile=profile)
#-----------withdraw job-------------
@app.route("/withdraw/<int:job_id>")
def withdraw_job(job_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = db.cursor()
    cur.execute(
        "DELETE FROM job_applications WHERE user_id=%s AND job_id=%s",
        (session["user_id"], job_id)
    )
    db.commit()

    return redirect(request.referrer or "/")




#----------Update profile-----------
@app.route('/update-profile', methods=['GET', 'POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if password:  # password optional
            cursor.execute(
                "UPDATE users SET name=%s, email=%s, password=%s WHERE id=%s",
                (name, email, password, session['user_id'])
            )
        else:
            cursor.execute(
                "UPDATE users SET name=%s, email=%s WHERE id=%s",
                (name, email, session['user_id'])
            )

        db.commit()

        # update session
        session['name'] = name
        session['email'] = email

        return redirect(url_for('profile'))

    # GET request
    cursor.execute(
        "SELECT name, email FROM users WHERE id=%s",
        (session['user_id'],)
    )
    user = cursor.fetchone()

    return render_template(
        "update_profile.html",
        name=user['name'],
        email=user['email']
    )


#-----------deactivate ------------
@app.route('/deactivate-account')
def deactivate_account():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = db.cursor()
    cur.execute(
        "UPDATE users SET status='deactivated' WHERE id=%s",
        (session['user_id'],)
    )
    db.commit()
    cur.close()

    session.clear()
    return redirect(url_for('login'))



#-----------delete account----------
@app.route('/delete-account')
def delete_account():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    role = session.get('role')

    cur = db.cursor()

    # ✅ Agar company hai → uski jobs bhi delete karo
    if role == "company":
        cur.execute("DELETE FROM jobs WHERE company_id=%s", (user_id,))

    # ✅ Fir user delete karo
    cur.execute("DELETE FROM users WHERE id=%s", (user_id,))

    db.commit()
    cur.close()

    session.clear()
    return redirect(url_for('register'))



# ---------------- ALL JOBS + FILTER ----------------
@app.route("/jobs")
def jobs():
    keyword = request.args.get("keyword")
    category = request.args.get("category")
    job_type = request.args.get("type")
    location = request.args.get("location")  # ✅ ADDED

    all_categories = [
        "Development",
        "Design",
        "Marketing",
        "Customer Service",
        "Finance",
        "HR",
        "Sales",
        "IT Support"
    ]

    cur = db.cursor(dictionary=True)

    # 🔥 Top companies
    cur.execute("""
        SELECT company, COUNT(*) as job_count 
        FROM jobs 
        GROUP BY company 
        ORDER BY job_count DESC 
        LIMIT 4
    """)
    top_companies = cur.fetchall()

    # 🔍 Job filter query
    query = """
        SELECT j.*, IF(a.id IS NULL, 0, 1) AS applied
        FROM jobs j
        LEFT JOIN job_applications a
        ON j.id = a.job_id AND a.user_id = %s
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

    if location:   # ✅ LOCATION FILTER
        query += " AND j.location = %s"
        params.append(location)

    query += " ORDER BY j.id DESC"

    cur.execute(query, tuple(params))
    jobs_data = cur.fetchall()
    cur.close()

    return render_template(
        "job.html",
        jobs=jobs_data,
        categories=all_categories,
        top_companies=top_companies
    )




#--------job details ----------
@app.route("/job/<int:job_id>")
def job_detail(job_id):
    cur = db.cursor(dictionary=True)
    
    # 🔹 Job ki poori detail
    cur.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
    job = cur.fetchone()
    
    if not job:
        return "Job Not Found", 404

    # 🔹 Check user applied or not
    applied = False
    if 'user_id' in session:
        cur.execute(
            "SELECT id FROM job_applications WHERE user_id = %s AND job_id = %s",
            (session['user_id'], job_id)
        )
        if cur.fetchone():
            applied = True

    # 🔹 RELATED JOBS LOGIC
    # Same category ya same company ki jobs dikha rahe hain
    cur.execute("""
        SELECT * FROM jobs
        WHERE (category = %s OR company_id = %s)
        AND id != %s
        ORDER BY created_at DESC
        LIMIT 4
    """, (job['category'], job['company_id'], job_id))

    related_jobs = cur.fetchall()

    cur.close()

    return render_template(
        "job_detail.html",
        job=job,
        applied=applied,
        related_jobs=related_jobs
    )



# ---------------- APPLY / WITHDRAW ----------------
@app.route("/apply/<int:job_id>")
def apply_job(job_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") == "company":
        return redirect(url_for("job_detail", job_id=job_id))

    if not check_subscription():
        return redirect(url_for("pricing"))

    cur = db.cursor(dictionary=True)

    # 🔐 PROFILE COMPLETION CHECK (NEW)
    cur.execute("""
        SELECT phone, gender, date_of_birth, location, experience_level
        FROM user_profiles
        WHERE user_id=%s
    """, (session["user_id"],))
    profile = cur.fetchone()

    if not profile or any(value is None or value == "" for value in profile.values()):
        cur.close()
        return redirect(url_for("profile", incomplete=1))

    try:
        # 1️⃣ Insert application
        cur.execute(
            "INSERT INTO job_applications (user_id, job_id) VALUES (%s,%s)",
            (session["user_id"], job_id)
        )
        db.commit()

        # 2️⃣ Get job + company email
        cur.execute("""
            SELECT j.title, j.company, u.email AS company_email
            FROM jobs j
            JOIN users u ON j.company_id = u.id
            WHERE j.id = %s
        """, (job_id,))
        job = cur.fetchone()

        # 3️⃣ Send email to USER
        send_job_apply_email(
            session["email"],
            session["name"],
            job["title"],
            job["company"]
        )

        # 4️⃣ Send email to COMPANY
        send_company_application_email(
            job["company_email"],
            job["company"],
            session["name"],
            job["title"]
        )

    except Exception as e:
        print("Apply Error:", e)

    cur.close()
    return redirect(request.referrer or "/")

def send_job_apply_email(email, name, job_title, company):
    sender_email = "narotamdharaviya65@gmail.com"
    password = "wckt cxmm xvdu vulf"

    body = f"""
Hello {name},

Your job application has been submitted successfully!

Job Title: {job_title}
Company: {company}

Best of luck!
Job Portal Team
"""

    msg = MIMEText(body)
    msg["Subject"] = "Job Application Successful"
    msg["From"] = "Job Portal <narotamdharaviya65@gmail.com>"
    msg["To"] = email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, password)
        server.sendmail(sender_email, email, msg.as_string())   # ✅ safer


def send_company_application_email(company_email, company, candidate, job_title):
    sender_email = "narotamdharaviya65@gmail.com"
    password = "wckt cxmm xvdu vulf"

    body = f"""
Hello {company},

You have received a new job application 🎉

Candidate Name: {candidate}
Job Title     : {job_title}

Please login to your Job Portal dashboard to view full details.

Regards,
Job Portal Team
"""

    msg = MIMEText(body)
    msg["Subject"] = "New Job Application Received"
    msg["From"] = "Job Portal <narotamdharaviya65@gmail.com>"
    msg["To"] = company_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, password)
        server.sendmail(sender_email, company_email, msg.as_string())


@app.route("/application/<int:app_id>/accept")
def accept_application(app_id):
    if session.get("role") != "company":
        return redirect("/")

    cur = db.cursor(dictionary=True)

    # update status
    cur.execute("UPDATE job_applications SET status='accepted' WHERE id=%s", (app_id,))
    db.commit()

    # get user + job info
    cur.execute("""
        SELECT u.email, u.name, j.title, j.company
        FROM job_applications a
        JOIN users u ON a.user_id = u.id
        JOIN jobs j ON a.job_id = j.id
        WHERE a.id=%s
    """, (app_id,))
    data = cur.fetchone()

    # send email
    send_application_status_email(
        data["email"],
        data["name"],
        data["title"],
        data["company"],
        "accepted"
    )

    cur.close()
    return redirect(request.referrer or "/profile")


@app.route("/application/<int:app_id>/reject")
def reject_application(app_id):
    if session.get("role") != "company":
        return redirect("/")

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

    send_application_status_email(
        data["email"],
        data["name"],
        data["title"],
        data["company"],
        "rejected"
    )

    cur.close()
    return redirect(request.referrer or "/profile")

def send_application_status_email(to_email, user_name, job_title, company, status):
    subject = f"Application {status.capitalize()} - {job_title}"

    if status == "accepted":
        message = f"""
Hello {user_name},

Congratulations 🎉  
You have been SELECTED for the position:

Job: {job_title}  
Company: {company}

The company may contact you soon.

Best of luck!
"""
    else:
        message = f"""
Hello {user_name},

We regret to inform you that you were not selected for:

Job: {job_title}  
Company: {company}

Don't worry — keep applying and stay positive 💪
"""

    msg = MIMEText(message)
    msg["Subject"] = subject
    msg["From"] = "Job Portal <narotamdharaviya65@gmail.com>"
    msg["To"] = to_email

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login("narotamdharaviya65@gmail.com", "wckt cxmm xvdu vulf")
    server.send_message(msg)
    server.quit()
# =====================================================
# ================= ADMIN SECTION =====================
# =====================================================

# =====================================================
# ================= ADMIN SECTION =====================
# =====================================================

def admin_required():
    return 'admin_id' in session and session.get('admin_status') == 'approved'

def super_admin_required():
    return admin_required() and session.get('admin_role') == 'super_admin'

# 1. NEW: /admin URL માટે redirect route (404 Error સોલ્વ કરવા માટે)
@app.route("/admin")
def admin_index():
    if admin_required():
        return redirect("/admin/dashboard")
    return redirect("/admin/login")

# ---------------- ADMIN LOGIN ----------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        # Dictionary cursor નો ઉપયોગ કર્યો છે
        cur = db.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM admins WHERE email=%s AND password=%s",
            (email, password)
        )
        admin = cur.fetchone()
        cur.close()

        # Check: 1. Admin અસ્તિત્વમાં છે કે નહીં?
        if not admin:
            return render_template("admin/login.html", error="Invalid Email or Password")

        # Check: 2. Status 'approved' છે કે નહીં?
        if admin["status"] != "approved":
            return render_template("admin/login.html", error="Your account is not approved yet!")

        # Session સેટ કરો
        session["admin_id"] = admin["id"]
        session["admin_name"] = admin["name"]
        session["admin_role"] = admin["role"]
        session["admin_status"] = admin["status"]
        
        return redirect("/admin/dashboard")

    return render_template("admin/login.html")
# ---------------- ADMIN REVIEWS ----------------
@app.route('/admin/reviews')
def admin_reviews():
    if not admin_required():
        return redirect("/admin/login")

    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT reviews.id,
               reviews.rating,
               reviews.review,
               reviews.created_at,
               users.name
        FROM reviews
        JOIN users ON reviews.user_id = users.id
        ORDER BY reviews.id DESC
    """)
    reviews = cur.fetchall()
    cur.close()

    return render_template("admin/review.html", reviews=reviews)


@app.route('/admin/delete-review/<int:id>', methods=['POST'])
def admin_delete_review(id):
    # અહીં પણ admin_required() જ વાપરો
    if not admin_required():
        return redirect("/admin/login")

    cur = db.cursor()
    try:
        cur.execute("DELETE FROM reviews WHERE id=%s", (id,))
        db.commit()
    except Exception as e:
        db.rollback()
    finally:
        cur.close()

    return redirect(url_for('admin_reviews'))
# ---------------- ADMIN DASHBOARD ----------------
@app.route("/admin/dashboard")
def admin_dashboard():
    if not admin_required():
        return redirect("/admin/login")

    cur = db.cursor()

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

    return render_template(
        "admin/dashboard.html",
        total_jobs=total_jobs,
        total_feedback=total_feedback,
        total_blogs=total_blogs,
        total_users=total_users,
        total_applications=total_applications
    )
@app.route("/admin/users")
def admin_users():
    if not admin_required():
        return redirect("/admin/login")

    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()
    cur.close()

    return render_template("admin/users.html", users=users)


UPLOAD_FOLDER = "static/uploads/blogs"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# --- Admin: Manage Blogs List ---
@app.route("/admin/blogs")
def admin_blogs():
    if not admin_required(): return redirect("/admin/login")
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM blogs ORDER BY created_at DESC")
    blogs = cur.fetchall()
    cur.close()
    return render_template("admin/blogs.html", blogs=blogs)



# --- Admin: Add New Blog ---
@app.route("/admin/blog/add", methods=["GET", "POST"])
def admin_add_blog():
    if not admin_required():
        return redirect("/admin/login")

    if request.method == "POST":
        image_file = request.files.get("image")

        image_path = None
        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            image_path = f"uploads/blogs/{filename}"
            image_file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        cur = db.cursor()
        cur.execute("""
            INSERT INTO blogs (title, content, author, category, image_url)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            request.form["title"],
            request.form["content"],
            request.form["author"],
            request.form["category"],
            image_path
        ))
        db.commit()
        cur.close()

        return redirect("/admin/blogs")

    return render_template("admin/blog_form.html", title="Add New Blog")



# --- Admin: Delete Blog ---
@app.route("/admin/blog/delete/<int:id>")
def admin_delete_blog(id):
    if not admin_required(): return redirect("/admin/login")
    cur = db.cursor()
    cur.execute("DELETE FROM blogs WHERE id = %s", (id,))
    db.commit()
    cur.close()
    return redirect("/admin/blogs")


# ---------------- ADMIN JOB MANAGEMENT ----------------
@app.route("/admin/jobs")
def admin_jobs():
    if not admin_required():
        return redirect("/admin/login")

    cursor.execute("SELECT * FROM jobs ORDER BY id DESC")
    jobs = cursor.fetchall()
    return render_template("admin/jobs.html", jobs=jobs)


#----------job add--------------------
@app.route("/job/add", methods=["GET","POST"])
def admin_add_job():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    # Subscription status check
    if not check_subscription():
        return redirect(url_for('pricing')) 

    if request.method == "POST":
        try:
            # Session se details uthana
            c_id = session.get("user_id")
            c_name = session.get("name") # Agar session mein 'name' nahi hai toh 'company_name' check karein

            # Form se data uthana (HTML 'name' attributes se match hona chahiye)
            title = request.form.get("title")
            company = request.form.get("company")
            location = request.form.get("location")
            salary = request.form.get("salary")
            category = request.form.get("category")
            job_type = request.form.get("job_type")
            description = request.form.get("description")

            cur = db.cursor() # Ya aapka jo bhi cursor variable ho

            # 🔥 Sabse Important: Sequence ekdum sahi hona chahiye
            sql = """
                INSERT INTO jobs (title, company, company_id, location, salary, category, job_type, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (title, company, c_id, location, salary, category, job_type, description)

            cur.execute(sql, values)
            db.commit()
            cur.close()
            
            # Success ke baad profile page par redirect
            return redirect(url_for("profile", success="Job added successfully!"))

        except Exception as e:
            print(f"Database Error: {e}")
            return f"Error: {e}" # Ye error aapko batayega ki kaunsa column missing hai

    return render_template("job_form.html", title="Add Job", job=None)


#-------------job edit ----------------
@app.route("/admin/job/edit/<int:id>", methods=["GET","POST"])
def admin_edit_job(id):
    # Admin check ya session check yahan zaroori hai
    if "user_id" not in session:
        return redirect("/login")
        
    if not check_subscription():
        return redirect(url_for('pricing'))

    if request.method == "POST":
        cursor.execute("""
            UPDATE jobs SET title=%s, company=%s, location=%s,
            salary=%s, category=%s, job_type=%s, description=%s WHERE id=%s
        """, (
            request.form["title"],
            request.form["company"],
            request.form["location"],
            request.form["salary"],
            request.form["category"],
            request.form["job_type"],
            request.form["description"],
            id
        ))
        db.commit()
        return redirect("/profile") # Profile par wapas bhej dena sahi rahega

    cursor.execute("SELECT * FROM jobs WHERE id=%s", (id,))
    job = cursor.fetchone()
    # Check karein ki path sahi ho (admin/job_form.html ya sirf job_form.html)
    return render_template("job_form.html", title="Edit Job", job=job)

@app.route("/admin/job/delete/<int:id>")
def admin_delete_job(id):
    
    cursor.execute("DELETE FROM jobs WHERE id=%s", (id,))
    db.commit()
    return redirect("/profile")



# ---------------- SUPER ADMIN ----------------
@app.route("/admin/manage-admins")
def manage_admins():
    if not super_admin_required():
        return redirect("/admin/login")

    cursor.execute("SELECT * FROM admins")
    admins = cursor.fetchall()
    return render_template("admin/admins.html", admins=admins)

@app.route("/admin/approve-admin/<int:id>")
def approve_admin(id):
    if not super_admin_required():
        return redirect("/admin/login")

    cursor.execute("UPDATE admins SET status='approved' WHERE id=%s", (id,))
    db.commit()
    return redirect("/admin/manage-admins")


@app.route("/admin/feedback")
def admin_feedback():
    if not admin_required():
        return redirect("/admin/login")

    cursor.execute("SELECT * FROM feedback ORDER BY created_at DESC")
    feedbacks = cursor.fetchall()

    return render_template("admin/feedback.html", feedbacks=feedbacks)

@app.route("/admin/feedback/delete/<int:id>")
def delete_feedback(id):
    if not admin_required():
        return redirect("/admin/login")

    cursor.execute("DELETE FROM feedback WHERE id=%s", (id,))
    db.commit()

    return redirect("/admin/feedback")

@app.route("/about")
def about():
    return render_template("about.html")



@app.route("/admin/applications")
def admin_applications():
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    cur = db.cursor(dictionary=True)

    query = """
        SELECT ja.id AS application_id,
               u.id AS user_id,
               u.email,
               j.id AS job_id,
               j.title,
               ja.applied_at,
               ja.status
        FROM job_applications ja
        JOIN users u ON ja.user_id = u.id
        JOIN jobs j ON ja.job_id = j.id
        ORDER BY ja.applied_at DESC
    """
    cur.execute(query)
    applications = cur.fetchall()
    cur.close()

    return render_template("admin/admin_applications.html", applications=applications)

# ---------------- ADMIN DELETE USER ----------------
# ---------------- ADMIN DELETE USER ----------------
@app.route("/admin/user/delete/<int:id>", methods=["POST"])
def admin_delete_user(id):
    if not admin_required():
        return redirect("/admin/login")

    cur = db.cursor()
    try:
        # 1. Delete company jobs (if user is a company)
        cur.execute("DELETE FROM jobs WHERE company_id=%s", (id,))
        
        # 2. Delete applications submitted by user
        cur.execute("DELETE FROM job_applications WHERE user_id=%s", (id,))
        
        # 3. Delete profile details and main account
        cur.execute("DELETE FROM user_profiles WHERE user_id=%s", (id,))
        cur.execute("DELETE FROM users WHERE id=%s", (id,))
        
        db.commit()
    except Exception as e:
        db.rollback()
        # Optionally log the exception here
    finally:
        cur.close()

    return redirect("/admin/user")
    #--------------contact page------------------
import os
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, request

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        # 1. HTML ફોર્મમાંથી ડેટા મેળવવો
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        name = f"{first_name} {last_name}".strip()
        email = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        # ===============================
        # 1️⃣ SAVE TO DATABASE
        # ===============================
        try:
            cur = db.cursor()
            cur.execute(
                "INSERT INTO feedback (name, email, subject, message) VALUES (%s,%s,%s,%s)",
                (name, email, subject, message)
            )
            db.commit()
            cur.close()
            print("DATABASE SAVED ✅")
        except Exception as db_err:
            print("DATABASE ERROR ❌", db_err)

        # ===============================
        # 2️⃣ EMAIL CONFIG
        # ===============================
        SENDER_EMAIL = "narotamdharaviya65@gmail.com"
        # ⚠️ તમારો નવો 16 અક્ષરનો App Password અહીં વચ્ચે જગ્યા રાખ્યા વિના મૂકો
        APP_PASSWORD = "voeb nvlt zfjh ucmn".replace(" ", "") 
        ADMIN_EMAIL = "narotamdharaviya65@gmail.com"

        # ===============================
        # 3️⃣ SEND EMAIL (SMTP via TLS 587)
        # ===============================
        try:
            # Gmail Server connection (Port 587 TLS is more reliable)
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(SENDER_EMAIL, APP_PASSWORD)

            # --- A. Email to Admin ---
            admin_body = f"""New Contact Request 📩

Name   : {name}
Email  : {email}
Subject: {subject}

Message:
{message}
"""
            admin_msg = MIMEText(admin_body)
            admin_msg["Subject"] = f"New Contact: {subject}"
            admin_msg["From"] = SENDER_EMAIL
            admin_msg["To"] = ADMIN_EMAIL
            admin_msg["Reply-To"] = email

            server.sendmail(SENDER_EMAIL, ADMIN_EMAIL, admin_msg.as_string())

            # --- B. Auto-Reply to User ---
            user_body = f"""Hi {name},

Thank you for contacting Job Portal! 👋

We have received your message regarding:
"{subject}"

Our support team is reviewing your request and will get back to you as soon as possible.

⏳ Expected response time: 24 hours

Best regards,
Job Portal Support Team
"""
            user_msg = MIMEText(user_body)
            user_msg["Subject"] = "We received your request – Job Portal"
            user_msg["From"] = SENDER_EMAIL
            user_msg["To"] = email

            server.sendmail(SENDER_EMAIL, email, user_msg.as_string())

            server.quit()
            print("ADMIN + USER EMAIL SENT SUCCESSFULLY ✅")

        except smtplib.SMTPAuthenticationError:
            print("❌ EMAIL ERROR: App Password અથવા Email ખોટો છે!")
        except Exception as e:
            print("❌ EMAIL ERROR DETAILS:", str(e))

        return render_template("contact.html", success=True)

    return render_template("contact.html")

#--------privecy-policy---------
@app.route("/privacy-policy")
def privacy_policy():
    return render_template("privacy_policy.html")


#--------terms--------------
@app.route("/terms")
def terms_conditions():
    return render_template("terms_conditions.html")


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
