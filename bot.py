# -*- coding: utf-8 -*-
"""
بوت تليجرام - مساعد عقاري
تشغيل: python bot.py
يتطلب متغير بيئة BOT_TOKEN (توكن البوت من @BotFather)
"""

import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import database as db
import ai_assistant

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")

DEAL_TYPES = ["بيع", "إيجار"]
CATEGORIES = ["شقة", "فيلا", "أرض", "محل تجاري", "مكتب"]

# ---------- Conversation states ----------
(ADD_DEAL, ADD_CATEGORY, ADD_CITY, ADD_PRICE, ADD_AREA,
 ADD_ROOMS, ADD_DESC, ADD_PHOTO, ADD_PHONE) = range(9)

(SEARCH_DEAL, SEARCH_CATEGORY, SEARCH_CITY, SEARCH_MINPRICE, SEARCH_MAXPRICE) = range(9, 14)


# ================= أدوات مساعدة =================
def main_menu_kb():
    kb = [
        [InlineKeyboardButton("🤖 اسأل المساعد الذكي", callback_data="ask_ai")],
        [InlineKeyboardButton("🏠 تصفح العقارات", callback_data="browse")],
        [InlineKeyboardButton("🔍 بحث متقدم", callback_data="search")],
        [InlineKeyboardButton("➕ أضف عقار (للوكلاء)", callback_data="add_start")],
        [InlineKeyboardButton("📋 عقاراتي", callback_data="my_props")],
        [InlineKeyboardButton("☎️ تواصل معنا", callback_data="contact")],
    ]
    return InlineKeyboardMarkup(kb)


def choices_kb(options, prefix, back_cb="main_menu"):
    kb = [[InlineKeyboardButton(o, callback_data=f"{prefix}:{o}")] for o in options]
    kb.append([InlineKeyboardButton("⬅️ رجوع", callback_data=back_cb)])
    return InlineKeyboardMarkup(kb)


def format_property(p: dict) -> str:
    return (
        f"🏡 *عقار #{p['id']}*\n"
        f"النوع: {p['deal_type']} - {p['category']}\n"
        f"المدينة: {p['city']}\n"
        f"السعر: {p['price']:,.0f}\n"
        f"المساحة: {p['area'] or '-'} م²\n"
        f"الغرف: {p['rooms'] or '-'}\n"
        f"الوصف: {p['description'] or '-'}\n"
        f"للتواصل: {p['phone'] or '-'}"
    )


# ================= القائمة الرئيسية =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_agent(user.id, user.full_name)
    text = "أهلاً بك في المساعد العقاري 🏠\nاختر من القائمة:"
    if update.message:
        await update.message.reply_text(text, reply_markup=main_menu_kb())
    else:
        await update.callback_query.edit_message_text(text, reply_markup=main_menu_kb())


async def main_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await start(update, context)


async def contact_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "للتواصل مع فريق الدعم، راسلنا هنا مباشرة وسيتم الرد عليك.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]]
        ),
    )


# ================= المساعد الذكي =================
async def ask_ai_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "اكتب سؤالك مباشرة بلغتك الطبيعية، مثلاً:\n"
        "«بدي شقة للإيجار بدمشق بسعر أقل من 500 دولار»\n"
        "وسأبحث لك عن أفضل الخيارات المتوفرة.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]]),
    )


async def ai_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # يتجاهل أي رسالة ضمن محادثة نشطة (إضافة عقار / بحث متقدم) لأن تلك المعالجات تُعالَج أولاً
    user_text = update.message.text.strip()
    thinking = await update.message.reply_text("🤖 لحظة، أبحث لك عن أفضل الخيارات...")
    answer, matched = ai_assistant.ask_ai(user_text)
    kb = None
    if matched:
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"عرض تفاصيل #{p['id']}", callback_data=f"view:{p['id']}")] for p in matched]
        )
    await thinking.edit_text(answer, reply_markup=kb)


# ================= تصفح العقارات =================
async def browse_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("اختر نوع العملية:", reply_markup=choices_kb(DEAL_TYPES, "bdeal"))


async def browse_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    deal = q.data.split(":", 1)[1]
    context.user_data["b_deal"] = deal
    await q.edit_message_text("اختر نوع العقار:", reply_markup=choices_kb(CATEGORIES, "bcat", back_cb="browse"))


async def browse_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    category = q.data.split(":", 1)[1]
    deal = context.user_data.get("b_deal")
    results = db.search_properties(deal_type=deal, category=category, limit=10)
    if not results:
        await q.edit_message_text(
            "لا توجد عقارات مطابقة حالياً.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]]),
        )
        return
    kb = [
        [InlineKeyboardButton(f"#{p['id']} - {p['city']} - {p['price']:,.0f}", callback_data=f"view:{p['id']}")]
        for p in results
    ]
    kb.append([InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")])
    await q.edit_message_text("نتائج البحث:", reply_markup=InlineKeyboardMarkup(kb))


async def view_property(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    prop_id = int(q.data.split(":", 1)[1])
    p = db.get_property(prop_id)
    if not p:
        await q.edit_message_text("هذا العقار لم يعد متوفراً.")
        return
    caption = format_property(p)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="main_menu")]])
    if p["photo_file_id"]:
        await q.message.reply_photo(photo=p["photo_file_id"], caption=caption, parse_mode="Markdown", reply_markup=kb)
    else:
        await q.message.reply_text(caption, parse_mode="Markdown", reply_markup=kb)


# ================= البحث المتقدم =================
async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["s_filters"] = {}
    await q.edit_message_text("نوع العملية؟", reply_markup=choices_kb(DEAL_TYPES, "sdeal"))
    return SEARCH_DEAL


async def search_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["s_filters"]["deal_type"] = q.data.split(":", 1)[1]
    await q.edit_message_text("نوع العقار؟", reply_markup=choices_kb(CATEGORIES, "scat"))
    return SEARCH_CATEGORY


async def search_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["s_filters"]["category"] = q.data.split(":", 1)[1]
    await q.edit_message_text("اكتب اسم المدينة (أو أرسل - لتجاهل هذا الشرط):")
    return SEARCH_CITY


async def search_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "-":
        context.user_data["s_filters"]["city"] = text
    await update.message.reply_text("الحد الأدنى للسعر؟ (أرسل - لتجاهل)")
    return SEARCH_MINPRICE


async def search_minprice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "-":
        try:
            context.user_data["s_filters"]["min_price"] = float(text)
        except ValueError:
            await update.message.reply_text("رجاءً أرسل رقم صحيح، أو -.")
            return SEARCH_MINPRICE
    await update.message.reply_text("الحد الأعلى للسعر؟ (أرسل - لتجاهل)")
    return SEARCH_MAXPRICE


async def search_maxprice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "-":
        try:
            context.user_data["s_filters"]["max_price"] = float(text)
        except ValueError:
            await update.message.reply_text("رجاءً أرسل رقم صحيح، أو -.")
            return SEARCH_MAXPRICE
    filters_ = context.user_data.get("s_filters", {})
    results = db.search_properties(**filters_, limit=10)
    if not results:
        await update.message.reply_text("لا توجد نتائج مطابقة.", reply_markup=main_menu_kb())
        return ConversationHandler.END
    kb = [
        [InlineKeyboardButton(f"#{p['id']} - {p['city']} - {p['price']:,.0f}", callback_data=f"view:{p['id']}")]
        for p in results
    ]
    kb.append([InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="main_menu")])
    await update.message.reply_text("نتائج البحث:", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


# ================= إضافة عقار (للوكلاء) =================
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["new_prop"] = {}
    await q.edit_message_text("نوع العملية؟", reply_markup=choices_kb(DEAL_TYPES, "adeal"))
    return ADD_DEAL


async def add_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["new_prop"]["deal_type"] = q.data.split(":", 1)[1]
    await q.edit_message_text("نوع العقار؟", reply_markup=choices_kb(CATEGORIES, "acat"))
    return ADD_CATEGORY


async def add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["new_prop"]["category"] = q.data.split(":", 1)[1]
    await q.edit_message_text("اكتب اسم المدينة / المنطقة:")
    return ADD_CITY


async def add_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_prop"]["city"] = update.message.text.strip()
    await update.message.reply_text("السعر؟ (رقم فقط)")
    return ADD_PRICE


async def add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["new_prop"]["price"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("رجاءً أرسل رقم صحيح للسعر.")
        return ADD_PRICE
    await update.message.reply_text("المساحة بالمتر؟ (أرسل - لتجاهل)")
    return ADD_AREA


async def add_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["new_prop"]["area"] = None if text == "-" else float(text) if text.replace(".", "", 1).isdigit() else None
    await update.message.reply_text("عدد الغرف؟ (أرسل - لتجاهل)")
    return ADD_ROOMS


async def add_rooms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["new_prop"]["rooms"] = None if text == "-" else int(text) if text.isdigit() else None
    await update.message.reply_text("اكتب وصف مختصر للعقار:")
    return ADD_DESC


async def add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_prop"]["description"] = update.message.text.strip()
    await update.message.reply_text("أرسل صورة للعقار (أو اكتب - لتجاهل):")
    return ADD_PHOTO


async def add_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data["new_prop"]["photo_file_id"] = update.message.photo[-1].file_id
    else:
        context.user_data["new_prop"]["photo_file_id"] = None
    await update.message.reply_text("رقم هاتف التواصل؟")
    return ADD_PHONE


async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_prop"]["phone"] = update.message.text.strip()
    p = context.user_data["new_prop"]
    prop_id = db.add_property(
        agent_id=update.effective_user.id,
        deal_type=p["deal_type"],
        category=p["category"],
        city=p["city"],
        price=p["price"],
        area=p.get("area"),
        rooms=p.get("rooms"),
        description=p.get("description"),
        photo_file_id=p.get("photo_file_id"),
        phone=p.get("phone"),
    )
    await update.message.reply_text(f"✅ تمت إضافة العقار برقم #{prop_id} بنجاح.", reply_markup=main_menu_kb())
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم الإلغاء.", reply_markup=main_menu_kb())
    return ConversationHandler.END


# ================= عقاراتي (إدارة الوكيل) =================
async def my_props(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    props = db.list_agent_properties(update.effective_user.id)
    if not props:
        await q.edit_message_text(
            "لم تقم بإضافة أي عقار بعد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]]),
        )
        return
    kb = [
        [InlineKeyboardButton(f"🗑 حذف #{p['id']} - {p['city']}", callback_data=f"del:{p['id']}")]
        for p in props
    ]
    kb.append([InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")])
    await q.edit_message_text("عقاراتك (اضغط للحذف):", reply_markup=InlineKeyboardMarkup(kb))


async def delete_prop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    prop_id = int(q.data.split(":", 1)[1])
    ok = db.delete_property(prop_id, update.effective_user.id)
    msg = "تم الحذف." if ok else "تعذر الحذف."
    await q.edit_message_text(msg, reply_markup=main_menu_kb())


# ================= تشغيل البوت =================
def build_app():
    db.init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(main_menu_cb, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(contact_cb, pattern="^contact$"))
    app.add_handler(CallbackQueryHandler(ask_ai_cb, pattern="^ask_ai$"))

    # تصفح
    app.add_handler(CallbackQueryHandler(browse_start, pattern="^browse$"))
    app.add_handler(CallbackQueryHandler(browse_deal, pattern="^bdeal:"))
    app.add_handler(CallbackQueryHandler(browse_category, pattern="^bcat:"))
    app.add_handler(CallbackQueryHandler(view_property, pattern="^view:"))

    # عقاراتي
    app.add_handler(CallbackQueryHandler(my_props, pattern="^my_props$"))
    app.add_handler(CallbackQueryHandler(delete_prop, pattern="^del:"))

    # بحث متقدم (Conversation)
    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_start, pattern="^search$")],
        states={
            SEARCH_DEAL: [CallbackQueryHandler(search_deal, pattern="^sdeal:")],
            SEARCH_CATEGORY: [CallbackQueryHandler(search_category, pattern="^scat:")],
            SEARCH_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_city)],
            SEARCH_MINPRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_minprice)],
            SEARCH_MAXPRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_maxprice)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(search_conv)

    # إضافة عقار (Conversation)
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_start, pattern="^add_start$")],
        states={
            ADD_DEAL: [CallbackQueryHandler(add_deal, pattern="^adeal:")],
            ADD_CATEGORY: [CallbackQueryHandler(add_category, pattern="^acat:")],
            ADD_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_city)],
            ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_price)],
            ADD_AREA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_area)],
            ADD_ROOMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_rooms)],
            ADD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_desc)],
            ADD_PHOTO: [MessageHandler((filters.PHOTO | filters.TEXT) & ~filters.COMMAND, add_photo)],
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(add_conv)

    # المساعد الذكي: يلتقط أي رسالة نصية حرة لم تُعالج ضمن قائمة أو محادثة أعلاه
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_free_text))

    return app


if __name__ == "__main__":
    application = build_app()

    PORT = int(os.environ.get("PORT", 10000))
    RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")  # يضبطه Render تلقائياً على الخطة المجانية

    if RENDER_EXTERNAL_URL:
        # وضع Webhook: يعمل كخدمة ويب مجانية على Render (بدلاً من polling)
        log.info("Starting in webhook mode (Render)...")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}",
        )
    else:
        # وضع Polling: للتشغيل المحلي على جهازك
        log.info("Starting in polling mode (local)...")
        application.run_polling()
