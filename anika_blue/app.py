import colorsys
import hashlib
import math
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
import webcolors

CSS3_NAME_LIST = webcolors.names(webcolors.CSS3)
CSS3_HEX_TO_NAMES = {
    webcolors.normalize_hex(webcolors.name_to_hex(name, spec=webcolors.CSS3)): name
    for name in CSS3_NAME_LIST
}

COLOR_NAME_SUFFIXES = sorted(
    {
        "aquamarine",
        "chartreuse",
        "turquoise",
        "goldenrod",
        "firebrick",
        "spring",
        "magenta",
        "orange",
        "purple",
        "yellow",
        "violet",
        "indigo",
        "silver",
        "brown",
        "black",
        "white",
        "green",
        "blue",
        "gray",
        "grey",
        "red",
        "pink",
        "cyan",
        "gold",
        "aqua",
        "beige",
        "coral",
        "olive",
        "ivory",
        "tan",
        "khaki",
        "teal",
        "navy",
        "plum",
        "rose",
        "peru",
        "sienna",
        "wheat",
        "steel",
        "slate",
        "sky",
        "sea",
        "mint",
        "lavender",
        "honeydew",
        "lemon",
        "powder",
        "sandy",
        "peach",
        "papaya",
        "moccasin",
        "linen",
        "snow",
        "seashell",
        "orchid",
        "salmon",
        "tomato",
        "chocolate",
        "almond",
        "chiffon",
        "cream",
        "smoke",
        "ghost",
        "gainsboro",
        "antique",
        "rebecca",
        "dodger",
        "royal",
        "medium",
        "light",
        "dark",
        "deep",
        "pale",
        "hot",
        "old",
        "forest",
        "floral",
        "cadet",
        "lime",
        "fuchsia",
        "azure",
        "bisque",
        "thistle",
        "burly",
        "wood",
        "rosy",
        "lawn",
    },
    key=len,
    reverse=True,
)

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

    # Table for user votes (with migration support for legacy "choices" table)
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='votes'")
    has_votes_table = c.fetchone() is not None

    if not has_votes_table:
        c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='choices'"
        )
        legacy_choices_table = c.fetchone() is not None

        if legacy_choices_table:
            c.execute("ALTER TABLE choices RENAME TO votes")

    c.execute(
        """CREATE TABLE IF NOT EXISTS votes
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


def normalize_hex_color(hex_color: str | None) -> str | None:
    if not hex_color:
        return None
    value = hex_color.strip()
    if not value:
        return None
    if not value.startswith("#"):
        value = f"#{value}"
    value = value[:7]
    return value.lower()


def format_color_name(raw_name: str | None) -> str:
    if not raw_name:
        return "Unknown Color"
    name = raw_name.replace("-", " ").replace("_", " ").strip()
    if " " in name:
        return " ".join(word.capitalize() for word in name.split())

    for suffix in COLOR_NAME_SUFFIXES:
        if name.endswith(suffix) and name != suffix:
            prefix = name[: -len(suffix)]
            prefix_formatted = format_color_name(prefix)
            if prefix_formatted == "Unknown Color":
                prefix_formatted = prefix.capitalize() if prefix else ""
            suffix_formatted = suffix.capitalize()
            return (prefix_formatted + " " + suffix_formatted).strip()

    return name.capitalize()


def get_nearest_css3(hex_color: str | None):
    normalized = normalize_hex_color(hex_color)
    if not normalized:
        return None, None, None, False

    try:
        target_rgb = webcolors.hex_to_rgb(normalized)
    except ValueError:
        return None, None, None, False

    best_name = None
    best_hex = None
    best_distance = None

    for css_hex, css_name in CSS3_HEX_TO_NAMES.items():
        css_rgb = webcolors.hex_to_rgb(css_hex)
        distance = (
            (css_rgb.red - target_rgb.red) ** 2
            + (css_rgb.green - target_rgb.green) ** 2
            + (css_rgb.blue - target_rgb.blue) ** 2
        )

        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_name = css_name
            best_hex = css_hex

    if best_name is None:
        return None, None, None, False

    normalized_best_hex = webcolors.normalize_hex(best_hex)
    is_exact = normalized_best_hex == normalized

    return (
        format_color_name(best_name),
        normalized_best_hex,
        math.sqrt(best_distance) if best_distance is not None else None,
        is_exact,
    )


def describe_color(hex_color: str | None) -> str:
    normalized = normalize_hex_color(hex_color)
    if not normalized:
        return "Unknown Color"

    try:
        r = int(normalized[1:3], 16) / 255
        g = int(normalized[3:5], 16) / 255
        b = int(normalized[5:7], 16) / 255
    except ValueError:
        return "Unknown Color"

    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h_deg = (h * 360.0) % 360.0

    if s < 0.12:
        if l < 0.08:
            return "Near Black"
        if l < 0.22:
            return "Very Dark Gray"
        if l < 0.38:
            return "Dark Gray"
        if l < 0.65:
            return "Neutral Gray"
        if l < 0.85:
            return "Light Gray"
        return "Near White"

    hue_categories = [
        (345, 360, "Red"),
        (0, 15, "Red"),
        (15, 45, "Orange"),
        (45, 70, "Golden Yellow"),
        (70, 100, "Lime"),
        (100, 135, "Green"),
        (135, 165, "Spring Green"),
        (165, 190, "Teal"),
        (190, 215, "Cyan"),
        (215, 245, "Azure"),
        (245, 275, "Blue"),
        (275, 305, "Indigo"),
        (305, 330, "Violet"),
        (330, 345, "Magenta"),
    ]

    hue_name = "Color"
    for start, end, name in hue_categories:
        if start <= end:
            if start <= h_deg < end:
                hue_name = name
                break
        else:  # wraparound segment
            if h_deg >= start or h_deg < end:
                hue_name = name
                break

    if s < 0.28:
        saturation_adj = "Soft"
    elif s < 0.55:
        saturation_adj = ""
    elif s < 0.78:
        saturation_adj = "Vivid"
    else:
        saturation_adj = "Brilliant"

    if l < 0.2:
        lightness_adj = "Deep"
    elif l < 0.35:
        lightness_adj = "Dark"
    elif l < 0.5:
        lightness_adj = ""
    elif l < 0.7:
        lightness_adj = "Light"
    else:
        lightness_adj = "Pale"

    parts = [part for part in (saturation_adj, lightness_adj, hue_name) if part]
    return " ".join(parts) if parts else hue_name


def get_color_details(hex_color: str | None) -> dict:
    normalized = normalize_hex_color(hex_color)
    css_name, css_hex, css_distance, css_exact = get_nearest_css3(normalized)
    descriptive_name = describe_color(normalized)

    css_display_name = None
    if css_name:
        prefix = "" if css_exact else "~ "
        css_display_name = f"{prefix}{css_name}"

    if css_display_name:
        combined_name = f"{descriptive_name} / {css_display_name}"
    else:
        combined_name = descriptive_name

    return {
        "descriptive_name": descriptive_name,
        "css_name": css_name,
        "css_hex": css_hex,
        "css_distance": round(css_distance, 2) if css_distance is not None else None,
        "css_exact": css_exact,
        "css_display_name": css_display_name,
        "display_name": combined_name,
        "combined_name": combined_name,
    }


def build_color_context(color_info):
    if not color_info:
        return None
    hex_color, count = color_info
    normalized_hex = normalize_hex_color(hex_color)
    details = get_color_details(normalized_hex or hex_color)
    return {
        "hex": normalized_hex or hex_color,
        "count": count,
        **details,
    }


def get_user_average(user_id):
    """Calculate the average color for a user's Anika Blue votes"""
    conn = get_db()
    c = conn.cursor()

    c.execute(
        """SELECT hex_color FROM votes
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
    """Calculate the global average of all Anika Blue votes"""
    conn = get_db()
    c = conn.cursor()

    c.execute(
        """SELECT hex_color FROM votes
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

    return render_template(
        "shade_card.html",
        shade=shade,
        shade_details=get_color_details(shade),
    )


@app.route("/vote", methods=["POST"])
@ensure_user_id
def vote():
    """Record a user's vote for a shade"""
    shade = request.form.get("shade")
    vote_value = request.form.get("vote")  # 'yes', 'no', or 'skip'
    if vote_value is None:
        vote_value = request.form.get("choice")  # Backward compatibility

    if vote_value != "skip":
        is_anika_blue = 1 if vote_value == "yes" else 0

        conn = get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO votes (user_id, hex_color, is_anika_blue) VALUES (?, ?, ?)",
            (session["user_id"], shade, is_anika_blue),
        )
        conn.commit()
        conn.close()

    # Get updated averages
    user_avg_tuple = get_user_average(session["user_id"])
    if user_avg_tuple:
        set_user_base_color(session["user_id"], user_avg_tuple[0])

    user_avg = build_color_context(user_avg_tuple)
    global_avg = build_color_context(get_global_average())

    return render_template("stats.html", user_avg=user_avg, global_avg=global_avg)


@app.route("/stats")
@ensure_user_id
def stats():
    """Get current statistics"""
    user_avg = build_color_context(get_user_average(session["user_id"]))
    global_avg = build_color_context(get_global_average())

    return render_template("stats.html", user_avg=user_avg, global_avg=global_avg)


@app.route("/save-base-color", methods=["POST"])
@ensure_user_id
def save_base_color():
    """Save the current user's base color"""
    user_avg_tuple = get_user_average(session["user_id"])

    if user_avg_tuple:
        base_color = user_avg_tuple[0]
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
