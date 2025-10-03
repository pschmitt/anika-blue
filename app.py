import random
import sqlite3
from flask import Flask, render_template, request, session, jsonify
from functools import wraps
import secrets
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

DATABASE = 'anika_blue.db'

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Table for user choices
    c.execute('''CREATE TABLE IF NOT EXISTS choices
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT NOT NULL,
                  hex_color TEXT NOT NULL,
                  is_anika_blue INTEGER NOT NULL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Table for shades already shown to users
    c.execute('''CREATE TABLE IF NOT EXISTS shown_shades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT NOT NULL,
                  hex_color TEXT NOT NULL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_user_id(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            session['user_id'] = secrets.token_hex(16)
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
    
    c.execute('''SELECT hex_color FROM choices 
                 WHERE user_id = ? AND is_anika_blue = 1''', (user_id,))
    
    colors = [row['hex_color'] for row in c.fetchall()]
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
    
    c.execute('''SELECT hex_color FROM choices 
                 WHERE is_anika_blue = 1''')
    
    colors = [row['hex_color'] for row in c.fetchall()]
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

@app.route('/')
@ensure_user_id
def index():
    return render_template('index.html')

@app.route('/next-shade')
@ensure_user_id
def next_shade():
    """Get the next shade to show the user"""
    shade = generate_blue_shade()
    
    # Store that we've shown this shade to the user
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO shown_shades (user_id, hex_color) VALUES (?, ?)',
              (session['user_id'], shade))
    conn.commit()
    conn.close()
    
    return render_template('shade_card.html', shade=shade)

@app.route('/vote', methods=['POST'])
@ensure_user_id
def vote():
    """Record a user's vote for a shade"""
    shade = request.form.get('shade')
    choice = request.form.get('choice')  # 'yes', 'no', or 'skip'
    
    if choice != 'skip':
        is_anika_blue = 1 if choice == 'yes' else 0
        
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO choices (user_id, hex_color, is_anika_blue) VALUES (?, ?, ?)',
                  (session['user_id'], shade, is_anika_blue))
        conn.commit()
        conn.close()
    
    # Get updated averages
    user_avg = get_user_average(session['user_id'])
    global_avg = get_global_average()
    
    return render_template('stats.html', user_avg=user_avg, global_avg=global_avg)

@app.route('/stats')
@ensure_user_id
def stats():
    """Get current statistics"""
    user_avg = get_user_average(session['user_id'])
    global_avg = get_global_average()
    
    return render_template('stats.html', user_avg=user_avg, global_avg=global_avg)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
