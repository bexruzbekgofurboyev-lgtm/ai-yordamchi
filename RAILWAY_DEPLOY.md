# Railway'ga Botni Joylashtirish (Deploy) Yo'riqnomasi

Bu yo'riqnoma botingizni Railway'da 24/7 bepul ishlashini sozlab beradi.

## Kerakli fayllar

Quyidagi 4 ta fayl bitta papkada bo'lishi kerak (barchasi tayyorlangan):

- `bot.py` — botning asosiy kodi
- `requirements.txt` — kerakli kutubxonalar ro'yxati
- `Procfile` — Railway'ga botni qanday ishga tushirishni aytadi
- `README.md` — yordam uchun (majburiy emas)

## 1-qadam: GitHub'ga yuklash

Railway kodni GitHub orqali oladi, shuning uchun avval GitHub'da repository yaratish kerak.

1. [github.com](https://github.com) da hisobingiz bo'lmasa, ro'yxatdan o'ting (bepul).
2. Yangi repository yarating: yuqori o'ngdagi **+** tugmasi → **New repository**.
3. Nom bering, masalan `ai-yordamchi-bot`. **Private** qilib qo'yishingiz mumkin (xavfsizroq).
4. **Create repository** bosing.
5. Yuklab olgan 4 ta faylni (`bot.py`, `requirements.txt`, `Procfile`, `README.md`) shu
   repository'ga yuklang — sahifada **"uploading an existing file"** havolasini bosib,
   fayllarni sudrab tashlang (drag & drop), so'ng **Commit changes** bosing.

> ⚠️ Diqqat: API kalitlaringizni hech qachon kod ichiga yozmang va GitHub'ga yuklamang!
> Ular Railway sozlamalarida alohida saqlanadi (quyida ko'rsatilgan).

## 2-qadam: Railway'da hisob ochish

1. [railway.app](https://railway.app) ga o'ting.
2. **Login with GitHub** orqali kiring va ruxsat bering.

## 3-qadam: Yangi loyiha yaratish

1. Railway boshqaruv panelida **New Project** bosing.
2. **Deploy from GitHub repo** ni tanlang.
3. Yaratgan `ai-yordamchi-bot` repository'ni tanlang.
4. Railway avtomatik ravishda `requirements.txt` va `Procfile` ni topib,
   kerakli kutubxonalarni o'rnatishni boshlaydi.

## 4-qadam: API kalitlarni qo'shish (Environment Variables)

1. Loyiha ochilgach, **Variables** bo'limiga o'ting.
2. **+ New Variable** tugmasini bosing va quyidagi ikkitasini qo'shing:

   | Kalit nomi | Qiymati |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | BotFather'dan olgan tokeningiz |
   | `GEMINI_API_KEY` | Gemini API kalitingiz |

3. Har birini kiritgach **Add** bosing.

## 5-qadam: Ishga tushirish

1. Railway avtomatik ravishda qayta deploy qiladi (Variables qo'shilgach).
2. **Deployments** bo'limida jarayonni kuzatishingiz mumkin — yashil belgi
   chiqsa, bot ishga tushgan.
3. **View Logs** tugmasi orqali terminal chiqishini ko'rishingiz mumkin —
   "Bot ishga tushmoqda..." xabarini ko'rsangiz, tayyor!
4. Telegram'da botingizga o'tib `/start` bosing.

## Muhim eslatmalar

- **Bepul limit:** Railway har oy ma'lum miqdorda bepul soat beradi (odatda
  kichik botlar uchun yetarli). Limit tugasa, kartani bog'lash yoki kutish
  kerak bo'lishi mumkin — bu Railway'ning joriy tarifiga bog'liq, sozlamalar
  bo'limida tekshirib turing.
- **Kodni yangilash:** Kelajakda `bot.py` ni o'zgartirsangiz, shunchaki
  GitHub'dagi faylni yangilang (commit qiling) — Railway avtomatik ravishda
  qayta deploy qiladi.
- **Ma'lumotlar saqlanishi:** `tasks_data.json` fayli Railway serverida
  saqlanadi, lekin ba'zi bepul tariflar qayta ishga tushganda faylni
  tozalashi mumkin. Agar vazifalar yo'qolib qolsa, buni bildiring — sizga
  doimiy saqlaydigan (masalan, Railway'ning ma'lumotlar bazasi) yechimga
  o'tkazib beraman.

## Muammo yuzaga kelsa

- **Deploy xato beryapti** — **Deployments** → so'nggi urinish → **View Logs**
  orqali xato matnini ko'ring.
- **"ModuleNotFoundError"** — `requirements.txt` fayli to'g'ri yuklanganini
  tekshiring.
- **Bot javob bermayapti** — Variables bo'limida ikkala kalit ham to'g'ri
  yozilganini (bo'sh joysiz, qo'shtirnoqsiz) tekshiring.
