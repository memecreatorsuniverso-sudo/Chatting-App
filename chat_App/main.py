import os
import time
import uuid
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_login import LoginManager, login_required, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit, join_room, leave_room
from models import db, User, Message, FriendRequest, Block
from config import Config

# ---------- App setup ----------
app = Flask(__name__)
app.config.from_object(Config)

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {"png","jpg","jpeg","gif","webp","bmp","pdf","docx","doc","zip","txt","mp3","wav","ogg"}

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

login_manager = LoginManager(app)
login_manager.login_view = "index"

@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))

# ---------- Memory State ----------
waiting_queue = []
paired = {}
user_rooms = {}
sid_to_user = {}
user_to_sid = {}
user_id_to_sid = {}
sid_to_user_id = {}

# ---------- Helpers ----------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS

def make_anon_name():
    return f"Anon_{str(uuid.uuid4())[:8]}"

# ---------- Routes ----------
@app.route("/", methods=["GET","POST"])
def index():
    if request.method == "POST":
        action = request.form.get("action")
        username = request.form.get("username","").strip()
        password = request.form.get("password","")

        if not username or not password:
            flash("Enter username & password")
            return redirect(url_for("index"))

        if action == "register":
            if User.query.filter_by(username=username).first():
                flash("Username exists")
                return redirect(url_for("index"))

            u = User(username=username, password_hash=generate_password_hash(password))
            db.session.add(u)
            db.session.commit()
            login_user(u)
            return redirect(url_for("chat"))

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("chat"))

        flash("Invalid login")
        return redirect(url_for("index"))

    return render_template("index.html")


@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html", username=current_user.username)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or not allowed_file(file.filename):
        return jsonify({"error":"Invalid file"}),400

    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return jsonify({"filename":filename})


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ---------- SOCKET ----------
@socketio.on("connect")
def on_connect():
    print("connect:", request.sid)
    emit("online_count", {"count": len(user_to_sid)}, broadcast=True)

@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    username = sid_to_user.pop(sid, None)

    if not username:
        return

    user_to_sid.pop(username, None)

    # remove from queue
    if username in waiting_queue:
        waiting_queue.remove(username)

    # handle active chat
    partner = paired.pop(username, None)
    if partner:
        paired.pop(partner, None)

        room = user_rooms.pop(username, None)
        user_rooms.pop(partner, None)

        partner_sid = user_to_sid.get(partner)
        if partner_sid:
            emit("partner_left", {}, to=partner_sid)

            # requeue partner
            waiting_queue.append(partner)


# ---------- MATCHING ----------
@socketio.on("start_search")
def start_search(data):
    sid = request.sid

    # ✅ FIX: get username from frontend
    data = data or {}
    username = data.get("username")

    if not username:
        username = make_anon_name()

    sid_to_user[sid] = username
    user_to_sid[username] = sid

    # ✅ online count update
    socketio.emit("online_count", {"count": len(user_to_sid)})

    # clean queue
    waiting_queue[:] = [u for u in waiting_queue if u in user_to_sid and u != username]

    print("QUEUE:", waiting_queue)

    # already paired
    if username in paired:
        emit("matched", {"partner": paired[username], "room": user_rooms[username]}, to=sid)
        return

    # MATCH LOGIC
    if waiting_queue:
        partner = waiting_queue.pop(0)

        room = f"room_{partner}_{username}_{int(time.time())}"

        paired[username] = partner
        paired[partner] = username

        user_rooms[username] = room
        user_rooms[partner] = room

        join_room(room, sid=sid)

        partner_sid = user_to_sid.get(partner)

        if partner_sid:
            join_room(room, sid=partner_sid)

            emit("matched", {"partner": partner, "room": room}, to=sid)
            emit("matched", {"partner": username, "room": room}, to=partner_sid)

            print("MATCHED:", username, "<->", partner)

    else:
        waiting_queue.append(username)
        emit("waiting", {"msg": "Searching..."}, to=sid)

# ---------- CHAT ----------
@socketio.on("send_message")
def send_message(data):
    room = data.get("room")
    message = data.get("message")

    sender = sid_to_user.get(request.sid)

    if room and message:
        emit("new_message", {
            "sender": sender,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }, to=room)


@socketio.on("send_file")
def send_file(data):
    room = data.get("room")
    file_name = data.get("file_name")

    sender = sid_to_user.get(request.sid)

    if room and file_name:
        emit("new_message", {
            "sender": sender,
            "is_file": True,
            "file_name": file_name,
            "timestamp": datetime.utcnow().isoformat()
        }, to=room)


@socketio.on("typing")
def typing(data):
    room = data.get("room")
    sender = sid_to_user.get(request.sid)

    if room:
        emit("typing", {"user": sender}, to=room, include_self=False)


# ---------- RUN ----------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    socketio.run(app, host="0.0.0.0", port=8000, debug=True)
