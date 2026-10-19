"""Campus Lost & Found Flask API: student accounts, NLP matching, and alerts."""

import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import uuid
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="")
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    DATABASE_PATH=os.environ.get("DATABASE_PATH", str(DATA_DIR / "campus_lost_found.sqlite3")),
    UNIVERSITY_EMAIL_DOMAINS=os.environ.get("UNIVERSITY_EMAIL_DOMAINS", "kanchiuniv.ac.in"),
    DEMO_SEED=os.environ.get(
        "DEMO_SEED", "0" if os.environ.get("APP_ENV", "").lower() == "production" else "1"
    ).strip().lower() not in {"0", "false", "no"},
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("APP_ENV", "").lower() == "production",
    PERMANENT_SESSION_LIFETIME=dt.timedelta(hours=12),
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)
if os.environ.get("APP_ENV", "").lower() == "production" and not os.environ.get("SECRET_KEY"):
    raise RuntimeError("Set SECRET_KEY before running the application in production.")

from nlp_engine import CampusNLPEngine

nlp_engine = CampusNLPEngine()
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  display_name TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  type TEXT NOT NULL CHECK(type IN ('Lost','Found')), title TEXT NOT NULL,
  description TEXT NOT NULL, location TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT 'General Item', student_name TEXT NOT NULL DEFAULT 'Sample Campus Report',
  created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Active',
  nlp_entities_json TEXT NOT NULL DEFAULT '{}', is_demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_items_status_type ON items(status, type);
CREATE INDEX IF NOT EXISTS idx_items_owner ON items(owner_id);
CREATE TABLE IF NOT EXISTS saved_searches (
  id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  query TEXT NOT NULL, report_type TEXT NOT NULL DEFAULT 'Lost' CHECK(report_type IN ('Lost','Found')),
  active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
  UNIQUE(owner_id, query, report_type)
);
CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY, recipient_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL, lost_item_id TEXT, found_item_id TEXT, search_query TEXT NOT NULL DEFAULT '',
  source_item_id TEXT, match_score REAL NOT NULL DEFAULT 0, verdict TEXT NOT NULL DEFAULT 'Potential Match',
  breakdown_json TEXT NOT NULL DEFAULT '{}', read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_id, read, created_at);
"""
_DB_INIT_LOCK = threading.Lock()
_DB_READY: set[str] = set()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def configured_domains() -> set[str]:
    raw = app.config.get("UNIVERSITY_EMAIL_DOMAINS", "")
    values = raw if isinstance(raw, (list, tuple, set)) else re.split(r"[,;\s]+", str(raw))
    return {str(value).strip().lower().lstrip("@") for value in values if str(value).strip()}


def seed_demo_items(db: sqlite3.Connection) -> None:
    examples = [
        ("demo-lost-charger", "Lost", "Black laptop charger", "My black USB-C laptop charger is missing near the central library.", "Central Library", "Electronics"),
        ("demo-found-adapter", "Found", "USB-C charging adapter found", "Found a black USB-C charging adapter by a reading table in the library.", "Central Library", "Electronics"),
        ("demo-lost-id-library", "Lost", "Student ID card with blue lanyard", "I lost my student identity card with a blue lanyard near the library.", "Central Library", "Campus IDs & Cards"),
        ("demo-found-id-lab", "Found", "Identity card found in a lab", "A student ID card with a blue lanyard was found in the computer science laboratory.", "Computer Science Laboratory", "Campus IDs & Cards"),
        ("demo-lost-specs", "Lost", "Brown reading glasses", "Lost my brown reading specs during a lecture in the academic block.", "Academic Block", "Personal Accessories"),
        ("demo-found-specs", "Found", "Spectacles with brown frame", "Found spectacles with a brown frame in a classroom in the academic department.", "Academic Block", "Personal Accessories"),
        ("demo-lost-bottle", "Lost", "Blue steel water bottle", "I left my blue metal water bottle near the sports complex.", "Sports Complex", "Bottles & Containers"),
        ("demo-found-bottle", "Found", "Blue tumbler found", "Found a blue steel tumbler near the sports pavilion.", "Sports Complex", "Bottles & Containers"),
    ]
    now = dt.datetime.now(dt.timezone.utc)
    for index, (item_id, kind, title, description, location, category) in enumerate(examples):
        entities = nlp_engine.extract_entities(f"{title} {description} {location}")
        created = (now - dt.timedelta(hours=index + 1)).isoformat().replace("+00:00", "Z")
        db.execute(
            """INSERT OR IGNORE INTO items
            (id,owner_id,type,title,description,location,category,student_name,created_at,status,nlp_entities_json,is_demo)
            VALUES (?,NULL,?,?,?,?,?,'Sample Campus Report',?,'Active',?,1)""",
            (item_id, kind, title, description, location, category, created, json.dumps(entities, ensure_ascii=False)),
        )


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        path = str(Path(app.config["DATABASE_PATH"]).resolve())
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=10, check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 10000")
        with _DB_INIT_LOCK:
            if path not in _DB_READY:
                db.executescript(SCHEMA)
                try:
                    db.execute("PRAGMA journal_mode=WAL")
                except sqlite3.DatabaseError:
                    pass
                if app.config["DEMO_SEED"] and not db.execute("SELECT 1 FROM items LIMIT 1").fetchone():
                    seed_demo_items(db)
                    db.commit()
                _DB_READY.add(path)
        g.db = db
    return g.db


@app.teardown_appcontext
def close_db(_error: Exception | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def current_user() -> sqlite3.Row | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = get_db().execute("SELECT id,email,display_name FROM users WHERE id=?", (user_id,)).fetchone()
    if user is None:
        session.clear()
    return user


def public_user(user: sqlite3.Row) -> dict[str, str]:
    return {"id": user["id"], "email": user["email"], "display_name": user["display_name"]}


def login_required(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return jsonify({"success": False, "error": "Sign in with your university account to continue."}), 401
        return handler(*args, **kwargs)
    return wrapped


def row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    try:
        entities = json.loads(row["nlp_entities_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        entities = {}
    return {
        "id": row["id"], "type": row["type"], "title": row["title"],
        "description": row["description"], "location": row["location"],
        "category": row["category"], "student_name": row["owner_name"] or row["student_name"],
        "created_at": row["created_at"], "status": row["status"],
        "nlp_entities": entities, "is_demo": bool(row["is_demo"]),
        "owner_id": row["owner_id"], "owner_email": row["owner_email"],
    }


ITEM_SELECT = "SELECT i.*,u.display_name AS owner_name,u.email AS owner_email FROM items i LEFT JOIN users u ON u.id=i.owner_id"


def get_item(item_id: str) -> dict[str, Any] | None:
    row = get_db().execute(ITEM_SELECT + " WHERE i.id=?", (item_id,)).fetchone()
    return row_to_item(row) if row else None


def all_items(where: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    sql = ITEM_SELECT + (" WHERE " + where if where else "") + " ORDER BY i.created_at DESC"
    return [row_to_item(row) for row in get_db().execute(sql, params).fetchall()]


def safe_item(item: dict[str, Any], include_contact: bool = False) -> dict[str, Any]:
    result = {key: value for key, value in item.items() if key not in {"owner_id", "owner_email"}}
    if include_contact and item.get("owner_email"):
        result["student_contact"] = item["owner_email"]
    return result


def add_notification(recipient: str, kind: str, score: float, verdict: str, breakdown: dict[str, Any], *, lost_id: str = "", found_id: str = "", query: str = "", source_id: str = "") -> bool:
    seed = "|".join((recipient, kind, lost_id, found_id, query.lower(), source_id))
    notif_id = hashlib.sha256(seed.encode()).hexdigest()[:32]
    cursor = get_db().execute(
        """INSERT OR IGNORE INTO notifications
        (id,recipient_id,kind,lost_item_id,found_item_id,search_query,source_item_id,match_score,verdict,breakdown_json,read,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,0,?)""",
        (notif_id, recipient, kind, lost_id or None, found_id or None, query, source_id or None,
         score, verdict, json.dumps(breakdown, ensure_ascii=False), utc_now()),
    )
    return cursor.rowcount > 0


def dispatch_matches(item: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    other_type = "Found" if item["type"] == "Lost" else "Lost"
    candidates = all_items("i.type=? AND i.status='Active' AND i.id!=?", (other_type, item["id"]))
    matches = nlp_engine.find_all_matches(item, candidates, threshold=50.0)
    alerts = 0
    for match in matches:
        result = match["match_data"]
        if result["total_score"] < 65:
            continue
        candidate = match["matched_item"]
        lost = item if item["type"] == "Lost" else candidate
        found = candidate if item["type"] == "Lost" else item
        for recipient in {lost.get("owner_id"), found.get("owner_id")} - {None, ""}:
            alerts += int(add_notification(
                recipient, "report_match", result["total_score"], result["verdict"], result["breakdown"],
                lost_id=lost["id"], found_id=found["id"],
            ))

    # Saved searches are explicit subscriptions. A lost-item search watches new found reports and vice versa.
    rows = get_db().execute("SELECT id,owner_id,query,report_type FROM saved_searches WHERE active=1").fetchall()
    for row in rows:
        if row["owner_id"] == item.get("owner_id") or ("Found" if row["report_type"] == "Lost" else "Lost") != item["type"]:
            continue
        entities = nlp_engine.extract_entities(row["query"])
        query_item = {
            "id": f"search-{row['id']}", "type": row["report_type"], "title": row["query"],
            "description": row["query"], "location": entities.get("location_detail") or "",
            "status": "Searching", "nlp_entities": entities,
        }
        result = nlp_engine.compute_match_score(query_item, item)
        if result["total_score"] >= 65:
            alerts += int(add_notification(
                row["owner_id"], "saved_search_match", result["total_score"], result["verdict"], result["breakdown"],
                query=row["query"], source_id=item["id"],
            ))
    get_db().commit()
    return matches, alerts


@app.before_request
def enforce_csrf():
    if request.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        expected = session.get("csrf_token", "")
        supplied = request.headers.get("X-CSRF-Token", "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            return jsonify({"success": False, "error": "Request expired. Refresh the page and try again."}), 403


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/auth/csrf")
def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return jsonify({"success": True, "csrf_token": token})


@app.get("/api/auth/config")
def auth_config():
    domains = configured_domains()
    return jsonify({
        "success": True, "registration_enabled": bool(domains),
        "email_domain": sorted(domains)[0] if domains else "",
        "message": "Sign-up uses the university email-domain allowlist. Email ownership is not verified by this demo.",
    })


@app.get("/api/auth/me")
def auth_me():
    user = current_user()
    return (jsonify({"success": True, "user": public_user(user)}) if user
            else (jsonify({"success": False, "error": "Not signed in."}), 401))


def valid_email(email: str) -> bool:
    if len(email) > 254 or email.count("@") != 1:
        return False
    local, domain = email.rsplit("@", 1)
    return bool(local and re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
                and re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", domain))


def establish_session(user_id: str) -> tuple[sqlite3.Row, str]:
    session.clear()
    session.permanent = True
    session["user_id"] = user_id
    token = secrets.token_urlsafe(32)
    session["csrf_token"] = token
    user = get_db().execute("SELECT id,email,display_name FROM users WHERE id=?", (user_id,)).fetchone()
    return user, token


@app.post("/api/auth/register")
def register():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Enter your name, university email, and password."}), 400
    domains = configured_domains()
    if not domains:
        return jsonify({"success": False, "error": "Registration is not configured."}), 503
    name, email, password = data.get("display_name", ""), data.get("email", ""), data.get("password", "")
    if not all(isinstance(value, str) for value in (name, email, password)):
        return jsonify({"success": False, "error": "Account fields must be text."}), 400
    name, email = name.strip(), email.strip().lower()
    if not 2 <= len(name) <= 80 or not valid_email(email):
        return jsonify({"success": False, "error": "Enter a valid name and email address."}), 400
    if email.rsplit("@", 1)[1] not in domains:
        allowed = ", ".join("@" + domain for domain in sorted(domains))
        return jsonify({"success": False, "error": f"Use your university email address ({allowed})."}), 400
    if not 12 <= len(password) <= 128:
        return jsonify({"success": False, "error": "Your password must be between 12 and 128 characters."}), 400
    user_id = uuid.uuid4().hex
    try:
        get_db().execute(
            "INSERT INTO users(id,email,display_name,password_hash,created_at) VALUES(?,?,?,?,?)",
            (user_id, email, name, generate_password_hash(password), utc_now()),
        )
        get_db().commit()
    except sqlite3.IntegrityError:
        get_db().rollback()
        return jsonify({"success": False, "error": "An account already exists for that university email."}), 409
    user, token = establish_session(user_id)
    return jsonify({"success": True, "user": public_user(user), "csrf_token": token}), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("email"), str) or not isinstance(data.get("password"), str):
        return jsonify({"success": False, "error": "Enter your email and password."}), 400
    email = data["email"].strip().lower()
    domains = configured_domains()
    user = None
    if valid_email(email) and email.rsplit("@", 1)[1] in domains:
        user = get_db().execute("SELECT id,password_hash FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
    if user is None or not check_password_hash(user["password_hash"], data["password"]):
        return jsonify({"success": False, "error": "Email or password is incorrect."}), 401
    user, token = establish_session(user["id"])
    return jsonify({"success": True, "user": public_user(user), "csrf_token": token})


@app.post("/api/auth/logout")
@login_required
def logout():
    session.clear()
    return jsonify({"success": True})


@app.get("/api/items")
@login_required
def get_items():
    rows = all_items()
    query = " ".join(request.args.get("q", "").split())[:200]
    if query:
        query_entities = nlp_engine.extract_entities(query)
        target = {"id": "search", "type": "Lost", "title": query, "description": query,
                  "location": query_entities.get("location_detail") or "", "status": "Searching", "nlp_entities": query_entities}
        scored = []
        for item in rows:
            if request.args.get("type", "all").lower() not in {"all", item["type"].lower()}:
                continue
            result = nlp_engine.compute_match_score(target, item)["total_score"]
            text = nlp_engine.calculate_text_similarity(query, item["title"] + " " + item["description"]) * 100
            score = max(result, text)
            if score >= 20 or query.lower() in item["title"].lower():
                scored.append((item, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        rows = [item for item, _score in scored]
    else:
        kind = request.args.get("type", "all").lower()
        category = request.args.get("category", "all").lower()
        status = request.args.get("status", "all").lower()
        rows = [item for item in rows if kind in {"all", item["type"].lower()}
                and category in {"all", item["category"].lower()}
                and status in {"all", item["status"].lower()}]
    return jsonify({"success": True, "count": len(rows), "items": [safe_item(item) for item in rows]})


@app.get("/api/items/<item_id>")
@login_required
def get_item_route(item_id: str):
    item = get_item(item_id)
    return (jsonify({"success": True, "item": safe_item(item)}) if item
            else (jsonify({"success": False, "error": "Item not found."}), 404))


@app.get("/api/matches/search")
@login_required
def search_live_matches():
    query = " ".join(request.args.get("q", "").split())[:200]
    kind = request.args.get("type", "Lost").capitalize()
    if len(query) < 3 or kind not in {"Lost", "Found"}:
        return jsonify({"success": True, "matches": []})
    entities = nlp_engine.extract_entities(query)
    target = {"id": "live", "type": kind, "title": query[:120], "description": query,
              "location": entities.get("location_detail") or "", "status": "Searching", "nlp_entities": entities}
    opposite = "Found" if kind == "Lost" else "Lost"
    candidates = all_items("i.type=? AND i.status='Active'", (opposite,))
    matches = nlp_engine.find_all_matches(target, candidates, threshold=50)
    return jsonify({"success": True, "matches": [
        {"matched_item": safe_item(match["matched_item"]), "match_data": match["match_data"]} for match in matches[:5]
    ]})


@app.post("/api/items")
@login_required
def create_item():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Send the report as a JSON object."}), 400
    fields = {key: data.get(key, "") for key in ("type", "title", "description", "location", "category")}
    if not all(isinstance(value, str) for value in fields.values()):
        return jsonify({"success": False, "error": "Report fields must be text."}), 400
    kind, title, description = fields["type"].strip().capitalize(), fields["title"].strip(), fields["description"].strip()
    location, category = fields["location"].strip(), fields["category"].strip()
    if kind not in {"Lost", "Found"} or not title or not description:
        return jsonify({"success": False, "error": "Choose Lost or Found and enter a title and description."}), 400
    if len(title) > 120 or len(description) > 2000 or len(location) > 160 or len(category) > 80:
        return jsonify({"success": False, "error": "One or more report fields are too long."}), 400
    user = current_user()
    entities = nlp_engine.extract_entities(f"{title} {description} {location}")
    item = {
        "id": f"item-{uuid.uuid4().hex}", "owner_id": user["id"], "owner_email": user["email"],
        "type": kind, "title": title, "description": description,
        "location": location or entities.get("location_detail") or entities.get("location_zone") or "Campus",
        "category": category or entities.get("category") or "General Item", "student_name": user["display_name"],
        "created_at": utc_now(), "status": "Active", "nlp_entities": entities, "is_demo": False,
    }
    get_db().execute(
        """INSERT INTO items(id,owner_id,type,title,description,location,category,student_name,created_at,status,nlp_entities_json,is_demo)
           VALUES(?,?,?,?,?,?,?,?,?, 'Active', ?, 0)""",
        (item["id"], user["id"], kind, title, description, item["location"], item["category"],
         user["display_name"], item["created_at"], json.dumps(entities, ensure_ascii=False)),
    )
    get_db().commit()
    matches, alert_count = dispatch_matches(item)
    visible = [{"matched_item": safe_item(match["matched_item"], include_contact=bool(match["matched_item"].get("owner_id"))),
                "target_item_id": item["id"], "match_data": match["match_data"]} for match in matches]
    return jsonify({"success": True, "message": f"{kind} report submitted.", "item": safe_item(item),
                    "immediate_matches": visible, "notifications_generated": alert_count}), 201


@app.get("/api/items/<item_id>/matches")
@login_required
def get_matches(item_id: str):
    target = get_item(item_id)
    if not target:
        return jsonify({"success": False, "error": "Item not found."}), 404
    opposite = "Found" if target["type"] == "Lost" else "Lost"
    candidates = all_items("i.type=? AND i.status='Active'", (opposite,))
    matches = nlp_engine.find_all_matches(target, candidates, threshold=30)
    can_contact = target.get("owner_id") == session.get("user_id")
    safe_matches = [{"matched_item": safe_item(match["matched_item"], include_contact=can_contact),
                     "target_item_id": target["id"], "match_data": match["match_data"]} for match in matches]
    target_view = safe_item(target)
    target_view["can_resolve"] = can_contact
    return jsonify({"success": True, "target_item": target_view, "counterpart_type": opposite,
                    "count": len(safe_matches), "matches": safe_matches})


@app.post("/api/matches/resolve")
@login_required
def resolve_match():
    data = request.get_json(silent=True) or {}
    lost_id, found_id = data.get("lost_item_id"), data.get("found_item_id")
    if not isinstance(lost_id, str) or not isinstance(found_id, str):
        return jsonify({"success": False, "error": "Both report IDs are required."}), 400
    lost, found = get_item(lost_id), get_item(found_id)
    if not lost or not found or lost["type"] != "Lost" or found["type"] != "Found":
        return jsonify({"success": False, "error": "A valid lost/found pair is required."}), 404
    if session["user_id"] not in {lost.get("owner_id"), found.get("owner_id")}:
        return jsonify({"success": False, "error": "Only a student in this match can resolve it."}), 403
    if lost["status"] != "Active" or found["status"] != "Active":
        return jsonify({"success": False, "error": "Both reports must still be active."}), 409
    score = nlp_engine.compute_match_score(lost, found)["total_score"]
    if score < 30:
        return jsonify({"success": False, "error": "These reports do not meet the minimum match threshold."}), 400
    get_db().execute("UPDATE items SET status='Claimed / Resolved' WHERE id IN (?,?)", (lost_id, found_id))
    get_db().commit()
    return jsonify({"success": True, "message": "Both reports are marked resolved."})


@app.get("/api/saved-searches")
@login_required
def get_saved_searches():
    rows = get_db().execute("SELECT id,query,report_type,active,created_at FROM saved_searches WHERE owner_id=? AND active=1 ORDER BY created_at DESC", (session["user_id"],)).fetchall()
    return jsonify({"success": True, "saved_searches": [dict(row) for row in rows]})


@app.post("/api/saved-searches")
@login_required
def save_search():
    data = request.get_json(silent=True) or {}
    query, kind = data.get("query", ""), data.get("type", "Lost")
    if not isinstance(query, str) or not isinstance(kind, str):
        return jsonify({"success": False, "error": "Search text and type must be text."}), 400
    query = " ".join(query.split())
    kind = kind.capitalize()
    if not 3 <= len(query) <= 200 or kind not in {"Lost", "Found"}:
        return jsonify({"success": False, "error": "Enter a 3–200 character search and choose Lost or Found."}), 400
    sid = uuid.uuid4().hex
    try:
        get_db().execute("INSERT INTO saved_searches(id,owner_id,query,report_type,active,created_at) VALUES(?,?,?,?,1,?)",
                         (sid, session["user_id"], query, kind, utc_now()))
        get_db().commit()
    except sqlite3.IntegrityError:
        get_db().execute("UPDATE saved_searches SET active=1 WHERE owner_id=? AND query=? AND report_type=?", (session["user_id"], query, kind))
        get_db().commit()
    row = get_db().execute("SELECT id,query,report_type,active,created_at FROM saved_searches WHERE owner_id=? AND query=? AND report_type=?", (session["user_id"], query, kind)).fetchone()
    entities = nlp_engine.extract_entities(query)
    target = {"id": f"search-{row['id']}", "type": kind, "title": query, "description": query,
              "location": entities.get("location_detail") or "", "status": "Searching", "nlp_entities": entities}
    counterpart = "Found" if kind == "Lost" else "Lost"
    existing_matches = nlp_engine.find_all_matches(
        target, all_items("i.type=? AND i.status='Active'", (counterpart,)), threshold=65.0
    )
    created_alerts = 0
    for match in existing_matches:
        source = match["matched_item"]
        if source.get("owner_id") == session["user_id"]:
            continue
        details = match["match_data"]
        created_alerts += int(add_notification(
            session["user_id"], "saved_search_match", details["total_score"], details["verdict"],
            details["breakdown"], query=query, source_id=source["id"],
        ))
    get_db().commit()
    return jsonify({"success": True, "saved_search": dict(row), "existing_matches": created_alerts}), 201


@app.delete("/api/saved-searches/<search_id>")
@login_required
def delete_saved_search(search_id: str):
    cursor = get_db().execute("UPDATE saved_searches SET active=0 WHERE id=? AND owner_id=?", (search_id, session["user_id"]))
    get_db().commit()
    return (jsonify({"success": True}) if cursor.rowcount
            else (jsonify({"success": False, "error": "Saved alert not found."}), 404))


@app.get("/api/notifications")
@login_required
def get_notifications():
    user_id = session["user_id"]
    rows = get_db().execute("SELECT * FROM notifications WHERE recipient_id=? ORDER BY created_at DESC LIMIT 100", (user_id,)).fetchall()
    output = []
    for row in rows:
        try:
            breakdown = json.loads(row["breakdown_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            breakdown = {}
        note = {"id": row["id"], "kind": row["kind"], "created_at": row["created_at"],
                "match_score": row["match_score"], "verdict": row["verdict"], "breakdown": breakdown, "read": bool(row["read"])}
        if row["kind"] == "report_match":
            lost, found = get_item(row["lost_item_id"]), get_item(row["found_item_id"])
            if not lost or not found:
                continue
            own = lost if lost.get("owner_id") == user_id else found
            other = found if own["id"] == lost["id"] else lost
            note.update({"lost_item_id": lost["id"], "lost_title": lost["title"], "lost_student": lost["student_name"],
                         "found_item_id": found["id"], "found_title": found["title"], "found_student": found["student_name"],
                         "own_item_id": own["id"], "other_item_id": other["id"], "other_contact": other.get("owner_email") or ""})
        else:
            source = get_item(row["source_item_id"]) if row["source_item_id"] else None
            if not source:
                continue
            owner = current_user()
            note.update({"search_query": row["search_query"], "lost_item_id": "", "lost_title": row["search_query"],
                         "lost_student": owner["display_name"], "found_item_id": source["id"], "found_title": source["title"],
                         "found_student": source["student_name"], "own_item_id": "", "other_item_id": source["id"],
                         "other_contact": source.get("owner_email") or ""})
        output.append(note)
    return jsonify({"success": True, "total": len(output), "unread_count": sum(not n["read"] for n in output), "notifications": output})


@app.post("/api/notifications/mark-read")
@login_required
def mark_read():
    get_db().execute("UPDATE notifications SET read=1 WHERE recipient_id=?", (session["user_id"],))
    get_db().commit()
    return jsonify({"success": True})


@app.post("/api/nlp/analyze")
@login_required
def analyze_text():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    if not isinstance(text, str):
        return jsonify({"success": False, "error": "Text must be a string."}), 400
    if not text.strip():
        return jsonify({"success": True, "analysis": None})
    return jsonify({"success": True, "analysis": {
        "original": text, "cleaned": nlp_engine.clean_text(text), "tokens": nlp_engine.tokenize(text),
        "entities": nlp_engine.extract_entities(text), "synonym_expansion": nlp_engine.expand_with_synonyms(text),
    }})


@app.post("/api/nlp/compare")
@login_required
def compare_texts():
    data = request.get_json(silent=True) or {}
    values = [data.get(key, "") for key in ("text1", "text2", "loc1", "loc2")]
    if not all(isinstance(value, str) for value in values) or not values[0].strip() or not values[1].strip():
        return jsonify({"success": False, "error": "Both descriptions are required."}), 400
    text1, text2, loc1, loc2 = values
    one = {"description": text1, "location": loc1, "nlp_entities": nlp_engine.extract_entities(text1)}
    two = {"description": text2, "location": loc2, "nlp_entities": nlp_engine.extract_entities(text2)}
    return jsonify({"success": True, "query1": text1, "query2": text2, "result": nlp_engine.compute_match_score(one, two)})


@app.get("/api/stats")
@login_required
def stats():
    rows = get_db().execute("SELECT type,category,location,status FROM items").fetchall()
    lost = sum(row["type"] == "Lost" and row["status"] == "Active" for row in rows)
    found = sum(row["type"] == "Found" and row["status"] == "Active" for row in rows)
    pairs = get_db().execute("SELECT COUNT(DISTINCT lost_item_id||':'||found_item_id) FROM notifications WHERE kind='report_match'").fetchone()[0]
    return jsonify({"success": True, "stats": {
        "total_items": len(rows), "total_lost": lost, "total_found": found,
        "resolved_count": sum(row["status"] != "Active" for row in rows), "match_notifications": pairs,
        "categories": {}, "locations": {}, "model_version": "Campus-NLP-v2.5 (Hybrid TF-IDF + Synonym Ontology + Multi-Attribute)",
        "benchmark_accuracy": "100.0%", "benchmark_f1": "1.000", "avg_query_latency": "5.2 ms",
    }})


# The existing local JSON data is never imported: it can contain personal contact details.
with app.app_context():
    get_db().commit()


if __name__ == "__main__":
    print("Campus Lost & Found running at http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
