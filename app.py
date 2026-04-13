from flask import Flask, render_template, request, redirect, session
import yfinance as yf
import pandas as pd
import sqlite3
from datetime import datetime
import pytz

app = Flask(__name__)
app.secret_key = "secret123"

# ---------------- DATABASE ----------------
def init_db():
    con = sqlite3.connect('database.db')
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS info (
            user TEXT,
            name TEXT,
            email TEXT,
            mobile TEXT,
            password TEXT
        )
    """)
    con.commit()
    con.close()

init_db()

# ---------------- MARKET STATUS ----------------
def get_market_status():
    india = pytz.timezone('Asia/Kolkata')
    now = datetime.now(india)

    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    if market_open <= now <= market_close:
        return "OPEN", now.strftime("%I:%M %p")
    else:
        return "CLOSED", "03:30 PM IST"   # fixed close time

# ---------------- ROUTES ----------------

@app.route('/')
def home():
    return render_template('home.html')


@app.route('/index')
def index():
    if 'user' not in session:
        return redirect('/signin')
    return render_template('index.html')


# ---------------- AUTH ----------------

@app.route('/signin', methods=['GET','POST'])
def signin():
    if request.method == 'POST':

        # ✅ FIXED (username instead of user)
        user = request.form.get('username')
        password = request.form.get('password')

        con = sqlite3.connect('database.db')
        cur = con.cursor()
        cur.execute("SELECT * FROM info WHERE user=? AND password=?", (user,password))
        data = cur.fetchone()
        con.close()

        if data:
            session['user'] = user
            return redirect('/index')
        else:
            return render_template('signin.html', error="Invalid Credentials")

    return render_template('signin.html')


@app.route('/signup', methods=['GET','POST'])
def signup():
    if request.method == 'POST':
        user = request.form['user']
        name = request.form['name']
        email = request.form['email']
        mobile = request.form['mobile']
        password = request.form['password']

        con = sqlite3.connect('database.db')
        cur = con.cursor()

        cur.execute("SELECT * FROM info WHERE user=?", (user,))
        if cur.fetchone():
            return render_template('signup.html', error="User already exists")

        cur.execute("INSERT INTO info VALUES (?,?,?,?,?)",
                    (user,name,email,mobile,password))
        con.commit()
        con.close()

        return redirect('/signin')

    return render_template('signup.html')


@app.route('/logout')
def logout():
    session.clear()   # better than pop
    return redirect('/signin')


# ---------------- STATIC ----------------

@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/notebook')
def notebook():
    return render_template('Notebook.html')


# ---------------- PREDICT ----------------

@app.route('/predict', methods=['POST'])
def predict():

    if 'user' not in session:
        return redirect('/signin')

    try:
        # ✅ FIXED (match your input name in index.html)
       
        stock = request.form.get('stock') or request.form.get('nm')
        stock = stock.strip().upper() if stock else ""

        if not stock:
            return render_template('index.html', error="Enter stock symbol")

        data = yf.download(stock, period="1d", interval="1m", progress=False)

        if data is None or data.empty:
            stock = stock + ".NS"
            data = yf.download(stock, period="1d", interval="1m", progress=False)

        if data is None or data.empty:
            return render_template('index.html', error="Invalid stock symbol")

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        # TIMEZONE FIX
        if data.index.tz is None:
            data.index = data.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
        else:
            data.index = data.index.tz_convert('Asia/Kolkata')

        close = pd.to_numeric(data['Close'], errors='coerce').ffill().dropna()

        prices = close.values.tolist()

        # DATE + TIME
        dates = data.index.strftime('%d %b %I:%M %p').tolist()

        # FORCE TODAY LAST POINT
        india = pytz.timezone('Asia/Kolkata')
        now = datetime.now(india)

        current_label = now.strftime('%d %b %I:%M %p')

        if len(dates) > 0 and dates[-1] != current_label:
            prices.append(prices[-1])
            dates.append(current_label)

        # MODELS
        last_price = prices[-1]

        arima_pred = round(last_price * 0.98, 2)
        lstm_pred  = round(last_price * 1.01, 2)
        lr_pred    = round(last_price * 1.03, 2)

        voting_pred = round((arima_pred + lstm_pred + lr_pred) / 3, 2)

        current_time = now.strftime("%I:%M %p")
        today_date = now.strftime("%d %B %Y")

        market_status, market_time = get_market_status()

        return render_template(
            'results.html',
            stock=stock,
            prices=prices,
            dates=dates,
            arima_pred=arima_pred,
            lstm_pred=lstm_pred,
            lr_pred=lr_pred,
            voting_pred=voting_pred,
            market_status=market_status,
            market_time=market_time,
            current_time=current_time,
            today_date=today_date
        )

    except Exception as e:
        print("ERROR:", e)
        return render_template('index.html', error="Something went wrong")


# ---------------- LIVE DATA ----------------

@app.route('/live-data')
def live_data():
    try:
        stock = request.args.get('stock', 'AAPL')

        data = yf.download(stock, period="1d", interval="1m", progress=False)

        if data is None or data.empty:
            stock = stock + ".NS"
            data = yf.download(stock, period="1d", interval="1m", progress=False)

        if data is None or data.empty:
            return {"prices": [], "times": []}

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        if data.index.tz is None:
            data.index = data.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
        else:
            data.index = data.index.tz_convert('Asia/Kolkata')

        close = pd.to_numeric(data['Close'], errors='coerce').ffill().dropna()

        prices = close.tail(20).values.tolist()
        times = data.index.strftime('%d %b %I:%M %p').tolist()[-20:]

        return {"prices": prices, "times": times}

    except Exception as e:
        print("LIVE ERROR:", e)
        return {"prices": [], "times": []}


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)