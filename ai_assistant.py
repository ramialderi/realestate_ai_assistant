# -*- coding: utf-8 -*-
"""
طبقة الذكاء الاصطناعي: تفهم سؤال الزائر بلغة طبيعية، تبحث في قاعدة البيانات،
وتولّد رداً طبيعياً بالعربية بالاعتماد فقط على العقارات الموجودة فعلياً.

يستخدم Groq API (مجاني، حد يومي سخي) - احصل على مفتاح من:
https://console.groq.com/keys
"""

import json
import os

import requests

import database as db

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"

EXTRACT_SYSTEM = """أنت أداة استخراج بيانات فقط. حوّل سؤال المستخدم عن العقارات إلى JSON فقط بدون أي شرح أو نص إضافي، بالشكل التالي بالضبط:
{"deal_type": "بيع أو إيجار أو null", "category": "شقة أو فيلا أو أرض أو محل تجاري أو مكتب أو null", "city": "اسم المدينة أو null", "min_price": رقم أو null, "max_price": رقم أو null}
إن لم يذكر المستخدم أحد الحقول اجعله null. أرجع JSON فقط."""

ANSWER_SYSTEM = """أنت مساعد عقاري ودود يرد بالعربية. اعتمد فقط على قائمة العقارات المزوّدة لك في الرسالة - لا تختلق أي عقار أو سعر غير موجود فيها.
إن كانت القائمة فارغة، اعتذر بلطف وأخبر المستخدم أنه لا توجد عقارات مطابقة حالياً، واقترح عليه تعديل الطلب (مدينة أخرى، ميزانية مختلفة...).
إن وُجدت عقارات، لخّص أفضل الخيارات المطابقة بإيجاز (لا تتجاوز 5 عقارات) مع ذكر رقم كل عقار (#) والمدينة والسعر، وأضف جملة ودية تدعو المستخدم للسؤال عن التفاصيل."""


def _call_groq(messages, temperature=0.2):
    if not GROQ_API_KEY:
        return None
    try:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL, "messages": messages, "temperature": temperature},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Groq API error: {e}")
        return None


def _extract_filters(user_text: str) -> dict:
    raw = _call_groq(
        [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": user_text},
        ],
        temperature=0,
    )
    if not raw:
        return {}
    cleaned = raw.strip().strip("`")
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return {}
    filters = {}
    if data.get("deal_type") in ("بيع", "إيجار"):
        filters["deal_type"] = data["deal_type"]
    if data.get("category"):
        filters["category"] = data["category"]
    if data.get("city"):
        filters["city"] = data["city"]
    if isinstance(data.get("min_price"), (int, float)):
        filters["min_price"] = data["min_price"]
    if isinstance(data.get("max_price"), (int, float)):
        filters["max_price"] = data["max_price"]
    return filters


def _format_results(results):
    lines = []
    for p in results:
        lines.append(
            f"#{p['id']} | {p['deal_type']} | {p['category']} | {p['city']} | "
            f"السعر: {p['price']:,.0f} | المساحة: {p['area'] or '-'} | الغرف: {p['rooms'] or '-'} | "
            f"الوصف: {p['description'] or '-'}"
        )
    return "\n".join(lines) if lines else "لا توجد عقارات مطابقة في قاعدة البيانات حالياً."


def ask_ai(user_text: str):
    """
    يرجع (answer_text, matched_properties_list)
    إن لم يكن GROQ_API_KEY مضبوطاً، يرجع رسالة توضح ذلك.
    """
    if not GROQ_API_KEY:
        return (
            "ميزة المساعد الذكي غير مفعّلة بعد. اطلب من مدير البوت ضبط GROQ_API_KEY "
            "(مفتاح مجاني من https://console.groq.com/keys).",
            [],
        )

    filters = _extract_filters(user_text)
    results = db.search_properties(**filters, limit=5)

    answer = _call_groq(
        [
            {"role": "system", "content": ANSWER_SYSTEM},
            {
                "role": "user",
                "content": f"سؤال المستخدم: {user_text}\n\nالعقارات المتوفرة المطابقة:\n{_format_results(results)}",
            },
        ],
        temperature=0.4,
    )

    if not answer:
        answer = "حدث خطأ مؤقت في المساعد الذكي، جرّب مرة أخرى بعد قليل."

    return answer, results
