import os, sqlite3, datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, abort
import markdown

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production-9f3a2b")
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "blog.db"))
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")  # 上线前请在环境变量中设置 ADMIN_PASS


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            summary TEXT DEFAULT '',
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            views INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS murmurs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            caption TEXT DEFAULT '',
            album TEXT DEFAULT '风景',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    try:
        db.execute("ALTER TABLE photos ADD COLUMN album TEXT DEFAULT '风景'")
    except sqlite3.OperationalError:
        pass
    db.commit()
    db.close()


NOTE_COLORS = ["#fdf3b4", "#ffd9e0", "#d6f0dd", "#dbe7ff", "#ffe4c4"]


SOCIAL_LINKS = [
    {"name": "GitHub", "icon": "🐙", "url": "https://github.com/"},
    {"name": "邮箱", "icon": "📧", "url": "mailto:me@example.com"},
    {"name": "Bilibili", "icon": "📺", "url": "https://www.bilibili.com/"},
    {"name": "RSS", "icon": "📰", "url": "#"},
]

DEFAULT_SETTINGS = {
    "site_name": "甜馨",
    "avatar_text": "甜馨",
    "avatar_url": "",
    "author_name": "甜馨",
    "slogan": "不妨大胆一点，很多事情都没有答案",
    "about_text": "一个喜欢折腾技术的人。这里记录我的学习笔记、踩坑经历和一些小想法。写代码，也写生活。",
    "github_url": "https://github.com/",
    "email": "me@example.com",
    "bilibili_url": "https://www.bilibili.com/",
}


def get_settings():
    merged = dict(DEFAULT_SETTINGS)
    try:
        for row in get_db().execute("SELECT key, value FROM settings"):
            if row["value"]:
                merged[row["key"]] = row["value"]
    except sqlite3.OperationalError:
        pass
    s = merged
    social = []
    if s["github_url"]:
        social.append({"name": "GitHub", "icon": "🐙", "url": s["github_url"]})
    if s["email"]:
        social.append({"name": "邮箱", "icon": "📧", "url": f"mailto:{s['email']}"})
    if s["bilibili_url"]:
        social.append({"name": "Bilibili", "icon": "📺", "url": s["bilibili_url"]})
    return {**s, "social": social}


@app.context_processor
def inject_sidebar():
    s = get_settings()
    db = get_db()
    posts = db.execute("SELECT tags FROM posts").fetchall()
    tag_count, cat_count = {}, {}
    for p in posts:
        tags = [t.strip() for t in p["tags"].split(",") if t.strip()]
        for t in tags:
            tag_count[t] = tag_count.get(t, 0) + 1
        cat = tags[0] if tags else "未分类"
        cat_count[cat] = cat_count.get(cat, 0) + 1
    return {
        "side_tags": sorted(tag_count, key=lambda k: -tag_count[k])[:12],
        "side_cats": sorted(cat_count.items(), key=lambda kv: -kv[1]),
        "site": s,
    }


@app.route("/tag/<name>")
def tag_view(name):
    db = get_db()
    like = f"%{name}%"
    posts = db.execute(
        "SELECT * FROM posts WHERE (',' || tags || ',') LIKE ? ORDER BY created_at DESC",
        (f"%,{name},%",),
    ).fetchall()
    # 兜底：精确匹配不到时用模糊搜索
    if not posts:
        posts = db.execute(
            "SELECT * FROM posts WHERE tags LIKE ? ORDER BY created_at DESC", (like,)
        ).fetchall()
    return render_template("tag.html", tag_name=name, posts=posts)


@app.route("/categories")
def categories():
    db = get_db()
    posts = db.execute("SELECT * FROM posts ORDER BY created_at DESC").fetchall()
    cats = {}
    for p in posts:
        tags = [t.strip() for t in p["tags"].split(",") if t.strip()]
        key = tags[0] if tags else "未分类"
        cats.setdefault(key, []).append(p)
    cats = dict(sorted(cats.items(), key=lambda kv: -len(kv[1])))
    return render_template("categories.html", cats=cats)


@app.route("/wall", methods=["GET", "POST"])
def wall():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:30] or "匿名"
        content = request.form.get("content", "").strip()[:200]
        if content:
            db.execute(
                "INSERT INTO messages(name, content, created_at) VALUES(?,?,?)",
                (name, content, datetime.datetime.now().isoformat(timespec="seconds")),
            )
            db.commit()
        return redirect(url_for("wall"))
    msgs = db.execute("SELECT * FROM messages ORDER BY id DESC").fetchall()
    notes = [
        {"m": m, "color": NOTE_COLORS[i % len(NOTE_COLORS)], "rot": ((i * 37) % 9) - 4}
        for i, m in enumerate(msgs)
    ]
    return render_template("wall.html", notes=notes)


MURMUR_COLORS = ["#fff7e0", "#e8f4ea", "#eef3ff", "#fdeef0", "#f3ecff"]


@app.route("/murmurs", methods=["GET", "POST"])
def murmurs():
    db = get_db()
    if request.method == "POST":
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        content = request.form.get("content", "").strip()[:500]
        if content:
            db.execute(
                "INSERT INTO murmurs(content, created_at) VALUES(?,?)",
                (content, datetime.datetime.now().isoformat(timespec="seconds")),
            )
            db.commit()
        return redirect(url_for("murmurs"))
    rows = db.execute("SELECT * FROM murmurs ORDER BY id DESC").fetchall()
    items = [
        {"m": r, "color": MURMUR_COLORS[i % len(MURMUR_COLORS)]}
        for i, r in enumerate(rows)
    ]
    return render_template("murmurs.html", items=items)


@app.route("/gallery", methods=["GET", "POST"])
def gallery():
    db = get_db()
    if request.method == "POST":
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        f = request.files.get("photo")
        caption = request.form.get("caption", "").strip()[:100]
        album = request.form.get("album", "").strip()[:30] or "风景"
        if f and f.filename:
            import re
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                flash("仅支持 jpg/png/gif/webp 图片")
                return redirect(url_for("gallery"))
            os.makedirs(os.path.join(app.static_folder, "uploads"), exist_ok=True)
            fname = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
            f.save(os.path.join(app.static_folder, "uploads", fname))
            db.execute(
                "INSERT INTO photos(path, caption, album, created_at) VALUES(?,?,?,?)",
                (f"uploads/{fname}", caption, album, datetime.datetime.now().isoformat(timespec="seconds")),
            )
            db.commit()
        return redirect(url_for("gallery"))
    album = request.args.get("album", "全部")
    if album and album != "全部":
        photos = db.execute("SELECT * FROM photos WHERE album=? ORDER BY id DESC", (album,)).fetchall()
    else:
        photos = db.execute("SELECT * FROM photos ORDER BY id DESC").fetchall()
    albums = [r["album"] for r in db.execute(
        "SELECT DISTINCT album FROM photos ORDER BY album").fetchall()]
    return render_template("gallery.html", photos=photos, albums=albums, album=album)
def all_tags():
    db = get_db()
    posts = db.execute("SELECT tags FROM posts").fetchall()
    counts = {}
    for p in posts:
        for t in (x.strip() for x in p["tags"].split(",")):
            if t:
                counts[t] = counts.get(t, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])


@app.route("/admin/tags", methods=["GET", "POST"])
def admin_tags():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        name = request.form.get("name", "").strip()
        if name:
            if action == "rename":
                new = request.form.get("new_name", "").strip()
                if new and new != name:
                    for p in db.execute("SELECT id, tags FROM posts").fetchall():
                        tags = [t.strip() for t in p["tags"].split(",") if t.strip()]
                        if name in tags:
                            tags = [new if t == name else t for t in tags]
                            # 去重
                            seen, dedup = set(), []
                            for t in tags:
                                if t not in seen:
                                    seen.add(t)
                                    dedup.append(t)
                            db.execute("UPDATE posts SET tags=? WHERE id=?", (",".join(dedup), p["id"]))
                    flash(f"标签「{name}」已重命名为「{new}」")
            elif action == "delete":
                for p in db.execute("SELECT id, tags FROM posts").fetchall():
                    tags = [t.strip() for t in p["tags"].split(",") if t.strip() and t.strip() != name]
                    db.execute("UPDATE posts SET tags=? WHERE id=?", (",".join(tags), p["id"]))
                flash(f"标签「{name}」已从所有文章中移除")
        db.commit()
        return redirect(url_for("admin_tags"))
    return render_template("tags.html", tags=all_tags())


@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    db = get_db()
    if request.method == "POST":
        for key in DEFAULT_SETTINGS:
            if key == "avatar_url":
                continue
            val = request.form.get(key, "").strip()
            db.execute(
                "INSERT INTO settings(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, val),
            )
        # 头像图片上传
        f = request.files.get("avatar_file")
        if f and f.filename:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                os.makedirs(os.path.join(app.static_folder, "uploads"), exist_ok=True)
                fname = f"avatar{ext}"
                f.save(os.path.join(app.static_folder, "uploads", fname))
                db.execute(
                    "INSERT INTO settings(key, value) VALUES('avatar_url',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (f"uploads/{fname}",),
                )
        if request.form.get("remove_avatar"):
            db.execute("INSERT INTO settings(key, value) VALUES('avatar_url','') ON CONFLICT(key) DO UPDATE SET value=''")
        db.commit()
        flash("站点设置已保存")
        return redirect(url_for("admin_settings"))
    return render_template("settings.html", s=get_settings())


@app.route("/about")
def about():
    db = get_db()
    n_posts = db.execute("SELECT COUNT(*) c FROM posts").fetchone()["c"]
    n_msgs = db.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
    n_views = db.execute("SELECT COALESCE(SUM(views),0) v FROM posts").fetchone()["v"]
    return render_template("about.html", n_posts=n_posts, n_msgs=n_msgs, n_views=n_views)


@app.template_filter("readtime")
def readtime(text):
    minutes = max(1, round(len(text) / 400))
    return f"大约 {minutes} 分钟"


def slugify(s):
    import re
    s = s.strip().lower()
    s = re.sub(r"[\s]+", "-", s)
    s = re.sub(r"[^\w\-]", "", s, flags=re.UNICODE)
    return s or "post"


@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    db = get_db()
    if q:
        like = f"%{q}%"
        posts = db.execute(
            "SELECT * FROM posts WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? ORDER BY created_at DESC",
            (like, like, like),
        ).fetchall()
    else:
        posts = db.execute("SELECT * FROM posts ORDER BY created_at DESC").fetchall()
    # 所有标签及数量
    tag_count = {}
    for p in posts:
        for t in p["tags"].split(","):
            t = t.strip()
            if t:
                tag_count[t] = tag_count.get(t, 0) + 1
    tags = sorted(tag_count, key=lambda k: -tag_count[k])
    return render_template("index.html", posts=posts, q=q, tags=tags)


@app.route("/post/<slug>")
def post_detail(slug):
    db = get_db()
    p = db.execute("SELECT * FROM posts WHERE slug=?", (slug,)).fetchone()
    if not p:
        abort(404)
    db.execute("UPDATE posts SET views=views+1 WHERE id=?", (p["id"],))
    db.commit()
    comments = db.execute(
        "SELECT * FROM comments WHERE post_id=? ORDER BY created_at DESC", (p["id"],)
    ).fetchall()
    return render_template("post.html", post=p, body=markdown.markdown(p["content"], extensions=["fenced_code", "tables"]), comments=comments)


@app.route("/post/<slug>/comment", methods=["POST"])
def add_comment(slug):
    name = request.form.get("name", "").strip()[:50]
    content = request.form.get("content", "").strip()[:2000]
    if name and content:
        db = get_db()
        p = db.execute("SELECT id FROM posts WHERE slug=?", (slug,)).fetchone()
        if p:
            db.execute(
                "INSERT INTO comments(post_id, name, content, created_at) VALUES(?,?,?,?)",
                (p["id"], name, content, datetime.datetime.now().isoformat(timespec="seconds")),
            )
            db.commit()
    return redirect(url_for("post_detail", slug=slug))


# ---------- 管理后台 ----------
def login_required(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return fn(*a, **kw)

    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USER and request.form.get("password") == ADMIN_PASS:
            session["logged_in"] = True
            return redirect(url_for("admin"))
        flash("用户名或密码错误")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("index"))


@app.route("/admin")
@login_required
def admin():
    posts = get_db().execute("SELECT * FROM posts ORDER BY created_at DESC").fetchall()
    return render_template("admin.html", posts=posts)


@app.route("/admin/write", methods=["GET", "POST"])
@login_required
def write():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            flash("标题和内容不能为空")
            return render_template("edit.html", post=None)
        slug = slugify(title)
        base, i = slug, 2
        db = get_db()
        while db.execute("SELECT 1 FROM posts WHERE slug=?", (slug,)).fetchone():
            slug = f"{base}-{i}"
            i += 1
        summary = content.lstrip("# \n")[:120].split("\n")[0]
        db.execute(
            "INSERT INTO posts(title, slug, summary, content, tags, created_at) VALUES(?,?,?,?,?,?)",
            (title, slug, summary, content, request.form.get("tags", "").strip(),
             datetime.datetime.now().isoformat(timespec="seconds")),
        )
        db.commit()
        return redirect(url_for("admin"))
    return render_template("edit.html", post=None)


@app.route("/admin/edit/<int:post_id>", methods=["GET", "POST"])
@login_required
def edit(post_id):
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if title and content:
            db.execute(
                "UPDATE posts SET title=?, content=?, tags=? WHERE id=?",
                (title, content, request.form.get("tags", "").strip(), post_id),
            )
            db.commit()
        return redirect(url_for("admin"))
    p = db.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    return render_template("edit.html", post=p)


@app.route("/admin/delete/<int:post_id>", methods=["POST"])
@login_required
def delete(post_id):
    db = get_db()
    db.execute("DELETE FROM posts WHERE id=?", (post_id,))
    db.commit()
    return redirect(url_for("admin"))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
