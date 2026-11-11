import csv
import io
import json
import os
import time
import urllib.parse
import urllib.request
from functools import wraps

from flask import (Flask, Response, flash, redirect, render_template_string,
                   request, session)
from werkzeug.security import check_password_hash, generate_password_hash

import db

db.init()
app = Flask(__name__)
app.secret_key = db.get_setting("secret")

LAYOUT = """<!doctype html><html lang="uz"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Admin panel</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,sans-serif;margin:0;background:#f4f6fa;color:#1c2333}
nav{background:#1f3a8a;padding:10px 16px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
nav a{color:#fff;text-decoration:none;padding:6px 12px;border-radius:6px;font-size:14px}
nav a:hover{background:#3552b8}nav .sp{flex:1}
main{max-width:1100px;margin:20px auto;padding:0 14px}
.card{background:#fff;border-radius:10px;padding:16px;margin-bottom:16px;box-shadow:0 1px 3px #0001}
h2{margin:0 0 12px;font-size:18px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px;border-bottom:1px solid #e6e9f0;vertical-align:top}
th{background:#f0f3fa}.tblwrap{overflow-x:auto}
input,select,textarea{padding:8px;border:1px solid #c8cfdd;border-radius:6px;font:inherit;max-width:100%}
textarea{width:100%;min-height:130px}
button,.btn{background:#1f3a8a;color:#fff;border:0;padding:8px 14px;border-radius:6px;cursor:pointer;
font:inherit;text-decoration:none;display:inline-block}
.red{background:#c0392b}.gray{background:#6b7280}.green{background:#1e8e5a}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
.flash{background:#e6f4ea;border:1px solid #b7dfc3;padding:10px;border-radius:8px;margin-bottom:12px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.stat{background:#fff;border-radius:10px;padding:16px;text-align:center;box-shadow:0 1px 3px #0001}
.stat b{display:block;font-size:28px;color:#1f3a8a}
.ok{color:#1e8e5a;font-weight:600}.bad{color:#c0392b;font-weight:600}.muted{color:#6b7280;font-size:13px}
</style></head><body>
{% if session.get('auth') %}<nav>
<a href="/">📊 Bosh sahifa</a><a href="/classes">🏫 Sinflar</a><a href="/tests">📝 Testlar</a>
<a href="/results">📥 Natijalar</a><a href="/students">👥 O'quvchilar</a>
<a href="/messages">✉️ Xabarlar</a><a href="/broadcast">📣 Xabar yuborish</a><a href="/settings">⚙️ Sozlamalar</a>
<span class="sp"></span><a href="/logout">Chiqish</a></nav>{% endif %}
<main>{% for m in get_flashed_messages() %}<div class="flash">{{ m }}</div>{% endfor %}
{{ content|safe }}</main></body></html>"""


def page(body, **ctx):
    return render_template_string(LAYOUT, content=render_template_string(body, **ctx))


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("auth"):
            return redirect("/login")
        return f(*a, **k)
    return w


# ------------------------------------------------------------------ login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if (request.form["login"] == db.get_setting("admin_login")
                and check_password_hash(db.get_setting("admin_hash"), request.form["password"])):
            session["auth"] = True
            return redirect("/")
        flash("❌ Login yoki parol noto'g'ri")
    return page("""<div class="card" style="max-width:360px;margin:60px auto">
<h2>🔐 Admin panelga kirish</h2><form method="post">
<p><input name="login" placeholder="Login" style="width:100%" required></p>
<p><input name="password" type="password" placeholder="Parol" style="width:100%" required></p>
<button style="width:100%">Kirish</button></form></div>""")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ------------------------------------------------------------------ dashboard
@app.route("/")
@login_required
def dashboard():
    c = lambda sql: db.q(sql, one=True)[0]
    stats = dict(
        students=c("SELECT COUNT(*) FROM students"),
        classes=c("SELECT COUNT(*) FROM classes"),
        tests=c("SELECT COUNT(*) FROM tests"),
        done=c("SELECT COUNT(*) FROM results WHERE done=1"),
        avg=round(c("SELECT COALESCE(AVG(percent),0) FROM results WHERE done=1"), 1),
        unfinished=c("SELECT COUNT(*) FROM results WHERE done=0"),
        msgs=c("SELECT COUNT(*) FROM messages WHERE reply IS NULL"),
    )
    recent = db.q("SELECT * FROM results ORDER BY id DESC LIMIT 10")
    return page("""<div class="stats">
<div class="stat"><b>{{s.students}}</b>O'quvchilar</div><div class="stat"><b>{{s.classes}}</b>Sinflar</div>
<div class="stat"><b>{{s.tests}}</b>Testlar</div><div class="stat"><b>{{s.done}}</b>Topshirilgan</div>
<div class="stat"><b>{{s.avg}}%</b>O'rtacha natija</div><div class="stat"><b>{{s.unfinished}}</b>Tugallanmagan</div>
<a href="/messages" style="text-decoration:none;color:inherit"><div class="stat"><b>{{s.msgs}}</b>Javobsiz xabarlar</div></a>
</div><br><div class="card"><h2>So'nggi natijalar</h2><div class="tblwrap"><table>
<tr><th>F.I.Sh</th><th>Sinf</th><th>Test</th><th>Natija</th><th>Vaqt</th></tr>
{% for r in recent %}<tr><td>{{r.full_name}}</td><td>{{r.class_name}}</td><td>{{r.test_title}}</td>
<td>{% if r.done %}{{r.score}}/{{r.total}} ({{r.percent}}%){% else %}<span class="bad">tugallanmagan</span>{% endif %}</td>
<td>{{r.started}}</td></tr>{% endfor %}</table></div></div>""", s=stats, recent=recent)


# ------------------------------------------------------------------ sinflar
@app.route("/classes", methods=["GET", "POST"])
@login_required
def classes():
    if request.method == "POST":
        names = [n.strip() for n in request.form["names"].replace(",", "\n").splitlines() if n.strip()]
        for n in names:
            db.q("INSERT INTO classes(name,lang) VALUES(?,?)", (n, request.form["lang"]), commit=True)
        flash(f"✅ {len(names)} ta sinf qo'shildi")
        return redirect("/classes")
    rows = db.q("SELECT c.*,(SELECT COUNT(*) FROM students s WHERE s.class_id=c.id) cnt "
                "FROM classes c ORDER BY lang,name")
    return page("""<div class="card"><h2>Sinf qo'shish</h2><form method="post">
<div class="row"><select name="lang"><option value="uz">🇺🇿 O'zbek sinfi</option>
<option value="ru">🇷🇺 Rus sinfi</option></select></div>
<textarea name="names" placeholder="Bir qatorda bitta sinf yoki vergul bilan: 9-A, 9-B, 10-A" style="min-height:70px"></textarea>
<br><br><button>Qo'shish</button></form></div>
<div class="card"><h2>Sinflar</h2><table><tr><th>Sinf nomi va tili (tahrirlash)</th><th>O'quvchilar</th><th></th></tr>
{% for c in rows %}<tr><td><form method="post" action="/classes/edit/{{c.id}}" class="row" style="margin:0">
<input name="name" value="{{c.name}}" style="width:110px" required>
<select name="lang"><option value="uz" {{'selected' if c.lang=='uz'}}>🇺🇿 O'zbek</option>
<option value="ru" {{'selected' if c.lang=='ru'}}>🇷🇺 Rus</option></select><button class="gray">Saqlash</button></form></td>
<td>{{c.cnt}}</td>
<td><form method="post" action="/classes/del/{{c.id}}" onsubmit="return confirm('O‘chirilsinmi?')">
<button class="red">O'chirish</button></form></td></tr>{% endfor %}</table></div>""", rows=rows)


@app.route("/classes/edit/<int:i>", methods=["POST"])
@login_required
def class_edit(i):
    name, lang = request.form["name"].strip(), request.form["lang"]
    if name and lang in ("uz", "ru"):
        db.q("UPDATE classes SET name=?,lang=? WHERE id=?", (name, lang, i), commit=True)
        db.q("UPDATE students SET lang=? WHERE class_id=?", (lang, i), commit=True)
        db.q("UPDATE results SET class_name=? WHERE tg_id IN (SELECT tg_id FROM students WHERE class_id=?)",
             (name, i), commit=True)
        flash("✅ Sinf yangilandi")
    return redirect("/classes")


@app.route("/classes/del/<int:i>", methods=["POST"])
@login_required
def class_del(i):
    db.q("DELETE FROM classes WHERE id=?", (i,), commit=True)
    return redirect("/classes")


# ------------------------------------------------------------------ testlar
@app.route("/tests", methods=["GET", "POST"])
@login_required
def tests():
    if request.method == "POST":
        tid = db.q("INSERT INTO tests(title,lang,class_id,seconds) VALUES(?,?,?,?)",
                   (request.form["title"].strip(), request.form["lang"], int(request.form["class_id"]),
                    int(request.form["seconds"] or 0)), commit=True)
        flash("✅ Test yaratildi. Endi savollar qo'shing.")
        return redirect(f"/tests/{tid}")
    rows = db.q("SELECT t.*,(SELECT COUNT(*) FROM questions q WHERE q.test_id=t.id) qn,"
                "(SELECT name FROM classes c WHERE c.id=t.class_id) cname FROM tests t ORDER BY id DESC")
    cls = db.q("SELECT * FROM classes ORDER BY lang,name")
    return page("""<div class="card"><h2>Yangi test</h2><form method="post"><div class="row">
<input name="title" placeholder="Test nomi" required>
<select name="lang"><option value="uz">🇺🇿 O'zbek tilida</option><option value="ru">🇷🇺 Rus tilida</option></select>
<select name="class_id"><option value="0">Shu tildagi barcha sinflar</option>
{% for c in cls %}<option value="{{c.id}}">{{c.name}} ({{c.lang}})</option>{% endfor %}</select>
<input name="seconds" type="number" min="0" value="30" style="width:150px" title="Har savolga soniya (0 = cheksiz)">
<button>Yaratish</button></div><span class="muted">Vaqt: har bir savolga soniya (0 — cheklanmagan)</span></form></div>
<div class="card"><h2>Testlar</h2><div class="tblwrap"><table>
<tr><th>Nomi</th><th>Til</th><th>Sinf</th><th>Savollar</th><th>Vaqt</th><th>Holat</th><th></th></tr>
{% for t in rows %}<tr><td><a href="/tests/{{t.id}}">{{t.title}}</a></td><td>{{t.lang}}</td>
<td>{{t.cname or 'Hammasi'}}</td><td>{{t.qn}}</td><td>{{t.seconds}}s</td>
<td>{% if t.active %}<span class="ok">Faol</span>{% else %}<span class="bad">O'chiq</span>{% endif %}</td>
<td class="row"><form method="post" action="/tests/toggle/{{t.id}}"><button class="gray">
{{'O‘chirish' if t.active else 'Yoqish'}}</button></form>
<form method="post" action="/tests/del/{{t.id}}" onsubmit="return confirm('Test va savollari o‘chadi!')">
<button class="red">🗑</button></form></td></tr>{% endfor %}</table></div></div>""", rows=rows, cls=cls)


@app.route("/tests/toggle/<int:i>", methods=["POST"])
@login_required
def test_toggle(i):
    db.q("UPDATE tests SET active=1-active WHERE id=?", (i,), commit=True)
    return redirect("/tests")


@app.route("/tests/del/<int:i>", methods=["POST"])
@login_required
def test_del(i):
    db.q("DELETE FROM questions WHERE test_id=?", (i,), commit=True)
    db.q("DELETE FROM tests WHERE id=?", (i,), commit=True)
    return redirect("/tests")


def parse_correct(v, n):
    v = v.strip().upper()
    if v in ("A", "B", "C", "D"):
        idx = "ABCD".index(v)
    elif v.isdigit():
        idx = int(v) - 1
    else:
        return None
    return idx if 0 <= idx < n else None


@app.route("/tests/<int:i>", methods=["GET", "POST"])
@login_required
def test_detail(i):
    t = db.q("SELECT * FROM tests WHERE id=?", (i,), one=True)
    if not t:
        return redirect("/tests")
    if request.method == "POST":
        f = request.form
        if f.get("mode") == "bulk":
            added = 0
            for line in f["bulk"].splitlines():
                p = [x.strip() for x in line.split("|")]
                if len(p) < 4:
                    continue
                opts = p[1:-1][:4]
                corr = parse_correct(p[-1], len(opts))
                if corr is None or len(opts) < 2 or not p[0]:
                    continue
                opts += [""] * (4 - len(opts))
                db.q("INSERT INTO questions(test_id,text,a,b,c,d,correct) VALUES(?,?,?,?,?,?,?)",
                     (i, p[0], *opts, corr), commit=True)
                added += 1
            flash(f"✅ {added} ta savol qo'shildi")
        elif f.get("mode") == "edit":
            db.q("UPDATE tests SET title=?,seconds=? WHERE id=?",
                 (f["title"], int(f["seconds"] or 0), i), commit=True)
            flash("✅ Saqlandi")
        else:
            corr = int(f["correct"])
            opts = [f["a"].strip(), f["b"].strip(), f["c"].strip(), f["d"].strip()]
            db.q("INSERT INTO questions(test_id,text,a,b,c,d,correct) VALUES(?,?,?,?,?,?,?)",
                 (i, f["text"].strip(), *opts, corr), commit=True)
            flash("✅ Savol qo'shildi")
        return redirect(f"/tests/{i}")
    qs = db.q("SELECT * FROM questions WHERE test_id=? ORDER BY id", (i,))
    return page("""<div class="card"><h2>📝 {{t.title}}</h2><form method="post"><input type="hidden" name="mode" value="edit">
<div class="row"><input name="title" value="{{t.title}}"><input name="seconds" type="number" value="{{t.seconds}}"
style="width:120px"> soniya/savol <button>Saqlash</button></div></form></div>
<div class="card"><h2>Savol qo'shish</h2><form method="post"><textarea name="text" placeholder="Savol matni" required
style="min-height:70px"></textarea>
<div class="row"><input name="a" placeholder="A varianti" required><input name="b" placeholder="B varianti" required></div>
<div class="row"><input name="c" placeholder="C varianti (ixtiyoriy)"><input name="d" placeholder="D varianti (ixtiyoriy)"></div>
<div class="row">To'g'ri javob: <select name="correct"><option value="0">A</option><option value="1">B</option>
<option value="2">C</option><option value="3">D</option></select><button>Qo'shish</button></div></form></div>
<div class="card"><h2>Ko'p savolni birdan qo'shish</h2>
<p class="muted">Har qatorga bitta savol: <b>savol | A | B | C | D | to'g'ri harf</b><br>
Misol: <code>2+2 nechchi? | 3 | 4 | 5 | 6 | B</code></p>
<form method="post"><input type="hidden" name="mode" value="bulk"><textarea name="bulk"></textarea><br><br>
<button class="green">Hammasini qo'shish</button></form></div>
<div class="card"><h2>Savollar ({{qs|length}})</h2><table>{% for q in qs %}<tr><td>{{loop.index}}</td><td>
<b>{{q.text}}</b><br>
{% for k in 'abcd' %}{% if q[k] %}<span class="{{'ok' if loop.index0==q.correct else ''}}">
{{'ABCD'[loop.index0]}}) {{q[k]}}</span>&nbsp;&nbsp;{% endif %}{% endfor %}</td>
<td><form method="post" action="/questions/del/{{q.id}}"><button class="red">🗑</button></form></td></tr>{% endfor %}
</table></div>""", t=t, qs=qs)


@app.route("/questions/del/<int:i>", methods=["POST"])
@login_required
def question_del(i):
    q = db.q("SELECT test_id FROM questions WHERE id=?", (i,), one=True)
    db.q("DELETE FROM questions WHERE id=?", (i,), commit=True)
    return redirect(f"/tests/{q['test_id']}" if q else "/tests")


# ------------------------------------------------------------------ natijalar
def filtered_results():
    tid, cname, order = request.args.get("test", ""), request.args.get("cls", ""), request.args.get("order", "")
    sql, args = "SELECT * FROM results WHERE 1=1", []
    if tid:
        sql += " AND test_id=?"
        args.append(tid)
    if cname:
        sql += " AND class_name=?"
        args.append(cname)
    sql += " ORDER BY percent DESC, finished ASC" if order == "top" else " ORDER BY id DESC"
    return db.q(sql, args)


@app.route("/results")
@login_required
def results():
    rows = filtered_results()
    tests_ = db.q("SELECT id,title FROM tests ORDER BY id DESC")
    cls = db.q("SELECT DISTINCT name FROM classes ORDER BY name")
    return page("""<div class="card"><h2>📥 Natijalar</h2><form method="get" class="row">
<select name="test"><option value="">Barcha testlar</option>{% for t in tests_ %}
<option value="{{t.id}}" {{'selected' if request.args.get('test')==t.id|string}}>{{t.title}}</option>{% endfor %}</select>
<select name="cls"><option value="">Barcha sinflar</option>{% for c in cls %}
<option {{'selected' if request.args.get('cls')==c.name}}>{{c.name}}</option>{% endfor %}</select>
<select name="order"><option value="">Yangilari birinchi</option>
<option value="top" {{'selected' if request.args.get('order')=='top'}}>🏆 Reyting</option></select>
<button>Filtr</button><a class="btn green" href="/results.csv?{{request.query_string.decode()}}">⬇ Excel (CSV)</a></form>
<div class="tblwrap"><table><tr><th>#</th><th>F.I.Sh</th><th>Sinf</th><th>Til</th><th>Telegram</th><th>Test</th>
<th>Natija</th><th>Boshlandi</th><th>Tugadi</th><th></th></tr>
{% for r in rows %}<tr><td>{{loop.index}}</td><td>{{r.full_name}}</td><td>{{r.class_name}}</td><td>{{r.lang}}</td>
<td>{% if r.username %}@{{r.username}}{% endif %}<br><span class="muted">{{r.tg_name}} · {{r.tg_id}}</span></td>
<td>{{r.test_title}}</td>
<td>{% if r.done %}<b>{{r.score}}/{{r.total}}</b> ({{r.percent}}%){% else %}<span class="bad">tugallanmagan</span>{% endif %}</td>
<td>{{r.started}}</td><td>{{r.finished or ''}}</td>
<td class="row"><a class="btn gray" href="/results/{{r.id}}">Batafsil</a>
<form method="post" action="/results/del/{{r.id}}" onsubmit="return confirm('O‘chirilsa, o‘quvchi testni qayta topshira oladi')">
<button class="red">🗑</button></form></td></tr>{% endfor %}</table></div></div>""",
                tests_=tests_, cls=cls, rows=rows)


@app.route("/results.csv")
@login_required
def results_csv():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Familiya Ism", "Sinf", "Til", "Telegram username", "Telegram nomi", "Telegram ID",
                "Test", "To'g'ri", "Jami", "Foiz", "Boshlandi", "Tugadi", "Tugallandi"])
    for r in filtered_results():
        w.writerow([r["full_name"], r["class_name"], r["lang"], r["username"], r["tg_name"], r["tg_id"],
                    r["test_title"], r["score"], r["total"], r["percent"], r["started"], r["finished"],
                    "ha" if r["done"] else "yo'q"])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=natijalar.csv"})


@app.route("/results/<int:i>")
@login_required
def result_detail(i):
    r = db.q("SELECT * FROM results WHERE id=?", (i,), one=True)
    if not r:
        return redirect("/results")
    answers = json.loads(r["answers"] or "[]")
    return page("""<div class="card"><h2>{{r.full_name}} — {{r.class_name}}</h2>
<p>Test: <b>{{r.test_title}}</b> · Natija: <b>{{r.score}}/{{r.total}} ({{r.percent}}%)</b><br>
<span class="muted">Telegram: {% if r.username %}@{{r.username}}{% endif %} · {{r.tg_name}} · ID {{r.tg_id}}</span></p>
<table><tr><th>#</th><th>Savol</th><th>Javobi</th><th>To'g'ri javob</th></tr>
{% for a in answers %}<tr><td>{{loop.index}}</td><td>{{a.q}}</td>
<td class="{{'ok' if a.ok else 'bad'}}">{{a.chosen}}</td><td>{{a.correct}}</td></tr>{% endfor %}</table>
<br><a class="btn gray" href="/results">⬅ Orqaga</a></div>""", r=r, answers=answers)


@app.route("/results/del/<int:i>", methods=["POST"])
@login_required
def result_del(i):
    db.q("DELETE FROM results WHERE id=?", (i,), commit=True)
    return redirect("/results")


# ------------------------------------------------------------------ o'quvchilar
def student_rows():
    cid, text = request.args.get("cls", ""), request.args.get("q", "").strip()
    sql = ("SELECT s.*,(SELECT name FROM classes c WHERE c.id=s.class_id) cname,"
           "(SELECT COUNT(*) FROM results r WHERE r.tg_id=s.tg_id AND r.done=1) tests_done "
           "FROM students s WHERE 1=1")
    args = []
    if cid:
        sql += " AND s.class_id=?"
        args.append(cid)
    if text:
        sql += " AND s.full_name LIKE ?"
        args.append(f"%{text}%")
    return db.q(sql + " ORDER BY cname, s.full_name", args)


@app.route("/students")
@login_required
def students():
    rows = student_rows()
    cls = db.q("SELECT * FROM classes ORDER BY lang,name")
    return page("""<div class="card"><h2>👥 Maktab o'quvchilari ({{rows|length}})</h2>
<form method="get" class="row"><select name="cls"><option value="">Barcha sinflar</option>
{% for c in cls %}<option value="{{c.id}}" {{'selected' if request.args.get('cls')==c.id|string}}>{{c.name}} ({{c.lang}})</option>{% endfor %}</select>
<input name="q" placeholder="Ism bo'yicha qidirish" value="{{request.args.get('q','')}}"><button>Filtr</button>
<a class="btn green" href="/students.csv?{{request.query_string.decode()}}">⬇ Excel (CSV)</a></form>
<div class="tblwrap"><table><tr><th>#</th><th>F.I.Sh va sinf (tahrirlash)</th><th>Til</th><th>Telegram</th>
<th>Testlar</th><th>Ro'yxatdan o'tgan</th><th></th></tr>
{% for s in rows %}<tr><td>{{loop.index}}</td><td>
<form method="post" action="/students/edit/{{s.tg_id}}" class="row" style="margin:0">
<input name="full_name" value="{{s.full_name}}" style="width:190px" required>
<select name="class_id">{% for c in cls %}<option value="{{c.id}}" {{'selected' if c.id==s.class_id}}>{{c.name}} ({{c.lang}})</option>{% endfor %}</select>
<button class="gray">Saqlash</button></form></td><td>{{s.lang}}</td>
<td>{% if s.username %}@{{s.username}}{% endif %}<br><span class="muted">{{s.tg_name}} · {{s.tg_id}}</span></td>
<td>{{s.tests_done}}</td><td>{{s.registered}}</td>
<td><form method="post" action="/students/del/{{s.tg_id}}"
onsubmit="return confirm('O‘quvchi o‘chirilsinmi? (natijalari qoladi, u qayta ro‘yxatdan o‘ta oladi)')">
<button class="red">🗑</button></form></td></tr>{% endfor %}</table></div></div>""", rows=rows, cls=cls)


@app.route("/students.csv")
@login_required
def students_csv():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Familiya Ism", "Sinf", "Til", "Telegram username", "Telegram nomi", "Telegram ID",
                "Topshirgan testlar", "Ro'yxatdan o'tgan"])
    for r in student_rows():
        w.writerow([r["full_name"], r["cname"], r["lang"], r["username"], r["tg_name"], r["tg_id"],
                    r["tests_done"], r["registered"]])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=oquvchilar.csv"})


@app.route("/students/edit/<int:i>", methods=["POST"])
@login_required
def student_edit(i):
    name = request.form["full_name"].strip()
    c = db.q("SELECT * FROM classes WHERE id=?", (request.form["class_id"],), one=True)
    if name and c:
        db.q("UPDATE students SET full_name=?,class_id=?,lang=? WHERE tg_id=?",
             (name, c["id"], c["lang"], i), commit=True)
        flash("✅ O'quvchi ma'lumoti saqlandi")
    return redirect(request.referrer or "/students")


@app.route("/students/del/<int:i>", methods=["POST"])
@login_required
def student_del(i):
    db.q("DELETE FROM students WHERE tg_id=?", (i,), commit=True)
    return redirect("/students")


# ------------------------------------------------------------------ o'quvchi xabarlari
import ssl
import urllib.error

try:
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _CTX = ssl.create_default_context()


def explain(err):
    e = err.lower()
    if "blocked by the user" in e:
        return "o'quvchi botni bloklagan"
    if "chat not found" in e:
        return "o'quvchi botni hech ochmagan yoki ID noto'g'ri (chat topilmadi)"
    if "unauthorized" in e or "not found" in e and "chat" not in e:
        return "BOT_TOKEN noto'g'ri yoki eskirgan (" + err + ")"
    return err


def tg_send(chat_id, text):
    """(ok, xato_matni) qaytaradi. Avval ishlab turgan botning o'zi orqali yuboradi."""
    try:
        import asyncio
        import bot as botmod
        if botmod.BOT is not None and botmod.LOOP is not None:
            fut = asyncio.run_coroutine_threadsafe(botmod.BOT.send_message(chat_id, text), botmod.LOOP)
            try:
                fut.result(timeout=25)
                return True, ""
            except Exception as e:
                msg = str(e).strip()
                if not msg:
                    return False, "vaqt tugadi: Telegramga ulanish juda sekin"
                return False, explain(f"{type(e).__name__}: {msg}")
    except ImportError:
        pass
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        return False, "BOT_TOKEN panel jarayonida topilmadi"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage",
                               data, timeout=15, context=_CTX)
        return True, ""
    except urllib.error.HTTPError as e:
        try:
            desc = json.loads(e.read().decode("utf-8"))["description"]
        except Exception:
            desc = f"HTTP {e.code}"
        return False, explain(desc)
    except Exception as e:
        return False, f"internetga ulanib bo'lmadi: {type(e).__name__}: {e}"


@app.route("/messages")
@login_required
def messages():
    rows = db.q("SELECT * FROM messages ORDER BY (reply IS NULL) DESC, id DESC LIMIT 200")
    return page("""<div class="card"><h2>✉️ O'quvchilardan kelgan xabarlar</h2>
{% if not rows %}<p class="muted">Hozircha xabar yo'q.</p>{% endif %}
{% for m in rows %}<div class="card" style="border-left:5px solid {{'#1e8e5a' if m.reply else '#c0392b'}}">
<b>{{m.full_name}}</b> · {{m.class_name}} · {% if m.username %}@{{m.username}} · {% endif %}
<span class="muted">{{m.created}}</span>
<p style="white-space:pre-wrap">{{m.text}}</p>
{% if m.reply %}<p class="ok" style="white-space:pre-wrap">↳ Javobingiz ({{m.replied_at}}): {{m.reply}}</p>{% endif %}
<form method="post" action="/messages/reply/{{m.id}}"><textarea name="text" style="min-height:60px"
placeholder="{{'Yana javob yozish…' if m.reply else 'Javob yozing…'}}" required></textarea><br><br>
<div class="row"><button>Javob yuborish</button></div></form>
<form method="post" action="/messages/del/{{m.id}}" onsubmit="return confirm('O‘chirilsinmi?')">
<button class="red">🗑 O'chirish</button></form></div>{% endfor %}</div>""", rows=rows)


@app.route("/messages/reply/<int:i>", methods=["POST"])
@login_required
def message_reply(i):
    from datetime import datetime
    m = db.q("SELECT * FROM messages WHERE id=?", (i,), one=True)
    text = request.form["text"].strip()
    if m and text:
        head = "✉️ Admin javobi:" if m["lang"] == "uz" else "✉️ Ответ администратора:"
        ok, err = tg_send(m["tg_id"], f"{head}\n\n{text}")
        if ok:
            db.q("UPDATE messages SET reply=?,replied_at=? WHERE id=?",
                 (text, datetime.now().strftime("%Y-%m-%d %H:%M"), i), commit=True)
            flash("✅ Javob o'quvchiga yuborildi")
        else:
            flash("❌ Yuborib bo'lmadi: " + err)
    return redirect("/messages")


@app.route("/messages/del/<int:i>", methods=["POST"])
@login_required
def message_del(i):
    db.q("DELETE FROM messages WHERE id=?", (i,), commit=True)
    return redirect("/messages")


# ------------------------------------------------------------------ xabar yuborish
@app.route("/broadcast", methods=["GET", "POST"])
@login_required
def broadcast():
    if request.method == "POST":
        lang = request.form["lang"]
        sql = "SELECT tg_id FROM students" + (" WHERE lang=?" if lang else "")
        ids = [r["tg_id"] for r in db.q(sql, (lang,) if lang else ())]
        ok, first_err = 0, ""
        for uid in ids:
            sent, err = tg_send(uid, request.form["text"])
            if sent:
                ok += 1
            elif not first_err:
                first_err = err
            time.sleep(0.05)
        flash(f"✅ {ok}/{len(ids)} ta o'quvchiga yuborildi" + (f" · birinchi xato: {first_err}" if first_err else ""))
        return redirect("/broadcast")
    return page("""<div class="card"><h2>📣 O'quvchilarga xabar yuborish</h2><form method="post">
<div class="row"><select name="lang"><option value="">Hammaga</option><option value="uz">Faqat o'zbek sinflari</option>
<option value="ru">Faqat rus sinflari</option></select></div>
<textarea name="text" required placeholder="Xabar matni (masalan: Ertaga soat 10:00 da test bo'ladi)"></textarea><br><br>
<button>Yuborish</button></form></div>""")


# ------------------------------------------------------------------ sozlamalar
@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        f = request.form
        act = f["act"]
        if act == "student_pw" and f["pw"].strip():
            db.set_setting("student_password", f["pw"].strip())
            flash("✅ O'quvchilar paroli o'zgartirildi")
        elif act == "options":
            db.set_setting("show_result", "1" if f.get("show_result") else "0")
            db.set_setting("shuffle", "1" if f.get("shuffle") else "0")
            flash("✅ Sozlamalar saqlandi")
        elif act == "admin":
            if not check_password_hash(db.get_setting("admin_hash"), f["current"]):
                flash("❌ Joriy parol noto'g'ri")
            elif f["login"].strip() and f["new"].strip():
                db.set_setting("admin_login", f["login"].strip())
                db.set_setting("admin_hash", generate_password_hash(f["new"].strip()))
                flash("✅ Admin login va paroli o'zgartirildi")
        return redirect("/settings")
    return page("""<div class="card"><h2>🔑 O'quvchilar uchun umumiy parol</h2><form method="post" class="row">
<input type="hidden" name="act" value="student_pw"><input name="pw" value="{{pw}}" required><button>Saqlash</button></form>
<span class="muted">Hozirgi parol ko'rinib turibdi. Yangi parol faqat yangi kirayotganlarga ta'sir qiladi.</span></div>
<div class="card"><h2>⚙️ Test sozlamalari</h2><form method="post"><input type="hidden" name="act" value="options">
<p><label><input type="checkbox" name="show_result" {{'checked' if show_result=='1'}}>
Test tugagach natijani o'quvchining o'ziga ko'rsatish</label></p>
<p><label><input type="checkbox" name="shuffle" {{'checked' if shuffle=='1'}}>
Savollar va javob variantlarini har o'quvchiga aralashtirib berish</label></p><button>Saqlash</button></form></div>
<div class="card"><h2>🛡 Admin login va paroli</h2><form method="post"><input type="hidden" name="act" value="admin">
<div class="row"><input name="login" value="{{login}}" placeholder="Yangi login" required>
<input name="current" type="password" placeholder="Joriy parol" required>
<input name="new" type="password" placeholder="Yangi parol" required><button>O'zgartirish</button></div></form></div>""",
                pw=db.get_setting("student_password"), show_result=db.get_setting("show_result"),
                shuffle=db.get_setting("shuffle"), login=db.get_setting("admin_login"))