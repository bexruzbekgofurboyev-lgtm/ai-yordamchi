"""
AI Yordamchi va Vazifa Rejalashtiruvchi Telegram Bot
Gemini API asosida ishlaydi.

O'rnatish va ishga tushirish yo'riqnomasi README.md faylida.
"""

import json
import os
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==================== SOZLAMALAR ====================
# Bu ikkala qiymatni muhit o'zgaruvchilari (environment variables) orqali bering.
# Pastda README.md faylida buni qanday qilish tushuntirilgan.

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# DATA_DIR — ma'lumotlar qayerga saqlanishini belgilaydi. Agar Railway'da
# Volume ulangan bo'lsa, Railway buni avtomatik ravishda
# RAILWAY_VOLUME_MOUNT_PATH o'zgaruvchisiga yozadi — shuni ishlatamiz.
# Aks holda joriy papkada saqlanadi (Volume bo'lmasa, qayta deploy
# qilinganda ma'lumotlar yo'qolishi mumkin).
DATA_DIR = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or os.environ.get("DATA_DIR", ".")
DB_PATH = Path(DATA_DIR) / "tasks.db"

# Bot foydalanuvchisi joylashgan hudud vaqti — Toshkent (UTC+5). Nisbiy vaqt
# ifodalarini ("ertaga", "bugun kechqurun") to'g'ri hisoblash uchun kerak.
TASHKENT_OFFSET = timedelta(hours=5)

# Har bir foydalanuvchi uchun kontekstga qo'shiladigan oxirgi xabarlar soni.
CHAT_HISTORY_LIMIT = 16

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def now_tashkent() -> datetime:
    return datetime.utcnow() + TASHKENT_OFFSET


# ==================== MA'LUMOTLARNI SAQLASH (SQLite) ====================

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            text TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            created TEXT NOT NULL,
            proposed_remind_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            task_id INTEGER,
            task_text TEXT NOT NULL,
            remind_at TEXT NOT NULL,
            sent INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            created TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_actions (
            user_id TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            task_id INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ---------- Vazifalar ----------

def get_user_tasks(user_id: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, text, done, created FROM tasks WHERE user_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()
    conn.close()
    return [
        {"id": row["id"], "text": row["text"], "done": bool(row["done"]), "created": row["created"]}
        for row in rows
    ]


def add_user_task(user_id: str, text: str) -> int:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO tasks (user_id, text, done, created) VALUES (?, ?, 0, ?)",
        (user_id, text, now_tashkent().strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id


def toggle_task(task_id: int, done: bool) -> None:
    conn = get_connection()
    conn.execute("UPDATE tasks SET done = ? WHERE id = ?", (int(done), task_id))
    conn.commit()
    conn.close()


def delete_task(task_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.execute("DELETE FROM reminders WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()


def clear_done_tasks(user_id: str) -> int:
    conn = get_connection()
    cursor = conn.execute("DELETE FROM tasks WHERE user_id = ? AND done = 1", (user_id,))
    conn.commit()
    removed = cursor.rowcount
    conn.close()
    return removed


def set_proposed_reminder(task_id: int, remind_at) -> None:
    conn = get_connection()
    conn.execute("UPDATE tasks SET proposed_remind_at = ? WHERE id = ?", (remind_at, task_id))
    conn.commit()
    conn.close()


def get_task(task_id: int):
    conn = get_connection()
    row = conn.execute(
        "SELECT id, user_id, text, done, created, proposed_remind_at FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


# ---------- Eslatmalar (reminders) ----------

def create_reminder(user_id: str, task_id, task_text: str, remind_at: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO reminders (user_id, task_id, task_text, remind_at, sent) VALUES (?, ?, ?, ?, 0)",
        (user_id, task_id, task_text, remind_at),
    )
    conn.commit()
    conn.close()


def get_due_reminders(now_str: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, user_id, task_text, remind_at FROM reminders WHERE sent = 0 AND remind_at <= ?",
        (now_str,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_reminder_sent(reminder_id: int) -> None:
    conn = get_connection()
    conn.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


# ---------- Kutilayotgan amallar (masalan, vaqt so'ralgan holat) ----------

def set_pending_action(user_id: str, action: str, task_id: int) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO pending_actions (user_id, action, task_id) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET action = excluded.action, task_id = excluded.task_id",
        (user_id, action, task_id),
    )
    conn.commit()
    conn.close()


def get_pending_action(user_id: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT action, task_id FROM pending_actions WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def clear_pending_action(user_id: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM pending_actions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ---------- Suhbat xotirasi ----------

def add_chat_message(user_id: str, role: str, message: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO chat_history (user_id, role, message, created) VALUES (?, ?, ?, ?)",
        (user_id, role, message, now_tashkent().strftime("%Y-%m-%d %H:%M")),
    )
    # Eski xabarlarni tozalab, faqat oxirgi CHAT_HISTORY_LIMIT tasini qoldiramiz.
    conn.execute(
        """
        DELETE FROM chat_history
        WHERE user_id = ? AND id NOT IN (
            SELECT id FROM chat_history WHERE user_id = ? ORDER BY id DESC LIMIT ?
        )
        """,
        (user_id, user_id, CHAT_HISTORY_LIMIT),
    )
    conn.commit()
    conn.close()


def get_chat_history(user_id: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, message FROM chat_history WHERE user_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()
    conn.close()
    return [{"role": row["role"], "message": row["message"]} for row in rows]


def clear_chat_history(user_id: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ==================== GEMINI API ====================

def _gemini_request(contents: list, system_instruction: str = ""):
    """Gemini API ga xom (raw) so'rov yuboradi. Xato bo'lsa None qaytaradi."""
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    payload = {
        "contents": contents,
        # Gemini 3.x modellari uchun "thinkingLevel" ishlatiladi (eski
        # "thinkingBudget" emas) — "minimal" tezroq javob beradi.
        "generationConfig": {"thinkingConfig": {"thinkingLevel": "minimal"}},
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    for attempt in range(2):  # 1 marta qayta urinish bilan, jami 2 urinish
        try:
            response = requests.post(GEMINI_URL, headers=headers, json=payload, timeout=60)
            if response.status_code != 200:
                safe_body = response.text.replace(GEMINI_API_KEY, "[KALIT_YASHIRILGAN]")[:800]
                logger.error(f"Gemini API xatosi: {response.status_code} - {safe_body}")
                return None
            result = response.json()
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except requests.exceptions.Timeout:
            logger.error(f"Gemini API xatosi: timeout (urinish {attempt + 1}/2)")
            if attempt == 1:
                return None
            continue
        except Exception as e:
            safe_error = str(e).replace(GEMINI_API_KEY, "[KALIT_YASHIRILGAN]")
            logger.error(f"Gemini API xatosi: {safe_error}")
            return None


def ask_gemini_chat(user_id: str, user_message: str) -> str:
    """Suhbat tarixini hisobga olgan holda AI yordamchidan javob oladi."""
    history = get_chat_history(user_id)
    contents = [
        {"role": ("user" if h["role"] == "user" else "model"), "parts": [{"text": h["message"]}]}
        for h in history
    ]
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    reply = _gemini_request(contents, ASSISTANT_SYSTEM_PROMPT)
    if reply is None:
        return "Kechirasiz, hozir AI bilan bog'lanishda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring."

    add_chat_message(user_id, "user", user_message)
    add_chat_message(user_id, "model", reply)
    return reply


def extract_datetime(text: str) -> dict:
    """Matndan sana/vaqtni aniqlaydi. {"has_time": bool, "datetime": "YYYY-MM-DD HH:MM"|None, "display": str|None}"""
    current = now_tashkent().strftime("%Y-%m-%d %H:%M (%A)")
    system_instruction = (
        f"Joriy sana va vaqt (Toshkent, UTC+5): {current}. "
        "Foydalanuvchi matnidan sana/vaqtga oid ishorani top (masalan 'ertaga', "
        "'soat 15:00da', 'dushanba kuni', '20-avgust'). Agar aniq yoki taxminiy "
        "vaqt topsang, uni joriy sanaga nisbatan kelajakdagi to'liq sana-vaqtga "
        "aylantir. Agar vaqt haqida hech qanday ishora bo'lmasa, has_time ni "
        "false qil. FAQAT quyidagi JSON formatida javob ber, boshqa hech narsa "
        "yozma (izoh, kod bloki belgilari ham kerak emas):\n"
        '{"has_time": true yoki false, "datetime": "YYYY-MM-DD HH:MM" yoki null, '
        '"display": "odam o\'qiydigan qisqa format" yoki null}'
    )
    contents = [{"role": "user", "parts": [{"text": text}]}]
    reply = _gemini_request(contents, system_instruction)
    if reply is None:
        return {"has_time": False, "datetime": None, "display": None}

    cleaned = reply.strip().strip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    try:
        data = json.loads(cleaned)
        # Sana formatini tekshiramiz.
        if data.get("has_time") and data.get("datetime"):
            datetime.strptime(data["datetime"], "%Y-%m-%d %H:%M")
        return data
    except Exception:
        return {"has_time": False, "datetime": None, "display": None}


ASSISTANT_SYSTEM_PROMPT = (
    "Sen foydalanuvchining shaxsiy yordamchisisan. O'zbek tilida, qisqa, aniq va "
    "do'stona javob ber. Oldingi xabarlarni context sifatida hisobga ol. Agar "
    "foydalanuvchi vazifa haqida gapirsa, unga amaliy maslahat ber va agar mos "
    "bo'lsa, /task buyrug'idan foydalanishni tavsiya qil."
)

# ==================== TELEGRAM BUYRUQLARI ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Salom! 👋 Men sizning shaxsiy yordamchingiz va vazifa rejalashtiruvchi botman.\n\n"
        "🧠 Menga oddiy xabar yozing — AI sifatida javob beraman, oldingi xabarlarimizni "
        "ham eslab qolaman.\n\n"
        "📋 Buyruqlar:\n"
        "/task <matn> — yangi vazifa qo'shish (agar matnda vaqt bo'lsa, eslatma o'zi taklif qilinadi)\n"
        "/list — barcha vazifalaringizni ko'rish\n"
        "/clear — bajarilgan vazifalarni tozalash\n"
        "/forget — AI bilan suhbat xotirasini tozalash\n"
        "/help — yordam"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    clear_chat_history(user_id)
    await update.message.reply_text("🧹 Suhbat xotirasi tozalandi. Yangidan boshlaymiz!")


async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    task_text = " ".join(context.args)
    if not task_text:
        await update.message.reply_text("Foydalanish: /task Hisobot tayyorlash")
        return

    task_id = add_user_task(user_id, task_text)
    await update.message.reply_text(f"✅ Vazifa qo'shildi: {task_text}")

    await update.message.reply_chat_action("typing")
    info = extract_datetime(task_text)

    if info.get("has_time") and info.get("datetime"):
        set_proposed_reminder(task_id, info["datetime"])
        display = info.get("display") or info["datetime"]
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Ha, eslatma qo'y", callback_data=f"remindyes_{task_id}"),
            InlineKeyboardButton("❌ Yo'q, kerak emas", callback_data=f"remindno_{task_id}"),
        ]])
        await update.message.reply_text(
            f"🕐 Matningizda vaqt topdim: {display}\nShu vaqtga eslatma qo'yaymi?",
            reply_markup=keyboard,
        )
    else:
        set_pending_action(user_id, "awaiting_time", task_id)
        await update.message.reply_text(
            "🔔 Bu vazifa uchun bildirishnoma vaqtini xohlaysizmi?\n"
            "Vaqtni yozing (masalan: 'ertaga soat 10:00' yoki '2026-08-20 15:00'), "
            "yoki kerak bo'lmasa 'yo'q' deb yozing."
        )


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    tasks = get_user_tasks(user_id)

    if not tasks:
        await update.message.reply_text("Sizda hozircha vazifalar yo'q. /task orqali qo'shing.")
        return

    for task in tasks:
        status = "✅" if task["done"] else "🔲"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Bajarildi" if not task["done"] else "Bekor qilish",
                callback_data=f"toggle_{task['id']}",
            ),
            InlineKeyboardButton("O'chirish", callback_data=f"delete_{task['id']}"),
        ]])
        await update.message.reply_text(
            f"{status} {task['text']}\n🕐 {task['created']}",
            reply_markup=keyboard,
        )


async def clear_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    removed = clear_done_tasks(user_id)
    await update.message.reply_text(f"🗑️ {removed} ta bajarilgan vazifa tozalandi.")


async def debug_gemini(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vaqtinchalik diagnostika: generateContent so'rovining to'liq javobini ko'rsatadi."""
    await update.message.reply_chat_action("typing")
    try:
        response = requests.post(
            GEMINI_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY,
            },
            json={"contents": [{"parts": [{"text": "Salom"}]}]},
            timeout=30,
        )
        safe_body = response.text.replace(GEMINI_API_KEY, "[YASHIRILGAN]")[:1500]
        await update.message.reply_text(
            f"URL: {GEMINI_URL}\n\nStatus kod: {response.status_code}\n\nJavob:\n{safe_body}"
        )
    except Exception as e:
        safe_error = str(e).replace(GEMINI_API_KEY, "[YASHIRILGAN]")
        await update.message.reply_text(f"Xato: {safe_error}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    action, id_str = query.data.split("_")
    task_id = int(id_str)

    if action in ("remindyes", "remindno"):
        task = get_task(task_id)
        if task is None:
            await query.edit_message_text("Bu vazifa allaqachon o'chirilgan.")
            return
        if action == "remindyes" and task["proposed_remind_at"]:
            create_reminder(user_id, task_id, task["text"], task["proposed_remind_at"])
            set_proposed_reminder(task_id, None)
            await query.edit_message_text(
                f"🔔 Eslatma o'rnatildi: {task['text']}\n🕐 {task['proposed_remind_at']}"
            )
        else:
            set_proposed_reminder(task_id, None)
            await query.edit_message_text("Yaxshi, eslatma qo'yilmadi.")
        return

    tasks = get_user_tasks(user_id)
    task = next((t for t in tasks if t["id"] == task_id), None)
    if task is None:
        await query.edit_message_text("Bu vazifa allaqachon o'chirilgan.")
        return

    if action == "toggle":
        new_done = not task["done"]
        toggle_task(task_id, new_done)
        status = "✅" if new_done else "🔲"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Bekor qilish" if new_done else "Bajarildi",
                callback_data=f"toggle_{task_id}",
            ),
            InlineKeyboardButton("O'chirish", callback_data=f"delete_{task_id}"),
        ]])
        await query.edit_message_text(
            f"{status} {task['text']}\n🕐 {task['created']}",
            reply_markup=keyboard,
        )
    elif action == "delete":
        delete_task(task_id)
        await query.edit_message_text(f"🗑️ O'chirildi: {task['text']}")


async def chat_with_ai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Oddiy matnli xabarlarni qayta ishlaydi: eslatma vaqtini kutish yoki AI suhbat."""
    user_id = str(update.effective_user.id)
    user_message = update.message.text

    pending = get_pending_action(user_id)
    if pending and pending["action"] == "awaiting_time":
        task_id = pending["task_id"]
        task = get_task(task_id)
        clear_pending_action(user_id)

        if user_message.strip().lower() in ("yo'q", "yoq", "kerak emas", "yo'q rahmat"):
            await update.message.reply_text("Yaxshi, eslatma qo'yilmadi.")
            return

        await update.message.reply_chat_action("typing")
        info = extract_datetime(user_message)
        if info.get("has_time") and info.get("datetime") and task:
            create_reminder(user_id, task_id, task["text"], info["datetime"])
            display = info.get("display") or info["datetime"]
            await update.message.reply_text(
                f"🔔 Eslatma o'rnatildi: {task['text']}\n🕐 {display}"
            )
        else:
            await update.message.reply_text(
                "Kechirasiz, vaqtni aniqlay olmadim. Masalan shunday yozing: "
                "'ertaga soat 10:00' yoki '2026-08-20 15:00'."
            )
        return

    await update.message.reply_chat_action("typing")
    reply = ask_gemini_chat(user_id, user_message)
    await update.message.reply_text(reply)


# ==================== ESLATMALARNI YUBORISH ====================

async def check_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    now_str = now_tashkent().strftime("%Y-%m-%d %H:%M")
    due = get_due_reminders(now_str)
    for reminder in due:
        try:
            await context.bot.send_message(
                chat_id=int(reminder["user_id"]),
                text=f"🔔 Eslatma: {reminder['task_text']}",
            )
        except Exception as e:
            logger.error(f"Eslatma yuborishda xato: {e}")
        finally:
            mark_reminder_sent(reminder["id"])


# ==================== ASOSIY FUNKSIYA ====================

def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN muhit o'zgaruvchisi topilmadi. README.md ni ko'ring.")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY muhit o'zgaruvchisi topilmadi. README.md ni ko'ring.")

    init_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("task", add_task))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CommandHandler("clear", clear_done))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("debug", debug_gemini))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_with_ai))

    if app.job_queue is not None:
        app.job_queue.run_repeating(check_reminders, interval=30, first=10)
    else:
        logger.warning(
            "JobQueue mavjud emas — eslatmalar ishlamaydi. "
            "requirements.txt da 'python-telegram-bot[job-queue]' borligini tekshiring."
        )

    logger.info("Bot ishga tushmoqda...")
    app.run_polling()


if __name__ == "__main__":
    main()
