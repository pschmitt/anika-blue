import hashlib
import os
import random
import secrets
import sqlite3
import time
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, session
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
BIND_HOST = os.environ.get("BIND_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("BIND_PORT", 5000))
DATABASE = os.environ.get("DATABASE", "anika_blue.db")
DEBUG = os.environ.get("DEBUG") is not None
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))

LIVERELOAD_POLL_INTERVAL = float(os.environ.get("LIVERELOAD_POLL_INTERVAL", 1.5))
_LIVERELOAD_CACHE = {"token": None, "timestamp": 0.0}
WATCH_TARGETS = [
    BASE_DIR / "templates",
    BASE_DIR / "static",
    BASE_DIR / "app.py",
    BASE_DIR / "__main__.py",
]

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
app.secret_key = SECRET_KEY

if DEBUG:
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True


def compute_live_reload_token() -> str:
    digest = hashlib.sha1()

    for target in WATCH_TARGETS:
        if not target.exists():
            continue

        if target.is_file():
            stat = target.stat()
            digest.update(str(target.relative_to(BASE_DIR.parent)).encode("utf-8"))
            digest.update(str(stat.st_mtime_ns).encode("utf-8"))
            continue

        for path in sorted(target.rglob("*")):
            if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue

            if not path.is_file():
                continue
            stat = path.stat()
            digest.update(str(path.relative_to(BASE_DIR.parent)).encode("utf-8"))
            digest.update(str(stat.st_mtime_ns).encode("utf-8"))

    return digest.hexdigest()


def get_live_reload_token() -> str:
    now = time.monotonic()
    token = _LIVERELOAD_CACHE.get("token")
    timestamp = _LIVERELOAD_CACHE.get("timestamp", 0.0)

    if token is None or (now - timestamp) >= LIVERELOAD_POLL_INTERVAL:
        token = compute_live_reload_token()
        _LIVERELOAD_CACHE.update({"token": token, "timestamp": now})

    return token


def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # Table for user choices
    c.execute(
        """CREATE TABLE IF NOT EXISTS choices
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT NOT NULL,
                  hex_color TEXT NOT NULL,
                  is_anika_blue INTEGER NOT NULL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"""
    )

    # Table for shades already shown to users
    c.execute(
        """CREATE TABLE IF NOT EXISTS shown_shades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT NOT NULL,
                  hex_color TEXT NOT NULL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"""
    )

    # Table for user base colors (for cross-session/device identification)
    c.execute(
        """CREATE TABLE IF NOT EXISTS user_base_colors
                 (user_id TEXT PRIMARY KEY,
                  base_color TEXT NOT NULL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"""
    )

    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_user_id(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            session["user_id"] = secrets.token_hex(16)
        return f(*args, **kwargs)

    return decorated_function


def generate_blue_shade():
    """Generate a random shade of blue"""
    # Blue is typically R=0-100, G=0-200, B=150-255 for good blues
    r = random.randint(0, 100)
    g = random.randint(0, 200)
    b = random.randint(150, 255)
    return f"#{r:02x}{g:02x}{b:02x}"


def get_user_average(user_id):
    """Calculate the average color for a user's Anika Blue choices"""
    conn = get_db()
    c = conn.cursor()

    c.execute(
        """SELECT hex_color FROM choices
                 WHERE user_id = ? AND is_anika_blue = 1""",
        (user_id,),
    )

    colors = [row["hex_color"] for row in c.fetchall()]
    conn.close()

    if not colors:
        return None

    # Calculate average RGB values
    r_sum, g_sum, b_sum = 0, 0, 0
    for color in colors:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        r_sum += r
        g_sum += g
        b_sum += b

    count = len(colors)
    avg_r = int(r_sum / count)
    avg_g = int(g_sum / count)
    avg_b = int(b_sum / count)

    return f"#{avg_r:02x}{avg_g:02x}{avg_b:02x}", count


def get_global_average():
    """Calculate the global average of all Anika Blue choices"""
    conn = get_db()
    c = conn.cursor()

    c.execute(
        """SELECT hex_color FROM choices
                 WHERE is_anika_blue = 1"""
    )

    colors = [row["hex_color"] for row in c.fetchall()]
    conn.close()

    if not colors:
        return None

    # Calculate average RGB values
    r_sum, g_sum, b_sum = 0, 0, 0
    for color in colors:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        r_sum += r
        g_sum += g
        b_sum += b

    count = len(colors)
    avg_r = int(r_sum / count)
    avg_g = int(g_sum / count)
    avg_b = int(b_sum / count)

    return f"#{avg_r:02x}{avg_g:02x}{avg_b:02x}", count


def get_user_base_color(user_id):
    """Get the saved base color for a user"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT base_color FROM user_base_colors WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result["base_color"] if result else None


def set_user_base_color(user_id, base_color):
    """Save the base color for a user"""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """INSERT OR REPLACE INTO user_base_colors (user_id, base_color)
           VALUES (?, ?)""",
        (user_id, base_color),
    )
    conn.commit()
    conn.close()


def find_user_by_base_color(base_color):
    """Find a user_id by their base color"""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT user_id FROM user_base_colors WHERE base_color = ?", (base_color,)
    )
    result = c.fetchone()
    conn.close()
    return result["user_id"] if result else None


@app.route("/")
@ensure_user_id
def index():
    return render_template(
        "index.html",
        debug=DEBUG,
        livereload_token=get_live_reload_token() if DEBUG else None,
        livereload_interval=int(LIVERELOAD_POLL_INTERVAL * 1000),
    )


@app.route("/__livereload")
def livereload_endpoint():
    if not DEBUG:
        return jsonify({"enabled": False}), 404

    response = jsonify(
        {
            "enabled": True,
            "version": get_live_reload_token(),
            "interval": LIVERELOAD_POLL_INTERVAL,
        }
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/next-shade")
@ensure_user_id
def next_shade():
    """Get the next shade to show the user"""
    shade = generate_blue_shade()

    # Store that we've shown this shade to the user
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO shown_shades (user_id, hex_color) VALUES (?, ?)",
        (session["user_id"], shade),
    )
    conn.commit()
    conn.close()

    return render_template("shade_card.html", shade=shade)


@app.route("/vote", methods=["POST"])
@ensure_user_id
def vote():
    """Record a user's vote for a shade"""
    shade = request.form.get("shade")
    choice = request.form.get("choice")  # 'yes', 'no', or 'skip'

    if choice != "skip":
        is_anika_blue = 1 if choice == "yes" else 0

        conn = get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO choices (user_id, hex_color, is_anika_blue) VALUES (?, ?, ?)",
            (session["user_id"], shade, is_anika_blue),
        )
        conn.commit()
        conn.close()

    # Get updated averages
    user_avg = get_user_average(session["user_id"])
    if user_avg:
        set_user_base_color(session["user_id"], user_avg[0])

    global_avg = get_global_average()

    return render_template("stats.html", user_avg=user_avg, global_avg=global_avg)


@app.route("/stats")
@ensure_user_id
def stats():
    """Get current statistics"""
    user_avg = get_user_average(session["user_id"])
    global_avg = get_global_average()

    return render_template("stats.html", user_avg=user_avg, global_avg=global_avg)


@app.route("/save-base-color", methods=["POST"])
@ensure_user_id
def save_base_color():
    """Save the current user's base color"""
    user_avg = get_user_average(session["user_id"])

    if user_avg:
        base_color = user_avg[0]
        set_user_base_color(session["user_id"], base_color)
        return jsonify({"success": True, "base_color": base_color})

    return jsonify({"success": False, "error": "No average color available"}), 400


@app.route("/load-base-color", methods=["POST"])
def load_base_color():
    """Load a user session by their base color"""
    base_color = request.form.get("base_color", "").strip()

    if not base_color:
        return jsonify({"success": False, "error": "No base color provided"}), 400

    # Validate hex color format
    if not base_color.startswith("#") or len(base_color) != 7:
        return jsonify({"success": False, "error": "Invalid hex color format"}), 400

    user_id = find_user_by_base_color(base_color)

    if user_id:
        session["user_id"] = user_id
        return jsonify({"success": True, "message": "Session restored successfully"})

    return (
        jsonify({"success": False, "error": "No user found with this base color"}),
        404,
    )


@app.route("/favicon.ico")
def favicon():
    """Generate a dynamic favicon based on user's Anika Blue color"""
    # Get user ID from session if available
    user_id = session.get("user_id")

    # Determine which color to use
    color = None
    if user_id:
        user_avg = get_user_average(user_id)
        if user_avg:
            color = user_avg[0]

    # If no user color, use global average
    if not color:
        global_avg = get_global_average()
        if global_avg:
            color = global_avg[0]
        else:
            # Default to a nice blue if no data exists
            color = "#667eea"

    # Convert hex to RGB
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)

    # Create a simple square favicon
    img = Image.new("RGB", (32, 32), color=(r, g, b))

    # Save to BytesIO
    img_io = BytesIO()
    img.save(img_io, "ICO")
    img_io.seek(0)

    return send_file(img_io, mimetype="image/x-icon")
