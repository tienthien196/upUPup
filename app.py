# app.py
from flask import Flask, request, render_template, redirect, url_for, session, flash
import sqlite3
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Đổi thành chuỗi bí mật mạnh trong production
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Database setup ---
def get_db():
    conn = sqlite3.connect('social.db', detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        content TEXT,
        image_path TEXT,
        video_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS likes (
        user_id INTEGER,
        post_id INTEGER,
        PRIMARY KEY(user_id, post_id),
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(post_id) REFERENCES posts(id)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY,
        post_id INTEGER,
        user_id INTEGER,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(post_id) REFERENCES posts(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS follows (
        follower_id INTEGER,
        followed_id INTEGER,
        PRIMARY KEY(follower_id, followed_id),
        FOREIGN KEY(follower_id) REFERENCES users(id),
        FOREIGN KEY(followed_id) REFERENCES users(id)
    )''')
    conn.commit()

with app.app_context():
    init_db()

# --- Helper functions ---
def current_user():
    if 'user_id' in session:
        db = get_db()
        return db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    return None

@app.context_processor
def inject_user():
    return dict(current_user=current_user())

# --- Routes ---
@app.route('/')
def home():
    db = get_db()
    if current_user():
        user_id = current_user()['id']

        # --- 1. Bảng tin chính: bài từ người bạn theo dõi + bài của bạn ---
        feed_posts = db.execute('''
            SELECT p.*, u.username
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE p.user_id = :user_id 
               OR p.user_id IN (
                   SELECT followed_id FROM follows WHERE follower_id = :user_id
               )
            ORDER BY p.created_at DESC
            LIMIT 20
        ''', {'user_id': user_id}).fetchall()

        # --- 2. Gợi ý khám phá: bài phổ biến từ người bạn CHƯA theo dõi ---
        suggested_posts = db.execute('''
            SELECT p.*, u.username,
                   (SELECT COUNT(*) FROM likes WHERE post_id = p.id) AS like_count
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE p.user_id != :user_id
              AND p.user_id NOT IN (
                  SELECT followed_id FROM follows WHERE follower_id = :user_id
              )
            ORDER BY like_count DESC, p.created_at DESC
            LIMIT 5
        ''', {'user_id': user_id}).fetchall()

        # Chuẩn bị dữ liệu like cho cả hai danh sách
        def enrich_posts(posts_list):
            enriched = []
            for post in posts_list:
                post = dict(post)
                like_count = db.execute('SELECT COUNT(*) FROM likes WHERE post_id = ?', (post['id'],)).fetchone()[0]
                liked = db.execute('SELECT 1 FROM likes WHERE user_id = ? AND post_id = ?', 
                                  (user_id, post['id'])).fetchone() is not None
                post['like_count'] = like_count
                post['liked'] = liked
                enriched.append(post)
            return enriched

        return render_template('home.html', 
                             feed_posts=enrich_posts(feed_posts),
                             suggested_posts=enrich_posts(suggested_posts))
    else:
        # Khách vãng lai: hiển thị bài phổ biến nhất
        popular_posts = db.execute('''
            SELECT p.*, u.username,
                   (SELECT COUNT(*) FROM likes WHERE post_id = p.id) AS like_count
            FROM posts p
            JOIN users u ON p.user_id = u.id
            ORDER BY like_count DESC, p.created_at DESC
            LIMIT 20
        ''').fetchall()
        return render_template('home.html', popular_posts=popular_posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        if db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            flash('Username already exists!')
            return redirect(url_for('register'))
        hashed = generate_password_hash(password)
        db.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed))
        db.commit()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))

# ✅ SỬA LỖI: Thêm endpoint='create_post'
@app.route('/post', methods=['POST'], endpoint='create_post')
def create_post():
    if not current_user():
        return redirect(url_for('login'))
    content = request.form.get('content', '').strip()
    image_path = None
    video_path = None

    if 'image' in request.files:
        img = request.files['image']
        if img.filename:
            filename = secure_filename(img.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            img.save(image_path)

    if 'video' in request.files:
        vid = request.files['video']
        if vid.filename:
            filename = secure_filename(vid.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            vid.save(video_path)

    db = get_db()
    db.execute('INSERT INTO posts (user_id, content, image_path, video_path) VALUES (?, ?, ?, ?)',
               (current_user()['id'], content, image_path, video_path))
    db.commit()
    return redirect(url_for('home'))

@app.route('/like/<int:post_id>')
def like(post_id):
    if not current_user():
        return redirect(url_for('login'))
    db = get_db()
    db.execute('INSERT OR IGNORE INTO likes (user_id, post_id) VALUES (?, ?)',
               (current_user()['id'], post_id))
    db.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/unlike/<int:post_id>')
def unlike(post_id):
    if not current_user():
        return redirect(url_for('login'))
    db = get_db()
    db.execute('DELETE FROM likes WHERE user_id = ? AND post_id = ?', (current_user()['id'], post_id))
    db.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/profile/<username>')
def profile(username):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    if not user:
        flash('User not found')
        return redirect(url_for('home'))
    
    posts = db.execute('SELECT * FROM posts WHERE user_id = ? ORDER BY created_at DESC', (user['id'],)).fetchall()
    
    enriched_posts = []
    for post in posts:
        post = dict(post)
        like_count = db.execute('SELECT COUNT(*) FROM likes WHERE post_id = ?', (post['id'],)).fetchone()[0]
        liked = False
        if current_user():
            liked = db.execute('SELECT 1 FROM likes WHERE user_id = ? AND post_id = ?', 
                              (current_user()['id'], post['id'])).fetchone() is not None
        post['like_count'] = like_count
        post['liked'] = liked
        enriched_posts.append(post)

    is_following = False
    if current_user():
        is_following = db.execute('SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?',
                                  (current_user()['id'], user['id'])).fetchone() is not None

    followers_count = db.execute('SELECT COUNT(*) FROM follows WHERE followed_id = ?', (user['id'],)).fetchone()[0]
    following_count = db.execute('SELECT COUNT(*) FROM follows WHERE follower_id = ?', (user['id'],)).fetchone()[0]

    return render_template('profile.html', user=user, posts=enriched_posts, is_following=is_following,
                           followers_count=followers_count, following_count=following_count)
import bleach
from markdown import markdown

@app.template_filter('markdown')
def markdown_filter(text):
    # Chuyển Markdown → HTML
    html = markdown(text, extensions=['fenced_code', 'nl2br'])
    # Chỉ cho phép một số thẻ HTML an toàn
    allowed_tags = ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'blockquote', 'code', 'pre']
    allowed_attrs = {}
    clean_html = bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs, strip=True)
    return clean_html


@app.route('/follow/<int:user_id>')
def follow(user_id):
    if not current_user():
        return redirect(url_for('login'))
    if current_user()['id'] == user_id:
        flash("You can't follow yourself!")
        return redirect(request.referrer or url_for('home'))
    db = get_db()
    db.execute('INSERT OR IGNORE INTO follows (follower_id, followed_id) VALUES (?, ?)',
               (current_user()['id'], user_id))
    db.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/unfollow/<int:user_id>')
def unfollow(user_id):
    if not current_user():
        return redirect(url_for('login'))
    db = get_db()
    db.execute('DELETE FROM follows WHERE follower_id = ? AND followed_id = ?', (current_user()['id'], user_id))
    db.commit()
    return redirect(request.referrer or url_for('home'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')