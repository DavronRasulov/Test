import asyncio
import functools
import json
import logging
import os
import random
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, ChatMemberUpdated,
                           InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, Message, ReplyKeyboardMarkup,
                           ReplyKeyboardRemove)

import db
from utils import valid_name

TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
# Admin Telegram ID lari (vergul bilan ajratilgan): "123456789,987654321"
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: set[int] = set()
if ADMIN_IDS_RAW.strip():
    for _a in ADMIN_IDS_RAW.split(","):
        try:
            ADMIN_IDS.add(int(_a.strip()))
        except ValueError:
            pass

LET = "ABCD"
router = Router()
SESS = {}          # tg_id -> test sessiyasi (faol)
PAUSED_SESS = {}   # tg_id -> to'xtatilgan sessiya (bot block qilinganda saqlanadi)
ADMIN_SESS = {}    # tg_id -> admin panel sessiyasi holati


# ================================================================
# FSM States
# ================================================================
class Reg(StatesGroup):
    password = State()
    name = State()
    cls = State()


class Contact(StatesGroup):
    msg = State()


class AdminSt(StatesGroup):
    # Sinflar
    add_class = State()
    # Testlar
    add_test_title = State()
    add_test_seconds = State()
    # Savol qo'shish
    add_q_text = State()
    add_q_a = State()
    add_q_b = State()
    add_q_c = State()
    add_q_d = State()
    add_q_correct = State()
    # Broadcast
    broadcast_text = State()
    broadcast_confirm = State()
    # Parol o'zgartirish
    change_student_pass = State()
    change_admin_pass = State()
    # Xabarga javob
    reply_msg = State()


T = {
    "uz": dict(
        ask_pass="🔑 Parolni kiriting:",
        bad_pass="❌ Parol noto'g'ri. Qayta kiriting:",
        ask_name="✍️ Ism va familiyangizni yozing (masalan: Ali Valiyev):",
        ask_class="🏫 Sinfingizni tanlang:",
        no_class="Hozircha sinflar qo'shilmagan. Keyinroq /start bosing.",
        menu="📋 Sizga mavjud testlar:",
        no_tests="Hozircha sizga test yo'q.",
        need_reg="Avval /start bosib ro'yxatdan o'ting.",
        taken="Siz bu testni topshirgansiz.",
        busy="⚠️ Sizda test davom etmoqda.",
        rules=("📝 <b>{title}</b>\n\n❓ Savollar: {n}\n⏱ Har savolga: {sec}\n\n"
               "<b>Qoidalar:</b>\n• Test faqat 1 marta topshiriladi\n"
               "• Orqaga qaytib bo'lmaydi\n• Savollarni nusxalash, forward qilish mumkin emas\n"
               "• Vaqt tugasa keyingi savolga o'tadi\n\nTayyormisiz?"),
        sec="soniya", nolimit="cheklanmagan", go="▶️ Boshlash", back="⬅️ Orqaga",
        finish="🏁 Test yakunlandi!\n✅ To'g'ri javoblar: {s}/{t}\n📊 Natija: {p}%",
        finish_hidden="🏁 Test yakunlandi! Javoblaringiz o'qituvchiga yuborildi.",
        empty="Bu testda hali savollar yo'q.",
        stopped="Test davom etayotganda boshqa buyruq ishlamaydi.",
        bad_name=("❌ Ismingizni to'g'ri kiriting!\n\nIsm va familiyangizni faqat harflar bilan, "
                  "ikkita so'z qilib yozing.\nMasalan: Ali Valiyev"),
        btn_test="📝 Testni boshlash",
        btn_admin="✉️ Adminga yozish",
        btn_cancel="❌ Bekor qilish",
        btn_my_results="📊 Natijalarim",
        btn_rating="🏆 Reyting",
        btn_help="❓ Yordam",
        btn_profile="👤 Profilim",
        welcome="✅ Ro'yxatdan o'tdingiz, {name}!\n🏫 Sinf: {cls}\n\nQuyidagi tugmalardan foydalaning 👇",
        back_welcome="👋 Xush kelibsiz, {name}! ({cls})\nQuyidagi tugmalardan foydalaning 👇",
        ask_msg="✉️ Adminga yubormoqchi bo'lgan xabaringizni yozing:",
        msg_sent="✅ Xabaringiz adminga yuborildi. Javob kelsa, shu yerda ko'rasiz.",
        msg_cancel="Bekor qilindi.",
        my_results_empty="Hali birorta test topshirmadingiz.",
        my_results_header="📊 <b>Sizning natijalaringiz:</b>\n\n",
        rating_header="🏆 <b>Reyting (top 10):</b>\n\n",
        rating_empty="Hali natijalar yo'q.",
        help_text=(
            "❓ <b>Yordam</b>\n\n"
            "📝 <b>Testni boshlash</b> — mavjud testlar ro'yxatini ko'rish\n"
            "📊 <b>Natijalarim</b> — o'z natijalaringizni ko'rish\n"
            "🏆 <b>Reyting</b> — eng yaxshi natijalar ro'yxati\n"
            "✉️ <b>Adminga yozish</b> — o'qituvchiga xabar yuborish\n"
            "👤 <b>Profilim</b> — shaxsiy ma'lumotlaringiz\n\n"
            "📌 Test paytida:\n"
            "• Har bir savolga vaqt ajratilgan\n"
            "• Savollarni nusxalash mumkin emas\n"
            "• Test 1 marta topshiriladi"
        ),
        profile_text=(
            "👤 <b>Profil</b>\n\n"
            "📛 Ism: {name}\n"
            "🏫 Sinf: {cls}\n"
            "🌐 Til: {lang}\n"
            "📅 Ro'yxatdan o'tgan: {reg}\n"
            "📊 Topshirilgan testlar: {tests}"
        ),
        admin_panel_btn="🔧 Admin panel",
        # To'xtatilgan test
        test_paused_blocked=(
            "⚠️ <b>Test to'xtatildi!</b>\n\n"
            "Siz Telegramdan chiqib AI ishlatdingiz yoki botni blokladingiz.\n"
            "Bu harakatlar taqiqlangan.\n\n"
            "📌 Testingiz saqlab qo'yildi.\n"
            "Davom ettirish uchun quyidagi tugmani bosing 👇"
        ),
        btn_continue_test="▶️ Testni davom ettirish",
        continue_not_found="Sizda to'xtatilgan test topilmadi.",
        continue_confirm=(
            "📋 <b>To'xtatilgan test:</b>\n\n"
            "📝 {title}\n"
            "❓ Javoblangan: {done}/{total}\n\n"
            "Davom ettirilsinmi?"
        ),
        btn_yes_continue="✅ Ha, davom ettirish",
        btn_no_discard="❌ Yo'q, bekor qilish",
        discard_done="🗑 Test bekor qilindi.",
    ),
    "ru": dict(
        ask_pass="🔑 Введите пароль:",
        bad_pass="❌ Неверный пароль. Попробуйте ещё раз:",
        ask_name="✍️ Напишите имя и фамилию (например: Иван Петров):",
        ask_class="🏫 Выберите свой класс:",
        no_class="Классы пока не добавлены. Нажмите /start позже.",
        menu="📋 Доступные вам тесты:",
        no_tests="Пока тестов для вас нет.",
        need_reg="Сначала зарегистрируйтесь: /start.",
        taken="Вы уже проходили этот тест.",
        busy="⚠️ У вас уже идёт тест.",
        rules=("📝 <b>{title}</b>\n\n❓ Вопросов: {n}\n⏱ На каждый вопрос: {sec}\n\n"
               "<b>Правила:</b>\n• Тест сдаётся только 1 раз\n"
               "• Назад вернуться нельзя\n• Копировать и пересылать вопросы нельзя\n"
               "• По истечении времени бот переходит к следующему вопросу\n\nГотовы?"),
        sec="сек.", nolimit="без ограничения", go="▶️ Начать", back="⬅️ Назад",
        finish="🏁 Тест завершён!\n✅ Правильных ответов: {s}/{t}\n📊 Результат: {p}%",
        finish_hidden="🏁 Тест завершён! Ваши ответы отправлены учителю.",
        empty="В этом тесте пока нет вопросов.",
        stopped="Пока идёт тест, другие команды не работают.",
        bad_name=("❌ Введите имя правильно!\n\nНапишите имя и фамилию только буквами, "
                  "двумя словами.\nНапример: Иван Петров"),
        btn_test="📝 Начать тест",
        btn_admin="✉️ Написать админу",
        btn_cancel="❌ Отмена",
        btn_my_results="📊 Мои результаты",
        btn_rating="🏆 Рейтинг",
        btn_help="❓ Помощь",
        btn_profile="👤 Мой профиль",
        welcome="✅ Вы зарегистрированы, {name}!\n🏫 Класс: {cls}\n\nПользуйтесь кнопками ниже 👇",
        back_welcome="👋 Добро пожаловать, {name}! ({cls})\nПользуйтесь кнопками ниже 👇",
        ask_msg="✉️ Напишите сообщение для админа:",
        msg_sent="✅ Сообщение отправлено админу. Ответ придёт сюда.",
        msg_cancel="Отменено.",
        my_results_empty="Вы ещё не сдавали ни одного теста.",
        my_results_header="📊 <b>Ваши результаты:</b>\n\n",
        rating_header="🏆 <b>Рейтинг (топ 10):</b>\n\n",
        rating_empty="Результатов пока нет.",
        help_text=(
            "❓ <b>Помощь</b>\n\n"
            "📝 <b>Начать тест</b> — список доступных тестов\n"
            "📊 <b>Мои результаты</b> — посмотреть свои результаты\n"
            "🏆 <b>Рейтинг</b> — список лучших результатов\n"
            "✉️ <b>Написать админу</b> — отправить сообщение учителю\n"
            "👤 <b>Мой профиль</b> — личные данные\n\n"
            "📌 Во время теста:\n"
            "• На каждый вопрос отводится время\n"
            "• Копировать вопросы нельзя\n"
            "• Тест сдаётся 1 раз"
        ),
        profile_text=(
            "👤 <b>Профиль</b>\n\n"
            "📛 Имя: {name}\n"
            "🏫 Класс: {cls}\n"
            "🌐 Язык: {lang}\n"
            "📅 Дата регистрации: {reg}\n"
            "📊 Сдано тестов: {tests}"
        ),
        admin_panel_btn="🔧 Admin panel",
        # Приостановленный тест
        test_paused_blocked=(
            "⚠️ <b>Тест приостановлен!</b>\n\n"
            "Вы вышли из Telegram или заблокировали бота.\n"
            "Эти действия запрещены во время теста.\n\n"
            "📌 Ваш тест сохранён.\n"
            "Нажмите кнопку ниже, чтобы продолжить 👇"
        ),
        btn_continue_test="▶️ Продолжить тест",
        continue_not_found="У вас нет приостановленного теста.",
        continue_confirm=(
            "📋 <b>Приостановленный тест:</b>\n\n"
            "📝 {title}\n"
            "❓ Отвечено: {done}/{total}\n\n"
            "Продолжить?"
        ),
        btn_yes_continue="✅ Да, продолжить",
        btn_no_discard="❌ Нет, отменить",
        discard_done="🗑 Тест отменён.",
    ),
}

# ================================================================
# Klaviaturalar
# ================================================================

def main_kb(L, is_admin=False, has_paused=False):
    """Asosiy reply klaviatura — o'quvchilar uchun."""
    row1 = [KeyboardButton(text=T[L]["btn_test"]), KeyboardButton(text=T[L]["btn_admin"])]
    row2 = [KeyboardButton(text=T[L]["btn_my_results"]), KeyboardButton(text=T[L]["btn_rating"])]
    row3 = [KeyboardButton(text=T[L]["btn_profile"]), KeyboardButton(text=T[L]["btn_help"])]
    keyboard = [row1, row2, row3]
    if has_paused:
        keyboard.insert(0, [KeyboardButton(text=T[L]["btn_continue_test"])])
    if is_admin:
        keyboard.append([KeyboardButton(text=T[L]["admin_panel_btn"])])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def admin_main_kb():
    """Telegram admin panel bosh menyusi."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm:stats"),
         InlineKeyboardButton(text="👥 O'quvchilar", callback_data="adm:students")],
        [InlineKeyboardButton(text="🏫 Sinflar", callback_data="adm:classes"),
         InlineKeyboardButton(text="📝 Testlar", callback_data="adm:tests")],
        [InlineKeyboardButton(text="✉️ Xabarlar", callback_data="adm:messages"),
         InlineKeyboardButton(text="📢 Broadcast", callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="⚙️ Sozlamalar", callback_data="adm:settings"),
         InlineKeyboardButton(text="📈 Natijalar", callback_data="adm:results")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="adm:close")],
    ])


def back_to_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="adm:main")
    ]])


# ================================================================
# Yordamchi funksiyalar
# ================================================================

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def student(uid):
    return db.q("SELECT * FROM students WHERE tg_id=?", (uid,), one=True)


def is_admin(uid: int) -> bool:
    """Foydalanuvchi admin ekanini tekshiradi."""
    if ADMIN_IDS and uid in ADMIN_IDS:
        return True
    # ADMIN_CHAT_ID ham admin sifatida qabul qilinadi
    if ADMIN_CHAT_ID and str(uid) == str(ADMIN_CHAT_ID):
        return True
    # DB dagi admin_ids ro'yxati
    ids_str = db.get_setting("admin_ids", "")
    if ids_str:
        for aid in ids_str.split(","):
            try:
                if int(aid.strip()) == uid:
                    return True
            except ValueError:
                pass
    return False


def lang_of(uid):
    s = student(uid)
    return s["lang"] if s else "uz"


def get_test_for(uid, tid):
    s = student(uid)
    if not s:
        return None, None
    t = db.q("SELECT * FROM tests WHERE id=? AND active=1 AND lang=? AND (class_id=0 OR class_id=?)",
             (tid, s["lang"], s["class_id"]), one=True)
    return s, t


# ================================================================
# START va ro'yxatdan o'tish
# ================================================================

@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    if m.from_user.id in SESS:
        return await m.answer(T["uz"]["busy"] + " / " + T["ru"]["busy"])
    await state.clear()
    uid = m.from_user.id
    s = student(uid)
    adm = is_admin(uid)
    has_paused = uid in PAUSED_SESS
    if s:
        cls = db.q("SELECT name FROM classes WHERE id=?", (s["class_id"],), one=True)
        if has_paused:
            ps = PAUSED_SESS[uid]
            L = s["lang"]
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=T[L]["btn_yes_continue"], callback_data="continue:yes")],
                [InlineKeyboardButton(text=T[L]["btn_no_discard"], callback_data="continue:no")],
            ])
            return await m.answer(
                T[L]["continue_confirm"].format(
                    title=ps["test_title"],
                    done=ps["i"],
                    total=ps["total"]
                ),
                reply_markup=kb, parse_mode="HTML"
            )
        return await m.answer(
            T[s["lang"]]["back_welcome"].format(name=s["full_name"], cls=cls["name"] if cls else "?"),
            reply_markup=main_kb(s["lang"], is_admin=adm, has_paused=has_paused))
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang:uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
    ]])
    if adm:
        await m.answer("🔧 Admin sifatida kirgansiz. Admin panel:", reply_markup=admin_main_kb())
    await m.answer("Tilni tanlang / Выберите язык:", reply_markup=kb)


@router.message(Command("admin"))
async def cmd_admin(m: Message, state: FSMContext):
    """Admin panelni ochish buyrug'i."""
    if not is_admin(m.from_user.id):
        return await m.answer("⛔ Sizda admin huquqi yo'q.")
    await state.clear()
    await m.answer("🔧 <b>Admin panel</b>", reply_markup=admin_main_kb(), parse_mode="HTML")


@router.callback_query(F.data.startswith("lang:"))
async def pick_lang(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id in SESS:
        return await cb.answer()
    lang = cb.data.split(":")[1]
    await state.update_data(lang=lang)
    await state.set_state(Reg.password)
    await cb.message.edit_text(T[lang]["ask_pass"])
    await cb.answer()


@router.message(Reg.password, F.text)
async def got_password(m: Message, state: FSMContext):
    L = (await state.get_data())["lang"]
    try:
        await m.delete()
    except Exception:
        pass
    if m.text.strip() != db.get_setting("student_password"):
        return await m.answer(T[L]["bad_pass"])
    await state.set_state(Reg.name)
    await m.answer(T[L]["ask_name"])


@router.message(Reg.name, F.text)
async def got_name(m: Message, state: FSMContext):
    L = (await state.get_data())["lang"]
    name = valid_name(m.text)
    if not name:
        return await m.answer(T[L]["bad_name"])
    classes = db.q("SELECT * FROM classes WHERE lang=? ORDER BY name", (L,))
    if not classes:
        await state.clear()
        return await m.answer(T[L]["no_class"])
    await state.update_data(name=name)
    rows, row = [], []
    for c in classes:
        row.append(InlineKeyboardButton(text=c["name"], callback_data=f"c:{c['id']}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    await state.set_state(Reg.cls)
    await m.answer(T[L]["ask_class"], reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(Reg.cls, F.data.startswith("c:"))
async def got_class(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    L = d["lang"]
    cid = int(cb.data.split(":")[1])
    u = cb.from_user
    db.q("INSERT OR REPLACE INTO students(tg_id,username,tg_name,full_name,class_id,lang,registered) "
         "VALUES(?,?,?,?,?,?,?)",
         (u.id, u.username or "", u.full_name, d["name"], cid, L, now()), commit=True)
    cls = db.q("SELECT name FROM classes WHERE id=?", (cid,), one=True)
    adm = is_admin(u.id)
    await state.clear()
    await cb.message.delete()
    await cb.message.answer(T[L]["welcome"].format(name=d["name"], cls=cls["name"] if cls else "?"),
                            reply_markup=main_kb(L, is_admin=adm, has_paused=u.id in PAUSED_SESS))
    await cb.answer()


# ================================================================
# Testlar ro'yxati
# ================================================================

async def show_tests(target: Message, uid: int):
    s = student(uid)
    if not s:
        return await target.answer(T["uz"]["need_reg"] + "\n" + T["ru"]["need_reg"])
    L = s["lang"]
    tests = db.q("SELECT * FROM tests WHERE active=1 AND lang=? AND (class_id=0 OR class_id=?) ORDER BY id DESC",
                 (L, s["class_id"]))
    if not tests:
        return await target.answer(T[L]["no_tests"])
    taken = {r["test_id"] for r in db.q("SELECT test_id FROM results WHERE tg_id=?", (uid,))}
    rows = [[InlineKeyboardButton(
        text=t["title"] + (" ✔️" if t["id"] in taken else ""),
        callback_data=f"t:{t['id']}")] for t in tests]
    await target.answer(T[L]["menu"], reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(Command("tests", "menu"))
async def cmd_tests(m: Message):
    if m.from_user.id in SESS:
        return await m.answer(T[lang_of(m.from_user.id)]["stopped"])
    await show_tests(m, m.from_user.id)


ALL_TEST_BTNS = {T["uz"]["btn_test"], T["ru"]["btn_test"]}
ALL_ADMIN_BTNS = {T["uz"]["btn_admin"], T["ru"]["btn_admin"]}
ALL_CANCEL_BTNS = {T["uz"]["btn_cancel"], T["ru"]["btn_cancel"]}
ALL_RESULTS_BTNS = {T["uz"]["btn_my_results"], T["ru"]["btn_my_results"]}
ALL_RATING_BTNS = {T["uz"]["btn_rating"], T["ru"]["btn_rating"]}
ALL_HELP_BTNS = {T["uz"]["btn_help"], T["ru"]["btn_help"]}
ALL_PROFILE_BTNS = {T["uz"]["btn_profile"], T["ru"]["btn_profile"]}
ALL_ADMIN_PANEL_BTNS = {T["uz"]["admin_panel_btn"], T["ru"]["admin_panel_btn"]}
ALL_CONTINUE_BTNS = {T["uz"]["btn_continue_test"], T["ru"]["btn_continue_test"]}


# ================================================================
# Yangi o'quvchi tugmalari handlerlari
# ================================================================

@router.message(F.text.in_(ALL_TEST_BTNS))
async def btn_test(m: Message):
    uid = m.from_user.id
    if uid in SESS:
        try:
            await m.delete()
        except Exception:
            pass
        return
    await show_tests(m, uid)


@router.message(F.text.in_(ALL_ADMIN_BTNS))
async def btn_admin(m: Message, state: FSMContext):
    uid = m.from_user.id
    if uid in SESS:
        try:
            await m.delete()
        except Exception:
            pass
        return
    s = student(uid)
    if not s:
        return await m.answer(T["uz"]["need_reg"] + "\n" + T["ru"]["need_reg"])
    L = s["lang"]
    await state.set_state(Contact.msg)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=T[L]["btn_cancel"])]], resize_keyboard=True)
    await m.answer(T[L]["ask_msg"], reply_markup=kb)


@router.message(F.text.in_(ALL_RESULTS_BTNS))
async def btn_my_results(m: Message):
    uid = m.from_user.id
    if uid in SESS:
        try:
            await m.delete()
        except Exception:
            pass
        return
    s = student(uid)
    if not s:
        return await m.answer(T["uz"]["need_reg"])
    L = s["lang"]
    results = db.q(
        "SELECT test_title, score, total, percent, finished FROM results "
        "WHERE tg_id=? AND done=1 ORDER BY finished DESC LIMIT 20",
        (uid,)
    )
    if not results:
        return await m.answer(T[L]["my_results_empty"])
    lines = [T[L]["my_results_header"]]
    for i, r in enumerate(results, 1):
        emoji = "✅" if r["percent"] >= 60 else "❌"
        lines.append(
            f"{i}. {emoji} <b>{r['test_title']}</b>\n"
            f"   {r['score']}/{r['total']} — {r['percent']}%\n"
            f"   📅 {r['finished'] or '—'}\n"
        )
    await m.answer("".join(lines), parse_mode="HTML")


@router.message(F.text.in_(ALL_RATING_BTNS))
async def btn_rating(m: Message):
    uid = m.from_user.id
    if uid in SESS:
        try:
            await m.delete()
        except Exception:
            pass
        return
    s = student(uid)
    if not s:
        return await m.answer(T["uz"]["need_reg"])
    L = s["lang"]
    # Har bir o'quvchining eng yaxshi natijasi bo'yicha reyting
    top = db.q(
        "SELECT full_name, class_name, MAX(percent) as best_pct, COUNT(*) as cnt "
        "FROM results WHERE done=1 AND lang=? "
        "GROUP BY tg_id ORDER BY best_pct DESC LIMIT 10",
        (L,)
    )
    if not top:
        return await m.answer(T[L]["rating_empty"])
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    lines = [T[L]["rating_header"]]
    for i, r in enumerate(top):
        lines.append(
            f"{medals[i]} {i+1}. <b>{r['full_name']}</b> ({r['class_name']})\n"
            f"   📊 {r['best_pct']}% | 📝 {r['cnt']} test\n"
        )
    await m.answer("".join(lines), parse_mode="HTML")


@router.message(F.text.in_(ALL_HELP_BTNS))
async def btn_help(m: Message):
    uid = m.from_user.id
    if uid in SESS:
        try:
            await m.delete()
        except Exception:
            pass
        return
    s = student(uid)
    L = s["lang"] if s else "uz"
    await m.answer(T[L]["help_text"], parse_mode="HTML")


@router.message(F.text.in_(ALL_PROFILE_BTNS))
async def btn_profile(m: Message):
    uid = m.from_user.id
    if uid in SESS:
        try:
            await m.delete()
        except Exception:
            pass
        return
    s = student(uid)
    if not s:
        return await m.answer(T["uz"]["need_reg"])
    L = s["lang"]
    cls = db.q("SELECT name FROM classes WHERE id=?", (s["class_id"],), one=True)
    tests_count = db.q("SELECT COUNT(*) c FROM results WHERE tg_id=? AND done=1", (uid,), one=True)["c"]
    lang_name = "O'zbek" if L == "uz" else "Русский"
    await m.answer(
        T[L]["profile_text"].format(
            name=s["full_name"],
            cls=cls["name"] if cls else "?",
            lang=lang_name,
            reg=s["registered"] or "—",
            tests=tests_count,
        ),
        parse_mode="HTML"
    )


@router.message(F.text.in_(ALL_ADMIN_PANEL_BTNS))
async def btn_admin_panel(m: Message, state: FSMContext):
    uid = m.from_user.id
    if uid in SESS:
        try:
            await m.delete()
        except Exception:
            pass
        return
    if not is_admin(uid):
        return await m.answer("⛔ Sizda admin huquqi yo'q.")
    await state.clear()
    await m.answer("🔧 <b>Admin panel</b>", reply_markup=admin_main_kb(), parse_mode="HTML")


@router.message(Contact.msg, F.text)
async def contact_got(m: Message, state: FSMContext, bot: Bot):
    uid = m.from_user.id
    s = student(uid)
    L = s["lang"] if s else "uz"
    txt = m.text.strip()
    if txt in ALL_CANCEL_BTNS:
        await state.clear()
        return await m.answer(T[L]["msg_cancel"], reply_markup=main_kb(L, is_admin=is_admin(uid), has_paused=uid in PAUSED_SESS))
    if txt in ALL_TEST_BTNS:
        await state.clear()
        await m.answer(T[L]["msg_cancel"], reply_markup=main_kb(L, is_admin=is_admin(uid), has_paused=uid in PAUSED_SESS))
        return await show_tests(m, uid)
    if txt in ALL_ADMIN_BTNS:
        return await m.answer(T[L]["ask_msg"])
    cls = db.q("SELECT name FROM classes WHERE id=?", (s["class_id"],), one=True)
    cname = cls["name"] if cls else "?"
    db.q("INSERT INTO messages(tg_id,full_name,class_name,username,lang,text,created) VALUES(?,?,?,?,?,?,?)",
         (uid, s["full_name"], cname, s["username"], L, txt[:3000], now()), commit=True)
    await state.clear()
    await m.answer(T[L]["msg_sent"], reply_markup=main_kb(L, is_admin=is_admin(uid), has_paused=uid in PAUSED_SESS))
    if ADMIN_CHAT_ID:
        try:
            who = f"@{s['username']}" if s["username"] else s["tg_name"]
            await bot.send_message(ADMIN_CHAT_ID, f"✉️ {s['full_name']} ({cname}) {who}:\n\n{txt}")
        except Exception:
            pass


# ================================================================
# Test info va test jarayoni
# ================================================================

@router.callback_query(F.data.startswith("t:"))
async def test_info(cb: CallbackQuery):
    uid = cb.from_user.id
    L = lang_of(uid)
    if uid in SESS:
        return await cb.answer(T[L]["busy"], show_alert=True)
    s, t = get_test_for(uid, int(cb.data.split(":")[1]))
    if not t:
        return await cb.answer()
    if db.q("SELECT 1 FROM results WHERE tg_id=? AND test_id=?", (uid, t["id"]), one=True):
        return await cb.answer(T[L]["taken"], show_alert=True)
    n = db.q("SELECT COUNT(*) c FROM questions WHERE test_id=?", (t["id"],), one=True)["c"]
    if n == 0:
        return await cb.answer(T[L]["empty"], show_alert=True)
    sec = f"{t['seconds']} {T[L]['sec']}" if t["seconds"] else T[L]["nolimit"]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=T[L]["back"], callback_data="menu"),
        InlineKeyboardButton(text=T[L]["go"], callback_data=f"go:{t['id']}"),
    ]])
    await cb.message.edit_text(T[L]["rules"].format(title=t["title"], n=n, sec=sec),
                               reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "menu")
async def back_menu(cb: CallbackQuery):
    if cb.from_user.id in SESS:
        return await cb.answer()
    await cb.message.delete()
    await show_tests(cb.message, cb.from_user.id)
    await cb.answer()


@router.callback_query(F.data.startswith("go:"))
async def go(cb: CallbackQuery, bot: Bot):
    uid = cb.from_user.id
    L = lang_of(uid)
    if uid in SESS:
        return await cb.answer(T[L]["busy"], show_alert=True)
    s, t = get_test_for(uid, int(cb.data.split(":")[1]))
    if not t:
        return await cb.answer()
    if db.q("SELECT 1 FROM results WHERE tg_id=? AND test_id=?", (uid, t["id"]), one=True):
        return await cb.answer(T[L]["taken"], show_alert=True)
    rows = db.q("SELECT * FROM questions WHERE test_id=?", (t["id"],))
    if not rows:
        return await cb.answer(T[L]["empty"], show_alert=True)

    shuffle = db.get_setting("shuffle", "1") == "1"
    qs = []
    for r in rows:
        opts = [(i, r[k]) for i, k in enumerate("abcd") if r[k]]
        if shuffle:
            random.shuffle(opts)
        qs.append(dict(text=r["text"], opts=opts, correct=r["correct"]))
    if shuffle:
        random.shuffle(qs)

    cls = db.q("SELECT name FROM classes WHERE id=?", (s["class_id"],), one=True)
    rid = db.q("INSERT INTO results(tg_id,username,tg_name,full_name,class_name,lang,test_id,test_title,total,started) "
               "VALUES(?,?,?,?,?,?,?,?,?,?)",
               (uid, s["username"], s["tg_name"], s["full_name"], cls["name"] if cls else "?",
                s["lang"], t["id"], t["title"], len(qs), now()), commit=True)
    SESS[uid] = dict(qs=qs, i=0, score=0, answers=[], msg=None, task=None,
                     sec=t["seconds"], rid=rid, lang=L, total=len(qs),
                     test_title=t["title"])
    await cb.message.delete()
    await cb.answer()
    await ask(bot, uid)


async def ask(bot: Bot, uid: int):
    s = SESS.get(uid)
    if not s:
        return
    if s["msg"]:
        try:
            await bot.delete_message(uid, s["msg"])
        except Exception:
            pass
        s["msg"] = None
    if s["i"] >= len(s["qs"]):
        return await finish(bot, uid)
    L = s["lang"]
    qd = s["qs"][s["i"]]
    head = f"❓ {s['i'] + 1}/{s['total']}"
    if s["sec"]:
        head += f"   ⏱ {s['sec']} {T[L]['sec']}"
    body = "\n".join([head, "", qd["text"], ""] + [f"{LET[k]}) {o[1]}" for k, o in enumerate(qd["opts"])])
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=LET[k], callback_data=f"a:{s['i']}:{k}") for k in range(len(qd["opts"]))
    ]])
    protect = db.get_setting("screenshot_block", "1") == "1"
    m = await bot.send_message(uid, body, reply_markup=kb, protect_content=protect)
    s["msg"] = m.message_id
    if s["sec"]:
        s["task"] = asyncio.create_task(timeout(bot, uid, s["i"], s["sec"]))


def record(s, qd, pos):
    correct_text = next(o[1] for o in qd["opts"] if o[0] == qd["correct"])
    if pos is None:
        chosen, ok = "—", False
    else:
        chosen = qd["opts"][pos][1]
        ok = qd["opts"][pos][0] == qd["correct"]
    if ok:
        s["score"] += 1
    s["answers"].append(dict(q=qd["text"], chosen=chosen, correct=correct_text, ok=ok))


async def timeout(bot: Bot, uid: int, i: int, sec: int):
    await asyncio.sleep(sec)
    s = SESS.get(uid)
    if s and s["i"] == i:
        record(s, s["qs"][i], None)
        s["i"] += 1
        await ask(bot, uid)


@router.callback_query(F.data.startswith("a:"))
async def answer(cb: CallbackQuery, bot: Bot):
    uid = cb.from_user.id
    s = SESS.get(uid)
    _, i, pos = cb.data.split(":")
    if not s or s["i"] != int(i):
        return await cb.answer()
    if s["task"]:
        s["task"].cancel()
    record(s, s["qs"][s["i"]], int(pos))
    s["i"] += 1
    await cb.answer()
    await ask(bot, uid)


async def finish(bot: Bot, uid: int):
    s = SESS.pop(uid, None)
    if not s:
        return
    L = s["lang"]
    pct = round(s["score"] * 100 / s["total"], 1)
    db.q("UPDATE results SET score=?,percent=?,finished=?,done=1,answers=? WHERE id=?",
         (s["score"], pct, now(), json.dumps(s["answers"], ensure_ascii=False), s["rid"]), commit=True)
    if db.get_setting("show_result", "1") == "1":
        text = T[L]["finish"].format(s=s["score"], t=s["total"], p=pct)
    else:
        text = T[L]["finish_hidden"]
    await bot.send_message(uid, text)
    if ADMIN_CHAT_ID:
        r = db.q("SELECT * FROM results WHERE id=?", (s["rid"],), one=True)
        try:
            await bot.send_message(
                ADMIN_CHAT_ID,
                f"📥 {r['full_name']} ({r['class_name']}) — {r['test_title']}: {r['score']}/{r['total']} ({pct}%)")
        except Exception:
            pass


# ================================================================
#  TELEGRAM ADMIN PANEL
# ================================================================

def adm_only(func):
    """Admin decorator."""
    @functools.wraps(func)
    async def wrapper(cb: CallbackQuery, *args, **kwargs):
        if not is_admin(cb.from_user.id):
            return await cb.answer("⛔ Ruxsat yo'q!", show_alert=True)
        return await func(cb, *args, **kwargs)
    return wrapper


# ---- Admin: bosh menyu ----

@router.callback_query(F.data == "adm:main")
@adm_only
async def adm_main(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.edit_text("🔧 <b>Admin panel</b>", reply_markup=admin_main_kb(), parse_mode="HTML")
    except Exception:
        await cb.message.answer("🔧 <b>Admin panel</b>", reply_markup=admin_main_kb(), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "adm:close")
@adm_only
async def adm_close(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer("✅ Admin panel yopildi.")


# ---- Admin: Statistika ----

@router.callback_query(F.data == "adm:stats")
@adm_only
async def adm_stats(cb: CallbackQuery):
    students_count = db.q("SELECT COUNT(*) c FROM students", one=True)["c"]
    classes_count = db.q("SELECT COUNT(*) c FROM classes", one=True)["c"]
    tests_count = db.q("SELECT COUNT(*) c FROM tests", one=True)["c"]
    active_tests = db.q("SELECT COUNT(*) c FROM tests WHERE active=1", one=True)["c"]
    results_count = db.q("SELECT COUNT(*) c FROM results WHERE done=1", one=True)["c"]
    avg_pct = db.q("SELECT AVG(percent) a FROM results WHERE done=1", one=True)["a"]
    unread_msgs = db.q("SELECT COUNT(*) c FROM messages WHERE reply IS NULL OR reply=''", one=True)["c"]
    active_sessions = len(SESS)

    text = (
        "📊 <b>Statistika</b>\n\n"
        f"👥 O'quvchilar: <b>{students_count}</b>\n"
        f"🏫 Sinflar: <b>{classes_count}</b>\n"
        f"📝 Testlar (jami): <b>{tests_count}</b> | Faol: <b>{active_tests}</b>\n"
        f"📈 Topshirilgan testlar: <b>{results_count}</b>\n"
        f"📊 O'rtacha ball: <b>{round(avg_pct or 0, 1)}%</b>\n"
        f"✉️ O'qilmagan xabarlar: <b>{unread_msgs}</b>\n"
        f"⚡ Hozir test topshirmoqda: <b>{active_sessions}</b>\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="adm:stats")],
        [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="adm:main")],
    ])
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


# ---- Admin: O'quvchilar ----

@router.callback_query(F.data == "adm:students")
@adm_only
async def adm_students(cb: CallbackQuery):
    students_list = db.q(
        "SELECT s.tg_id, s.full_name, c.name as cls, s.lang, s.registered "
        "FROM students s LEFT JOIN classes c ON s.class_id=c.id "
        "ORDER BY s.registered DESC LIMIT 20"
    )
    total = db.q("SELECT COUNT(*) c FROM students", one=True)["c"]
    text = f"👥 <b>O'quvchilar (oxirgi 20 ta, jami: {total})</b>\n\n"
    for i, s in enumerate(students_list, 1):
        lang_flag = "🇺🇿" if s["lang"] == "uz" else "🇷🇺"
        text += f"{i}. {lang_flag} <b>{s['full_name']}</b> — {s['cls'] or '?'}\n"
        text += f"   ID: <code>{s['tg_id']}</code> | {s['registered'] or '—'}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Eng faollar", callback_data="adm:top_students")],
        [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="adm:main")],
    ])
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "adm:top_students")
@adm_only
async def adm_top_students(cb: CallbackQuery):
    top = db.q(
        "SELECT full_name, class_name, COUNT(*) tests, AVG(percent) avg_pct "
        "FROM results WHERE done=1 GROUP BY tg_id "
        "ORDER BY avg_pct DESC LIMIT 10"
    )
    text = "🏆 <b>Eng faol o'quvchilar (o'rtacha ball bo'yicha)</b>\n\n"
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    for i, r in enumerate(top):
        text += f"{medals[i]} {r['full_name']} ({r['class_name']}): {round(r['avg_pct'],1)}% | {r['tests']} test\n"
    kb = back_to_admin_kb()
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


# ---- Admin: Sinflar ----

@router.callback_query(F.data == "adm:classes")
@adm_only
async def adm_classes(cb: CallbackQuery):
    classes = db.q("SELECT c.*, COUNT(s.tg_id) as cnt FROM classes c "
                   "LEFT JOIN students s ON s.class_id=c.id GROUP BY c.id ORDER BY c.name")
    text = "🏫 <b>Sinflar ro'yxati</b>\n\n"
    if not classes:
        text += "Hali sinflar yo'q.\n"
    else:
        for c in classes:
            flag = "🇺🇿" if c["lang"] == "uz" else "🇷🇺"
            text += f"{flag} <b>{c['name']}</b> — {c['cnt']} o'quvchi (ID: {c['id']})\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Sinf qo'shish", callback_data="adm:add_class")],
        [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="adm:main")],
    ])
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "adm:add_class")
@adm_only
async def adm_add_class_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSt.add_class)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:classes")
    ]])
    try:
        await cb.message.edit_text(
            "🏫 <b>Yangi sinf qo'shish</b>\n\n"
            "Sinf nomini va tilini yozing:\n"
            "<code>10A uz</code> yoki <code>9B ru</code>\n\n"
            "Bir nechta sinf qo'shish uchun har birini yangi qatorga yozing.",
            reply_markup=kb, parse_mode="HTML"
        )
    except Exception:
        pass
    await cb.answer()


@router.message(AdminSt.add_class, F.text)
async def adm_add_class_done(m: Message, state: FSMContext, bot: Bot):
    if not is_admin(m.from_user.id):
        return
    added = []
    for line in m.text.strip().splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            lang = parts[-1].lower()
            if lang not in ("uz", "ru"):
                lang = "uz"
            name = " ".join(parts[:-1])
            db.q("INSERT INTO classes(name,lang) VALUES(?,?)", (name, lang), commit=True)
            added.append(f"{name} ({lang})")
        elif len(parts) == 1:
            db.q("INSERT INTO classes(name,lang) VALUES(?,?)", (parts[0], "uz"), commit=True)
            added.append(f"{parts[0]} (uz)")
    await state.clear()
    text = f"✅ Qo'shildi: {', '.join(added)}" if added else "❌ Hech narsa qo'shilmadi."
    await m.answer(text, reply_markup=admin_main_kb())


# ---- Admin: Testlar ----

@router.callback_query(F.data == "adm:tests")
@adm_only
async def adm_tests(cb: CallbackQuery):
    tests = db.q("SELECT t.*, COUNT(q.id) as q_cnt FROM tests t "
                 "LEFT JOIN questions q ON q.test_id=t.id GROUP BY t.id ORDER BY t.id DESC LIMIT 20")
    text = "📝 <b>Testlar (oxirgi 20 ta)</b>\n\n"
    if not tests:
        text += "Hali testlar yo'q.\n"
    else:
        for t in tests:
            status = "✅" if t["active"] else "⛔"
            flag = "🇺🇿" if t["lang"] == "uz" else "🇷🇺"
            text += f"{status} {flag} <b>{t['title']}</b>\n"
            text += f"   ❓ {t['q_cnt']} savol | ⏱ {t['seconds']}s | ID: {t['id']}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Test yaratish", callback_data="adm:add_test")],
        [InlineKeyboardButton(text="📋 Testni boshqarish", callback_data="adm:manage_tests")],
        [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="adm:main")],
    ])
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "adm:add_test")
@adm_only
async def adm_add_test_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSt.add_test_title)
    await state.update_data(adm_msg_id=cb.message.message_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:tests")
    ]])
    try:
        await cb.message.edit_text(
            "📝 <b>Yangi test yaratish</b>\n\n"
            "1️⃣ Test nomini yozing (masalan: <i>Matematika — 1-variant</i>):",
            reply_markup=kb, parse_mode="HTML"
        )
    except Exception:
        pass
    await cb.answer()


@router.message(AdminSt.add_test_title, F.text)
async def adm_add_test_title(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    await state.update_data(test_title=m.text.strip())
    await state.set_state(AdminSt.add_test_seconds)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="30 son.", callback_data="adm:sec:30"),
         InlineKeyboardButton(text="60 son.", callback_data="adm:sec:60"),
         InlineKeyboardButton(text="90 son.", callback_data="adm:sec:90")],
        [InlineKeyboardButton(text="Cheklanmagan", callback_data="adm:sec:0")],
    ])
    await m.answer(
        "2️⃣ Har bir savolga necha soniya vaqt?\n(Yoki quyidagidan tanlang):",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("adm:sec:"))
@adm_only
async def adm_test_seconds_cb(cb: CallbackQuery, state: FSMContext):
    sec = int(cb.data.split(":")[-1])
    await _finish_test_creation(cb.message, state, sec, cb.from_user.id)
    await cb.answer()


@router.message(AdminSt.add_test_seconds, F.text)
async def adm_test_seconds_msg(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    try:
        sec = int(m.text.strip())
    except ValueError:
        sec = 30
    await _finish_test_creation(m, state, sec, m.from_user.id)


async def _finish_test_creation(target, state: FSMContext, sec: int, uid: int):
    d = await state.get_data()
    title = d.get("test_title", "Test")
    # Tilni bilish uchun admin sinfidan olish yoki default
    s = student(uid)
    lang = s["lang"] if s else "uz"
    tid = db.q("INSERT INTO tests(title,lang,seconds,active) VALUES(?,?,?,1)",
               (title, lang, sec), commit=True)
    await state.clear()
    text = (
        f"✅ Test yaratildi!\n\n"
        f"📝 Nom: <b>{title}</b>\n"
        f"⏱ Vaqt: <b>{sec if sec else 'cheklanmagan'}</b>\n"
        f"🆔 ID: <b>{tid}</b>\n\n"
        f"Savol qo'shish uchun: /addq_{tid}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Savol qo'shish", callback_data=f"adm:addq:{tid}")],
        [InlineKeyboardButton(text="🔙 Testlar", callback_data="adm:tests")],
    ])
    if hasattr(target, 'edit_text'):
        try:
            await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await target.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "adm:manage_tests")
@adm_only
async def adm_manage_tests(cb: CallbackQuery):
    tests = db.q("SELECT * FROM tests ORDER BY id DESC LIMIT 15")
    if not tests:
        await cb.answer("Testlar yo'q!", show_alert=True)
        return
    text = "📋 <b>Test tanlang:</b>"
    rows = []
    for t in tests:
        status = "✅" if t["active"] else "⛔"
        rows.append([InlineKeyboardButton(
            text=f"{status} {t['title'][:30]}",
            callback_data=f"adm:test:{t['id']}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="adm:tests")])
    try:
        await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:test:"))
@adm_only
async def adm_test_detail(cb: CallbackQuery):
    tid = int(cb.data.split(":")[-1])
    t = db.q("SELECT * FROM tests WHERE id=?", (tid,), one=True)
    if not t:
        return await cb.answer("Test topilmadi!")
    q_cnt = db.q("SELECT COUNT(*) c FROM questions WHERE test_id=?", (tid,), one=True)["c"]
    results_cnt = db.q("SELECT COUNT(*) c FROM results WHERE test_id=? AND done=1", (tid,), one=True)["c"]
    status_text = "✅ Faol" if t["active"] else "⛔ Nofaol"
    flag = "🇺🇿" if t["lang"] == "uz" else "🇷🇺"
    text = (
        f"📝 <b>{t['title']}</b>\n\n"
        f"🆔 ID: {tid}\n"
        f"{flag} Til: {t['lang']}\n"
        f"📊 Holat: {status_text}\n"
        f"⏱ Vaqt: {t['seconds'] if t['seconds'] else 'cheklanmagan'} s\n"
        f"❓ Savollar: {q_cnt} ta\n"
        f"📈 Topshirildi: {results_cnt} marta\n"
    )
    toggle_text = "⛔ O'chirish" if t["active"] else "✅ Yoqish"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Savol qo'shish", callback_data=f"adm:addq:{tid}")],
        [InlineKeyboardButton(text="📋 Savollarni ko'rish", callback_data=f"adm:qlist:{tid}")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"adm:toggle:{tid}"),
         InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"adm:deltest:{tid}")],
        [InlineKeyboardButton(text="🔙 Testlar", callback_data="adm:manage_tests")],
    ])
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:toggle:"))
@adm_only
async def adm_toggle_test(cb: CallbackQuery):
    tid = int(cb.data.split(":")[-1])
    t = db.q("SELECT active FROM tests WHERE id=?", (tid,), one=True)
    if not t:
        return await cb.answer("Test topilmadi!")
    new_val = 0 if t["active"] else 1
    db.q("UPDATE tests SET active=? WHERE id=?", (new_val, tid), commit=True)
    status = "✅ Yoqildi" if new_val else "⛔ O'chirildi"
    await cb.answer(f"Test {status}", show_alert=True)
    # Refresh
    await adm_test_detail(cb)


@router.callback_query(F.data.startswith("adm:deltest:"))
@adm_only
async def adm_del_test(cb: CallbackQuery):
    tid = int(cb.data.split(":")[-1])
    db.q("DELETE FROM questions WHERE test_id=?", (tid,), commit=True)
    db.q("DELETE FROM tests WHERE id=?", (tid,), commit=True)
    await cb.answer("🗑 Test o'chirildi!", show_alert=True)
    await adm_tests(cb)


@router.callback_query(F.data.startswith("adm:qlist:"))
@adm_only
async def adm_qlist(cb: CallbackQuery):
    tid = int(cb.data.split(":")[-1])
    qs = db.q("SELECT * FROM questions WHERE test_id=? ORDER BY id", (tid,))
    t = db.q("SELECT title FROM tests WHERE id=?", (tid,), one=True)
    text = f"❓ <b>Savollar: {t['title'] if t else tid}</b>\n\n"
    if not qs:
        text += "Hali savollar yo'q."
    else:
        for i, q in enumerate(qs, 1):
            letters = "ABCD"
            opts = [f"{letters[j]}) {q[k]}" for j, k in enumerate("abcd") if q[k]]
            correct_letter = letters[q["correct"]] if q["correct"] < 4 else "?"
            text += f"{i}. {q['text']}\n   " + " | ".join(opts) + f"\n   ✅ To'g'ri: {correct_letter}\n\n"
            if len(text) > 3500:
                text += "...(qolganlar ko'rsatilmadi)"
                break
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Savol qo'shish", callback_data=f"adm:addq:{tid}")],
        [InlineKeyboardButton(text="🔙 Test", callback_data=f"adm:test:{tid}")],
    ])
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


# Savol qo'shish (qadam-qadam)
@router.callback_query(F.data.startswith("adm:addq:"))
@adm_only
async def adm_addq_start(cb: CallbackQuery, state: FSMContext):
    tid = int(cb.data.split(":")[-1])
    await state.set_state(AdminSt.add_q_text)
    await state.update_data(addq_tid=tid)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor", callback_data=f"adm:test:{tid}")
    ]])
    try:
        await cb.message.edit_text(
            "➕ <b>Yangi savol qo'shish</b>\n\n"
            "Savol matnini yozing.\n\n"
            "<i>Maslahat: Barcha ma'lumotni bir xabarda ham yuborishingiz mumkin:</i>\n"
            "<code>Savol matni\nA variant\nB variant\nC variant\nD variant\nA</code>",
            reply_markup=kb, parse_mode="HTML"
        )
    except Exception:
        pass
    await cb.answer()


@router.message(AdminSt.add_q_text, F.text)
async def adm_addq_text(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    lines = m.text.strip().splitlines()
    # Agar 6 qator kelsa: savol, A, B, C, D, to'g'ri
    if len(lines) >= 6:
        q_text = lines[0].strip()
        a, b, c, d = lines[1].strip(), lines[2].strip(), lines[3].strip(), lines[4].strip()
        correct_letter = lines[5].strip().upper()
        letter_map = {"A": 0, "B": 1, "C": 2, "D": 3, "1": 0, "2": 1, "3": 2, "4": 3}
        correct_idx = letter_map.get(correct_letter, 0)
        d_data = await state.get_data()
        tid = d_data["addq_tid"]
        db.q("INSERT INTO questions(test_id,text,a,b,c,d,correct) VALUES(?,?,?,?,?,?,?)",
             (tid, q_text, a, b, c, d, correct_idx), commit=True)
        q_cnt = db.q("SELECT COUNT(*) c FROM questions WHERE test_id=?", (tid,), one=True)["c"]
        await state.clear()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Yana savol", callback_data=f"adm:addq:{tid}")],
            [InlineKeyboardButton(text="📋 Savollar", callback_data=f"adm:qlist:{tid}")],
            [InlineKeyboardButton(text="🔙 Test", callback_data=f"adm:test:{tid}")],
        ])
        await m.answer(f"✅ Savol qo'shildi! Jami: {q_cnt} ta", reply_markup=kb)
        return
    # Aks holda qadam-qadam
    await state.update_data(addq_text=m.text.strip())
    await state.set_state(AdminSt.add_q_a)
    await m.answer("A) variantni yozing:")


@router.message(AdminSt.add_q_a, F.text)
async def adm_addq_a(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    await state.update_data(addq_a=m.text.strip())
    await state.set_state(AdminSt.add_q_b)
    await m.answer("B) variantni yozing:")


@router.message(AdminSt.add_q_b, F.text)
async def adm_addq_b(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    await state.update_data(addq_b=m.text.strip())
    await state.set_state(AdminSt.add_q_c)
    await m.answer("C) variantni yozing:")


@router.message(AdminSt.add_q_c, F.text)
async def adm_addq_c(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    await state.update_data(addq_c=m.text.strip())
    await state.set_state(AdminSt.add_q_d)
    await m.answer("D) variantni yozing (ixtiyoriy, o'tkazib yuborish uchun '-' yozing):")


@router.message(AdminSt.add_q_d, F.text)
async def adm_addq_d(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    d_val = m.text.strip()
    if d_val == "-":
        d_val = ""
    await state.update_data(addq_d=d_val)
    await state.set_state(AdminSt.add_q_correct)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="A", callback_data="adm:correct:0"),
        InlineKeyboardButton(text="B", callback_data="adm:correct:1"),
        InlineKeyboardButton(text="C", callback_data="adm:correct:2"),
        InlineKeyboardButton(text="D", callback_data="adm:correct:3"),
    ]])
    await m.answer("To'g'ri javobni tanlang:", reply_markup=kb)


@router.callback_query(F.data.startswith("adm:correct:"))
@adm_only
async def adm_addq_correct(cb: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != AdminSt.add_q_correct:
        return await cb.answer()
    correct_idx = int(cb.data.split(":")[-1])
    d = await state.get_data()
    tid = d["addq_tid"]
    db.q("INSERT INTO questions(test_id,text,a,b,c,d,correct) VALUES(?,?,?,?,?,?,?)",
         (tid, d["addq_text"], d["addq_a"], d["addq_b"], d["addq_c"], d.get("addq_d", ""), correct_idx),
         commit=True)
    q_cnt = db.q("SELECT COUNT(*) c FROM questions WHERE test_id=?", (tid,), one=True)["c"]
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yana savol", callback_data=f"adm:addq:{tid}")],
        [InlineKeyboardButton(text="📋 Savollar", callback_data=f"adm:qlist:{tid}")],
        [InlineKeyboardButton(text="🔙 Test", callback_data=f"adm:test:{tid}")],
    ])
    try:
        await cb.message.edit_text(f"✅ Savol qo'shildi! Jami: {q_cnt} ta", reply_markup=kb)
    except Exception:
        await cb.message.answer(f"✅ Savol qo'shildi! Jami: {q_cnt} ta", reply_markup=kb)
    await cb.answer()


# ---- Admin: Natijalar ----

@router.callback_query(F.data == "adm:results")
@adm_only
async def adm_results(cb: CallbackQuery):
    results = db.q(
        "SELECT full_name, class_name, test_title, score, total, percent, finished "
        "FROM results WHERE done=1 ORDER BY finished DESC LIMIT 15"
    )
    total_cnt = db.q("SELECT COUNT(*) c FROM results WHERE done=1", one=True)["c"]
    text = f"📈 <b>So'nggi natijalar (jami: {total_cnt})</b>\n\n"
    if not results:
        text += "Hali natijalar yo'q."
    else:
        for r in results:
            emoji = "✅" if r["percent"] >= 60 else "❌"
            text += (
                f"{emoji} <b>{r['full_name']}</b> ({r['class_name']})\n"
                f"   📝 {r['test_title']}\n"
                f"   {r['score']}/{r['total']} — {r['percent']}% | {r['finished'] or '—'}\n\n"
            )
            if len(text) > 3500:
                text += "...(qolganlar ko'rsatilmadi)"
                break
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="adm:results")],
        [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="adm:main")],
    ])
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


# ---- Admin: Xabarlar ----

@router.callback_query(F.data == "adm:messages")
@adm_only
async def adm_messages(cb: CallbackQuery):
    msgs = db.q(
        "SELECT * FROM messages ORDER BY created DESC LIMIT 10"
    )
    unread = db.q("SELECT COUNT(*) c FROM messages WHERE reply IS NULL OR reply=''", one=True)["c"]
    text = f"✉️ <b>Xabarlar (o'qilmagan: {unread})</b>\n\n"
    if not msgs:
        text += "Xabarlar yo'q."
        kb = back_to_admin_kb()
        try:
            await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
        return await cb.answer()

    rows = []
    for msg in msgs:
        status = "✅" if (msg["reply"] and msg["reply"].strip()) else "🔴"
        rows.append([InlineKeyboardButton(
            text=f"{status} {msg['full_name'][:20]}: {msg['text'][:25]}...",
            callback_data=f"adm:msg:{msg['id']}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="adm:main")])
    try:
        await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:msg:"))
@adm_only
async def adm_msg_detail(cb: CallbackQuery, state: FSMContext):
    mid = int(cb.data.split(":")[-1])
    msg = db.q("SELECT * FROM messages WHERE id=?", (mid,), one=True)
    if not msg:
        return await cb.answer("Xabar topilmadi!")
    text = (
        f"✉️ <b>Xabar #{mid}</b>\n\n"
        f"👤 {msg['full_name']} ({msg['class_name']})\n"
        f"🕐 {msg['created']}\n\n"
        f"📩 <b>Xabar:</b>\n{msg['text']}\n"
    )
    if msg["reply"]:
        text += f"\n📤 <b>Javob:</b>\n{msg['reply']}\n🕐 {msg['replied_at']}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Javob yozish", callback_data=f"adm:reply:{mid}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"adm:delmsg:{mid}")],
        [InlineKeyboardButton(text="🔙 Xabarlar", callback_data="adm:messages")],
    ])
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:reply:"))
@adm_only
async def adm_reply_start(cb: CallbackQuery, state: FSMContext):
    mid = int(cb.data.split(":")[-1])
    await state.set_state(AdminSt.reply_msg)
    await state.update_data(reply_msg_id=mid)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor", callback_data=f"adm:msg:{mid}")
    ]])
    try:
        await cb.message.edit_text(
            "📤 Javob matnini yozing (o'quvchiga Telegram orqali yuboriladi):",
            reply_markup=kb
        )
    except Exception:
        pass
    await cb.answer()


@router.message(AdminSt.reply_msg, F.text)
async def adm_reply_send(m: Message, state: FSMContext, bot: Bot):
    if not is_admin(m.from_user.id):
        return
    d = await state.get_data()
    mid = d["reply_msg_id"]
    msg = db.q("SELECT * FROM messages WHERE id=?", (mid,), one=True)
    if not msg:
        await state.clear()
        return await m.answer("Xabar topilmadi.")
    reply_text = m.text.strip()
    db.q("UPDATE messages SET reply=?,replied_at=? WHERE id=?",
         (reply_text, now(), mid), commit=True)
    # O'quvchiga yuborish
    try:
        await bot.send_message(
            msg["tg_id"],
            f"📬 <b>Admin javobi:</b>\n\n{reply_text}",
            parse_mode="HTML"
        )
        await m.answer("✅ Javob yuborildi!")
    except Exception as e:
        await m.answer(f"❌ Xato: {e}")
    await state.clear()


@router.callback_query(F.data.startswith("adm:delmsg:"))
@adm_only
async def adm_del_msg(cb: CallbackQuery):
    mid = int(cb.data.split(":")[-1])
    db.q("DELETE FROM messages WHERE id=?", (mid,), commit=True)
    await cb.answer("🗑 O'chirildi!", show_alert=True)
    await adm_messages(cb)


# ---- Admin: Broadcast ----

@router.callback_query(F.data == "adm:broadcast")
@adm_only
async def adm_broadcast_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSt.broadcast_text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 Faqat uzbekcha", callback_data="adm:bc_lang:uz"),
         InlineKeyboardButton(text="🇷🇺 Faqat ruscha", callback_data="adm:bc_lang:ru")],
        [InlineKeyboardButton(text="👥 Hammaga", callback_data="adm:bc_lang:all")],
        [InlineKeyboardButton(text="❌ Bekor", callback_data="adm:main")],
    ])
    try:
        await cb.message.edit_text(
            "📢 <b>Broadcast</b>\n\nKimga yuborilsin?",
            reply_markup=kb, parse_mode="HTML"
        )
    except Exception:
        pass
    await cb.answer()


@router.callback_query(F.data.startswith("adm:bc_lang:"))
@adm_only
async def adm_bc_lang(cb: CallbackQuery, state: FSMContext):
    lang = cb.data.split(":")[-1]
    await state.update_data(bc_lang=lang)
    await state.set_state(AdminSt.broadcast_text)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor", callback_data="adm:main")
    ]])
    lang_text = {"uz": "🇺🇿 O'zbek", "ru": "🇷🇺 Rus", "all": "👥 Hammaga"}
    try:
        await cb.message.edit_text(
            f"📢 Xabar matni ({lang_text.get(lang, lang)}):\n\nYuboriladigan xabarni yozing:",
            reply_markup=kb
        )
    except Exception:
        pass
    await cb.answer()


@router.message(AdminSt.broadcast_text, F.text)
async def adm_broadcast_text(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    await state.update_data(bc_text=m.text.strip())
    await state.set_state(AdminSt.broadcast_confirm)
    d = await state.get_data()
    lang = d.get("bc_lang", "all")
    if lang == "all":
        count = db.q("SELECT COUNT(*) c FROM students", one=True)["c"]
    else:
        count = db.q("SELECT COUNT(*) c FROM students WHERE lang=?", (lang,), one=True)["c"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Ha, {count} ta o'quvchiga yuborish", callback_data="adm:bc_confirm")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:main")],
    ])
    await m.answer(
        f"📢 <b>Xabar:</b>\n\n{m.text[:500]}\n\n"
        f"👥 Qabul qiluvchilar: <b>{count} ta</b>\n\nYuborishni tasdiqlaysizmi?",
        reply_markup=kb, parse_mode="HTML"
    )


@router.callback_query(F.data == "adm:bc_confirm")
@adm_only
async def adm_broadcast_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot):
    d = await state.get_data()
    text = d.get("bc_text", "")
    lang = d.get("bc_lang", "all")
    await state.clear()

    if lang == "all":
        students_list = db.q("SELECT tg_id FROM students")
    else:
        students_list = db.q("SELECT tg_id FROM students WHERE lang=?", (lang,))

    try:
        await cb.message.edit_text(f"⏳ Yuborilmoqda... ({len(students_list)} ta)")
    except Exception:
        pass

    sent, failed = 0, 0
    for s in students_list:
        try:
            await bot.send_message(s["tg_id"], text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await cb.answer()
    await cb.message.answer(
        f"✅ Broadcast yakunlandi!\n\n"
        f"📤 Yuborildi: {sent}\n"
        f"❌ Xato: {failed}",
        reply_markup=admin_main_kb()
    )


# ---- Admin: Sozlamalar ----

@router.callback_query(F.data == "adm:settings")
@adm_only
async def adm_settings(cb: CallbackQuery):
    show_result = db.get_setting("show_result", "1")
    shuffle = db.get_setting("shuffle", "1")
    screenshot_block = db.get_setting("screenshot_block", "1")
    student_pass = db.get_setting("student_password", "—")
    show_icon = "✅" if show_result == "1" else "❌"
    shuffle_icon = "✅" if shuffle == "1" else "❌"
    scr_icon = "🔒" if screenshot_block == "1" else "🔓"
    text = (
        "⚙️ <b>Sozlamalar</b>\n\n"
        f"🔑 O'quvchi paroli: <code>{student_pass}</code>\n"
        f"📊 Natijani ko'rsatish: {show_icon}\n"
        f"🔀 Savollarni aralashtirish: {shuffle_icon}\n"
        f"🔒 Screenshot bloklash: {scr_icon}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{show_icon} Natijani ko'rsatish", callback_data="adm:toggle_show")],
        [InlineKeyboardButton(text=f"{shuffle_icon} Aralashtirish", callback_data="adm:toggle_shuffle")],
        [InlineKeyboardButton(text=f"{scr_icon} Screenshot bloklash", callback_data="adm:toggle_scr")],
        [InlineKeyboardButton(text="🔑 Parolni o'zgartirish", callback_data="adm:change_pass")],
        [InlineKeyboardButton(text="👤 Admin ID qo'shish", callback_data="adm:add_admin_id")],
        [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="adm:main")],
    ])
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "adm:toggle_show")
@adm_only
async def adm_toggle_show(cb: CallbackQuery):
    cur = db.get_setting("show_result", "1")
    db.set_setting("show_result", "0" if cur == "1" else "1")
    await cb.answer("✅ O'zgartirildi!", show_alert=True)
    await adm_settings(cb)


@router.callback_query(F.data == "adm:toggle_shuffle")
@adm_only
async def adm_toggle_shuffle(cb: CallbackQuery):
    cur = db.get_setting("shuffle", "1")
    db.set_setting("shuffle", "0" if cur == "1" else "1")
    await cb.answer("✅ O'zgartirildi!", show_alert=True)
    await adm_settings(cb)


@router.callback_query(F.data == "adm:toggle_scr")
@adm_only
async def adm_toggle_scr(cb: CallbackQuery):
    cur = db.get_setting("screenshot_block", "1")
    new_val = "0" if cur == "1" else "1"
    db.set_setting("screenshot_block", new_val)
    status = "🔒 Yoqildi (savollar copy/screenshot bloklangan)" if new_val == "1" else "🔓 O'chirildi"
    await cb.answer(status, show_alert=True)
    await adm_settings(cb)


@router.callback_query(F.data == "adm:change_pass")
@adm_only
async def adm_change_pass_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSt.change_student_pass)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor", callback_data="adm:settings")
    ]])
    try:
        await cb.message.edit_text(
            "🔑 Yangi o'quvchi parolini yozing:",
            reply_markup=kb
        )
    except Exception:
        pass
    await cb.answer()


@router.message(AdminSt.change_student_pass, F.text)
async def adm_change_pass_done(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    new_pass = m.text.strip()
    if len(new_pass) < 4:
        return await m.answer("❌ Parol kamida 4 ta belgi bo'lishi kerak!")
    db.set_setting("student_password", new_pass)
    await state.clear()
    await m.answer(f"✅ O'quvchi paroli o'zgartirildi: <code>{new_pass}</code>",
                   reply_markup=admin_main_kb(), parse_mode="HTML")


@router.callback_query(F.data == "adm:add_admin_id")
@adm_only
async def adm_add_admin_id_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSt.change_admin_pass)
    current_ids = db.get_setting("admin_ids", "")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor", callback_data="adm:settings")
    ]])
    try:
        await cb.message.edit_text(
            f"👤 <b>Admin ID qo'shish</b>\n\n"
            f"Hozirgi adminlar: <code>{current_ids or 'ADMIN_IDS env orqali'}</code>\n\n"
            f"Yangi admin Telegram ID sini yozing:\n"
            f"(O'z ID ingizni bilish uchun @userinfobot botiga /start yuboring)",
            reply_markup=kb, parse_mode="HTML"
        )
    except Exception:
        pass
    await cb.answer()


@router.message(AdminSt.change_admin_pass, F.text)
async def adm_add_admin_id_done(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    try:
        new_id = int(m.text.strip())
    except ValueError:
        return await m.answer("❌ Noto'g'ri ID. Faqat raqam kiriting.")
    current_ids = db.get_setting("admin_ids", "")
    ids_list = [i.strip() for i in current_ids.split(",") if i.strip()] if current_ids else []
    if str(new_id) not in ids_list:
        ids_list.append(str(new_id))
    db.set_setting("admin_ids", ",".join(ids_list))
    # Xotiradagi admin ro'yxatga ham qo'shamiz
    ADMIN_IDS.add(new_id)
    await state.clear()
    await m.answer(
        f"✅ Admin qo'shildi: <code>{new_id}</code>\n"
        f"Jami adminlar: <code>{','.join(ids_list)}</code>",
        reply_markup=admin_main_kb(), parse_mode="HTML"
    )


# ================================================================
# TO'XTATILGAN TEST — davom ettirish tugmasi
# ================================================================

@router.message(F.text.in_(ALL_CONTINUE_BTNS))
async def btn_continue_test(m: Message, bot: Bot):
    uid = m.from_user.id
    if uid in SESS:
        try:
            await m.delete()
        except Exception:
            pass
        return
    s = student(uid)
    L = s["lang"] if s else "uz"
    if uid not in PAUSED_SESS:
        return await m.answer(T[L]["continue_not_found"])
    ps = PAUSED_SESS[uid]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=T[L]["btn_yes_continue"], callback_data="continue:yes")],
        [InlineKeyboardButton(text=T[L]["btn_no_discard"], callback_data="continue:no")],
    ])
    await m.answer(
        T[L]["continue_confirm"].format(
            title=ps["test_title"],
            done=ps["i"],
            total=ps["total"]
        ),
        reply_markup=kb, parse_mode="HTML"
    )


@router.callback_query(F.data == "continue:yes")
async def continue_yes(cb: CallbackQuery, bot: Bot):
    uid = cb.from_user.id
    s = student(uid)
    L = s["lang"] if s else "uz"
    if uid in SESS:
        return await cb.answer(T[L]["busy"], show_alert=True)
    ps = PAUSED_SESS.pop(uid, None)
    if not ps:
        await cb.answer(T[L]["continue_not_found"], show_alert=True)
        try:
            await cb.message.delete()
        except Exception:
            pass
        return
    # Sessiyani qayta tiklash
    SESS[uid] = ps
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer("▶️ Test davom etmoqda!")
    # Klaviaturani yangilash (continue tugmasi yo'qolsin)
    adm = is_admin(uid)
    try:
        await bot.send_message(
            uid,
            "▶️ Test davom etmoqda...",
            reply_markup=main_kb(L, is_admin=adm, has_paused=False)
        )
    except Exception:
        pass
    await ask(bot, uid)


@router.callback_query(F.data == "continue:no")
async def continue_no(cb: CallbackQuery):
    uid = cb.from_user.id
    s = student(uid)
    L = s["lang"] if s else "uz"
    ps = PAUSED_SESS.pop(uid, None)
    if ps:
        # Natijani o'chiramiz (qayta topshirish imkoniyati)
        db.q("DELETE FROM results WHERE id=?", (ps["rid"],), commit=True)
    adm = is_admin(uid)
    try:
        await cb.message.edit_text(T[L]["discard_done"])
    except Exception:
        pass
    await cb.answer()
    await cb.message.answer(
        T[L]["discard_done"],
        reply_markup=main_kb(L, is_admin=adm, has_paused=False)
    )


# ================================================================
# BOT BLOCK / UNBLOCK (foydalanuvchi TGdan chiqsa yoki AI ishlatsa)
# ================================================================

async def _notify_admins(bot: Bot, text: str):
    """Barcha adminlarga xabar yuborish."""
    notified = set()
    # ADMIN_CHAT_ID
    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(int(ADMIN_CHAT_ID), text, parse_mode="HTML")
            notified.add(str(ADMIN_CHAT_ID))
        except Exception:
            pass
    # ADMIN_IDS
    for aid in ADMIN_IDS:
        if str(aid) not in notified:
            try:
                await bot.send_message(aid, text, parse_mode="HTML")
            except Exception:
                pass
    # DB admin_ids
    ids_str = db.get_setting("admin_ids", "")
    if ids_str:
        for aid_s in ids_str.split(","):
            aid_s = aid_s.strip()
            if aid_s and aid_s not in notified:
                try:
                    await bot.send_message(int(aid_s), text, parse_mode="HTML")
                    notified.add(aid_s)
                except Exception:
                    pass


@router.my_chat_member()
async def on_my_chat_member(update: ChatMemberUpdated, bot: Bot):
    """
    Foydalanuvchi botni block qilganda yoki unblock qilganda ishga tushadi.
    block = foydalanuvchi TGdan chiqdi / AI ishlatish uchun botni ochdi deb hisoblanadi.
    """
    uid = update.from_user.id
    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status

    # Foydalanuvchi botni BLOCK qildi (kicked yoki left)
    if new_status in ("kicked", "left") and old_status not in ("kicked", "left"):
        s = student(uid)
        L = s["lang"] if s else "uz"
        name = s["full_name"] if s else update.from_user.full_name
        username = f"@{s['username']}" if s and s.get("username") else update.from_user.full_name

        # Test davom etayotgan bo'lsa — to'xtatib saqlaymiz
        sess = SESS.pop(uid, None)
        if sess:
            # Timeout taskni bekor qilamiz
            if sess.get("task"):
                sess["task"].cancel()
            # Natija satrini bekor qilamiz (o'chirib qayta topshirsin)
            # Sessiyani PAUSED_SESS ga ko'chiramiz
            PAUSED_SESS[uid] = sess

            # Adminga xabar
            cls_row = db.q("SELECT name FROM classes WHERE id=?",
                           (s["class_id"],), one=True) if s else None
            cls_name = cls_row["name"] if cls_row else "?"
            await _notify_admins(
                bot,
                f"🚨 <b>Test to'xtatildi!</b>\n\n"
                f"👤 {name} ({cls_name}) {username}\n"
                f"📝 Test: <b>{sess['test_title']}</b>\n"
                f"❓ Javoblangan: {sess['i']}/{sess['total']}\n"
                f"⚠️ Sabab: Foydalanuvchi Telegramdan chiqdi / botni blockladi\n\n"
                f"📌 O'quvchi qaytib kelganda testni davom ettirishi mumkin."
            )
        else:
            # Test bo'lmasa ham xabar berish (shubhali harakatlar uchun)
            if s:
                await _notify_admins(
                    bot,
                    f"⚠️ <b>Foydalanuvchi botni blockladi</b>\n\n"
                    f"👤 {name} {username}\n"
                    f"🕐 {now()}"
                )

    # Foydalanuvchi botni UNBLOCK qildi
    elif new_status == "member" and old_status in ("kicked", "left"):
        s = student(uid)
        if not s:
            return
        L = s["lang"]
        has_paused = uid in PAUSED_SESS
        adm = is_admin(uid)
        if has_paused:
            ps = PAUSED_SESS[uid]
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=T[L]["btn_yes_continue"], callback_data="continue:yes")],
                [InlineKeyboardButton(text=T[L]["btn_no_discard"], callback_data="continue:no")],
            ])
            try:
                await bot.send_message(
                    uid,
                    T[L]["test_paused_blocked"],
                    reply_markup=main_kb(L, is_admin=adm, has_paused=True),
                    parse_mode="HTML"
                )
                await bot.send_message(
                    uid,
                    T[L]["continue_confirm"].format(
                        title=ps["test_title"],
                        done=ps["i"],
                        total=ps["total"]
                    ),
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except Exception:
                pass


# ================================================================
# Fallback
# ================================================================

@router.message()
async def fallback(m: Message):
    if m.from_user.id in SESS:
        try:
            await m.delete()
        except Exception:
            pass


# ================================================================
# Run
# ================================================================

async def run():
    if not TOKEN:
        raise SystemExit("BOT_TOKEN o'rnatilmagan! Masalan: export BOT_TOKEN=123:ABC")
    # DB dan admin ID larni yuklash
    ids_str = db.get_setting("admin_ids", "")
    if ids_str:
        for aid in ids_str.split(","):
            try:
                ADMIN_IDS.add(int(aid.strip()))
            except ValueError:
                pass
    # screenshot_block default qiymati
    if not db.get_setting("screenshot_block"):
        db.set_setting("screenshot_block", "1")
    logging.basicConfig(level=logging.INFO)
    bot = Bot(TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    # my_chat_member update larini qabul qilish uchun
    from aiogram.types import Update
    await dp.start_polling(bot, allowed_updates=[
        "message", "callback_query", "my_chat_member"
    ])
