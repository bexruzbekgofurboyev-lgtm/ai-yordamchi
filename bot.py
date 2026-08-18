"""
AI Yordamchi va Vazifa Rejalashtiruvchi Telegram Bot
Gemini API asosida ishlaydi.

O'rnatish va ishga tushirish yo'riqnomasi README.md faylida.
"""

import json
import os
import logging
from datetime import datetime
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
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

DATA_FILE = Path("tasks_data.json")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ==================== MA'LUMOTLARNI SAQLASH ====================

def load_data() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user_tasks(user_id: str) -> list:
    data = load_data()
    return data.get(user_id, [])


def save_user_tasks(user_id: str, tasks: list) -> None:
    data = load_data()
    data[user_id] = tasks
    save_data(data)


# ==================== GEMINI API ====================

def ask_gemini(prompt: str, system_instruction: str = "") -> str:
    """Gemini API ga so'rov yuboradi va javob matnini qaytaradi."""
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    try:
        response = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Gemini API xatosi: {e}")
        return "Kechirasiz, hozir AI bilan bog'lanishda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring."


ASSISTANT_SYSTEM_PROMPT = (
    "Sen foydalanuvchining shaxsiy yordamchisisan. O'zbek tilida, qisqa, aniq va "
    "do'stona javob ber. Agar foydalanuvchi vazifa yoki reja haqida gapirsa, unga "
    "amaliy maslahat ber va agar mos bo'lsa, /task buyrug'idan foydalanishni tavsiya qil."
)

TASK_BREAKDOWN_SYSTEM_PROMPT = (
    "Foydalanuvchi bergan katta vazifani 3-6 ta kichik, aniq va bajarish mumkin bo'lgan "
    "bosqichlarga bo'l. Har bir bosqichni yangi qatordan, faqat matn sifatida, raqamlarsiz "
    "va qo'shimcha izohlarsiz yoz. Faqat bosqichlar ro'yxatini qaytar, boshqa hech narsa yozma."
)

# ==================== TELEGRAM BUYRUQLARI ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Salom! 👋 Men sizning shaxsiy yordamchingiz va vazifa rejalashtiruvchi botman.\n\n"
        "🧠 Menga oddiy xabar yozing — AI sifatida javob beraman va maslahat beraman.\n\n"
        "📋 Buyruqlar:\n"
        "/task <matn> — yangi vazifa qo'shish\n"
        "/plan <matn> — katta vazifani AI yordamida bosqichlarga bo'lib qo'shish\n"
        "/list — barcha vazifalaringizni ko'rish\n"
        "/clear — bajarilgan vazifalarni tozalash\n"
        "/help — yordam"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    task_text = " ".join(context.args)
    if not task_text:
        await update.message.reply_text("Foydalanish: /task Hisobot tayyorlash")
        return

    tasks = get_user_tasks(user_id)
    tasks.append({
        "text": task_text,
        "done": False,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    save_user_tasks(user_id, tasks)
    await update.message.reply_text(f"✅ Vazifa qo'shildi: {task_text}")


async def plan_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    goal_text = " ".join(context.args)
    if not goal_text:
        await update.message.reply_text("Foydalanish: /plan Marketing kampaniyasini ishga tushirish")
        return

    await update.message.reply_chat_action("typing")
    breakdown = ask_gemini(goal_text, TASK_BREAKDOWN_SYSTEM_PROMPT)
    steps = [s.strip("-• ") for s in breakdown.split("\n") if s.strip()]

    tasks = get_user_tasks(user_id)
    for step in steps:
        tasks.append({
            "text": step,
            "done": False,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
    save_user_tasks(user_id, tasks)

    reply = f"🎯 '{goal_text}' uchun {len(steps)} ta bosqich qo'shildi:\n\n"
    reply += "\n".join(f"• {s}" for s in steps)
    await update.message.reply_text(reply)


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    tasks = get_user_tasks(user_id)

    if not tasks:
        await update.message.reply_text("Sizda hozircha vazifalar yo'q. /task orqali qo'shing.")
        return

    for i, task in enumerate(tasks):
        status = "✅" if task["done"] else "🔲"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Bajarildi" if not task["done"] else "Bekor qilish",
                callback_data=f"toggle_{i}",
            ),
            InlineKeyboardButton("O'chirish", callback_data=f"delete_{i}"),
        ]])
        await update.message.reply_text(
            f"{status} {task['text']}\n🕐 {task['created']}",
            reply_markup=keyboard,
        )


async def clear_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    tasks = get_user_tasks(user_id)
    remaining = [t for t in tasks if not t["done"]]
    removed = len(tasks) - len(remaining)
    save_user_tasks(user_id, remaining)
    await update.message.reply_text(f"🗑️ {removed} ta bajarilgan vazifa tozalandi.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    action, idx_str = query.data.split("_")
    idx = int(idx_str)

    tasks = get_user_tasks(user_id)
    if idx >= len(tasks):
        await query.edit_message_text("Bu vazifa allaqachon o'chirilgan.")
        return

    if action == "toggle":
        tasks[idx]["done"] = not tasks[idx]["done"]
        save_user_tasks(user_id, tasks)
        status = "✅" if tasks[idx]["done"] else "🔲"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Bekor qilish" if tasks[idx]["done"] else "Bajarildi",
                callback_data=f"toggle_{idx}",
            ),
            InlineKeyboardButton("O'chirish", callback_data=f"delete_{idx}"),
        ]])
        await query.edit_message_text(
            f"{status} {tasks[idx]['text']}\n🕐 {tasks[idx]['created']}",
            reply_markup=keyboard,
        )
    elif action == "delete":
        removed_text = tasks.pop(idx)["text"]
        save_user_tasks(user_id, tasks)
        await query.edit_message_text(f"🗑️ O'chirildi: {removed_text}")


async def chat_with_ai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Oddiy matnli xabarlarni Gemini AI ga yuboradi."""
    await update.message.reply_chat_action("typing")
    user_message = update.message.text
    reply = ask_gemini(user_message, ASSISTANT_SYSTEM_PROMPT)
    await update.message.reply_text(reply)


# ==================== ASOSIY FUNKSIYA ====================

def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN muhit o'zgaruvchisi topilmadi. README.md ni ko'ring.")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY muhit o'zgaruvchisi topilmadi. README.md ni ko'ring.")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("task", add_task))
    app.add_handler(CommandHandler("plan", plan_task))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CommandHandler("clear", clear_done))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_with_ai))

    logger.info("Bot ishga tushmoqda...")
    app.run_polling()


if __name__ == "__main__":
    main()
