"""Structured, human-friendly error catalog for the Telegram reposter.

Every failure the backend can surface is described once here: a stable ``code``,
a short ``title``, a plain-language ``message``, an actionable ``hint`` and an
ordered list of ``steps`` to fix it. Both English (``en``) and Arabic (``ar``)
strings are provided so the dashboard can render the same error in either
language without the frontend hard-coding messages.

The API layer converts exceptions into this structure via
:func:`from_exception`, and the frontend simply prints the fields it receives.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
# Each entry: code -> {en: {...}, ar: {...}} plus an http_status used by the API.
CATALOG: Dict[str, Dict[str, Any]] = {
    "MISSING_API_ID": {
        "status": 400,
        "en": {
            "title": "API ID is missing",
            "message": "The Telegram API ID is empty, so the app cannot identify your application.",
            "hint": "Enter the numeric API ID from your Telegram developer account.",
            "steps": [
                "Open https://my.telegram.org and sign in with your phone number.",
                "Click 'API development tools'.",
                "Copy the 'App api_id' value into the API ID field.",
            ],
        },
        "ar": {
            "title": "معرّف API مفقود",
            "message": "حقل معرّف API فارغ، فلا يستطيع التطبيق التعرّف على تطبيقك.",
            "hint": "أدخل معرّف API الرقمي من حساب مطوّر تلغرام.",
            "steps": [
                "افتح https://my.telegram.org وسجّل الدخول برقم هاتفك.",
                "اضغط على 'API development tools'.",
                "انسخ قيمة 'App api_id' والصقها في حقل معرّف API.",
            ],
        },
    },
    "INVALID_API_ID": {
        "status": 400,
        "en": {
            "title": "API ID is invalid",
            "message": "The API ID must be a positive whole number (digits only).",
            "hint": "Remove any letters, spaces or symbols — keep only the digits.",
            "steps": [
                "Verify the value on https://my.telegram.org → API development tools.",
                "Example of a valid value: 1234567.",
            ],
        },
        "ar": {
            "title": "معرّف API غير صالح",
            "message": "يجب أن يكون معرّف API عدداً صحيحاً موجباً (أرقاماً فقط).",
            "hint": "أزل أي حروف أو مسافات أو رموز — أبقِ الأرقام فقط.",
            "steps": [
                "تحقّق من القيمة في https://my.telegram.org → API development tools.",
                "مثال على قيمة صحيحة: 1234567.",
            ],
        },
    },
    "MISSING_API_HASH": {
        "status": 400,
        "en": {
            "title": "API Hash is missing",
            "message": "The API Hash is empty, so the app cannot authenticate with Telegram.",
            "hint": "Paste the 32-character API Hash from my.telegram.org.",
            "steps": [
                "Open https://my.telegram.org → API development tools.",
                "Copy the 'App api_hash' value (32 hex characters).",
                "Paste it into the API Hash field.",
            ],
        },
        "ar": {
            "title": "هاش API مفقود",
            "message": "حقل هاش API فارغ، فلا يستطيع التطبيق المصادقة مع تلغرام.",
            "hint": "الصق هاش API المكوّن من 32 محرفاً من my.telegram.org.",
            "steps": [
                "افتح https://my.telegram.org → API development tools.",
                "انسخ قيمة 'App api_hash' (32 محرفاً).",
                "الصقها في حقل هاش API.",
            ],
        },
    },
    "MISSING_BOT_TOKEN": {
        "status": 400,
        "en": {
            "title": "Bot Token is missing",
            "message": "No bot token was provided, so nothing can post to the destination channel.",
            "hint": "Create a bot with @BotFather and paste its token.",
            "steps": [
                "Open Telegram and chat with @BotFather.",
                "Send /newbot and follow the prompts to get a token.",
                "Copy the token (looks like 123456:ABC-DEF...) into the Bot Token field.",
            ],
        },
        "ar": {
            "title": "توكن البوت مفقود",
            "message": "لم يُقدَّم توكن بوت، فلا يستطيع شيء النشر إلى قناة الوجهة.",
            "hint": "أنشئ بوتاً عبر @BotFather والصق توكنه.",
            "steps": [
                "افتح تلغرام وحادث @BotFather.",
                "أرسل /newbot واتبع التعليمات للحصول على التوكن.",
                "انسخ التوكن (يبدو مثل 123456:ABC-DEF...) والصقه في حقل توكن البوت.",
            ],
        },
    },
    "INVALID_BOT_TOKEN": {
        "status": 400,
        "en": {
            "title": "Bot Token is invalid",
            "message": "Telegram rejected the bot token during login.",
            "hint": "Re-copy the token from @BotFather — it must be the part after the colon too.",
            "steps": [
                "In @BotFather send /mybots, pick your bot, then 'API Token'.",
                "Copy the full token including the digits and the part after ':'.",
                "Make sure there are no trailing spaces.",
            ],
        },
        "ar": {
            "title": "توكن البوت غير صالح",
            "message": "رفض تلغرام توكن البوت أثناء تسجيل الدخول.",
            "hint": "أعد نسخ التوكن من @BotFather — بما في ذلك الجزء بعد النقطتين.",
            "steps": [
                "في @BotFather أرسل /mybots، اختر بوتك، ثم 'API Token'.",
                "انسخ التوكن كاملاً مع الأرقام والجزء بعد ':'.",
                "تأكّد من عدم وجود مسافات زائدة.",
            ],
        },
    },
    "MISSING_SOURCE_CHANNEL": {
        "status": 400,
        "en": {
            "title": "Source channel is missing",
            "message": "No source channel is set, so there is nothing to read messages from.",
            "hint": "Enter the source channel as @username or a numeric ID.",
            "steps": [
                "Open the source channel and copy its @username.",
                "Paste it into the Source Channel field (e.g. @my_source).",
                "For private channels, use the numeric ID (e.g. -1001234567890).",
            ],
        },
        "ar": {
            "title": "قناة المصدر مفقودة",
            "message": "لا قناة مصدر محددة، فلا يوجد ما تُقرأ منه الرسائل.",
            "hint": "أدخل قناة المصدر بصيغة @username أو معرّف رقمي.",
            "steps": [
                "افتح قناة المصدر وانسخ اسمها @username.",
                "الصقه في حقل قناة المصدر (مثال: @my_source).",
                "للقنوات الخاصة استخدم المعرّف الرقمي (مثال: -1001234567890).",
            ],
        },
    },
    "MISSING_DEST_CHANNEL": {
        "status": 400,
        "en": {
            "title": "Destination channel is missing",
            "message": "No destination channel is set, so there is nowhere to post.",
            "hint": "Enter the destination channel and make the bot an admin there.",
            "steps": [
                "Open the destination channel and copy its @username.",
                "Paste it into the Destination Channel field.",
                "Add your bot as an administrator of that channel.",
            ],
        },
        "ar": {
            "title": "قناة الوجهة مفقودة",
            "message": "لا قناة وجهة محددة، فلا يوجد مكان للنشر فيه.",
            "hint": "أدخل قناة الوجهة واجعل البوت أدمن فيها.",
            "steps": [
                "افتح قناة الوجهة وانسخ اسمها @username.",
                "الصقه في حقل قناة الوجهة.",
                "أضف بوتك أدمن في تلك القناة.",
            ],
        },
    },
    "USER_NOT_AUTHORIZED": {
        "status": 400,
        "en": {
            "title": "User account is not signed in",
            "message": "The Telegram user session has not been authorised yet.",
            "hint": "Sign in the user account once (phone + code) to create the session file.",
            "steps": [
                "The user account must log in once to create a session file.",
                "Provide a valid phone number and the login code Telegram sends you.",
                "If no session file exists, the app cannot read the source channel.",
            ],
        },
        "ar": {
            "title": "حساب المستخدم غير مسجّل الدخول",
            "message": "جلسة مستخدم تلغرام لم تُصرّح بعد.",
            "hint": "سجّل دخول حساب المستخدم مرة واحدة (هاتف + رمز) لإنشاء ملف الجلسة.",
            "steps": [
                "يجب أن يسجّل حساب المستخدم الدخول مرة لإنشاء ملف جلسة.",
                "زوّد برقم هاتف صالح ورمز الدخول الذي يرسله تلغرام.",
                "بدون ملف جلسة لا يستطيع التطبيق قراءة قناة المصدر.",
            ],
        },
    },
    "BOT_NOT_AUTHORIZED": {
        "status": 400,
        "en": {
            "title": "Bot is not authorised",
            "message": "The bot token was accepted but the bot could not be signed in.",
            "hint": "Double-check the token and that the bot still exists in @BotFather.",
            "steps": [
                "Open @BotFather → /mybots and confirm the bot is not deleted.",
                "Regenerate the token if needed and paste the fresh one.",
            ],
        },
        "ar": {
            "title": "البوت غير مصادق",
            "message": "قُبل توكن البوت لكن لم يُمكن تسجيل دخولا للبوت.",
            "hint": "تحقّق مزدوجاً من التوكن وأن البوت ما زال موجوداً في @BotFather.",
            "steps": [
                "افتح @BotFather → /mybots وتأكّد أن البوت غير محذوف.",
                "أعد توليد التوكن عند الحاجة والصق الجديد.",
            ],
        },
    },
    "CHANNEL_NOT_FOUND": {
        "status": 400,
        "en": {
            "title": "Channel could not be found",
            "message": "Telegram could not resolve one of the channels.",
            "hint": "Verify the @username or numeric ID and that the account can see it.",
            "steps": [
                "Confirm the channel username is correct and currently active.",
                "Make sure the user account has joined the source channel.",
                "Make sure the bot is a member/admin of the destination channel.",
            ],
        },
        "ar": {
            "title": "تعذّر العثور على القناة",
            "message": "لم يستطع تلغرام إيجاد إحدى القنوات.",
            "hint": "تحقّق من @username أو المعرّف الرقمي وأن الحساب يستطيع رؤيتها.",
            "steps": [
                "تأكّد أن اسم القناة صحيح وفعّال حالياً.",
                "تأكّد أن حساب المستخدم قد انضم إلى قناة المصدر.",
                "تأكّد أن البوت عضو/أدمن في قناة الوجهة.",
            ],
        },
    },
    "FLOOD_WAIT": {
        "status": 429,
        "en": {
            "title": "Telegram rate limit (FloodWait)",
            "message": "Telegram asked us to wait before sending more messages.",
            "hint": "Wait for the indicated number of seconds, then try again.",
            "steps": [
                "Do not restart repeatedly — that extends the wait.",
                "Wait the number of seconds Telegram reported, then retry.",
            ],
        },
        "ar": {
            "title": "حدّ معدّل تلغرام (FloodWait)",
            "message": "طلب تلغرام الانتظار قبل إرسال مزيد من الرسائل.",
            "hint": "انتظر عدد الثواني المذكور ثم أعد المحاولة.",
            "steps": [
                "لا تُعد التشغيل مراراً — فذلك يمدّد مدة الانتظار.",
                "انتظر عدد الثواني التي أبلغ بها تلغرام ثم أعد المحاولة.",
            ],
        },
    },
    "CONFIG_INVALID": {
        "status": 400,
        "en": {
            "title": "Configuration rejected",
            "message": "The configuration did not pass validation.",
            "hint": "Review the highlighted fields and correct the reported problem.",
            "steps": [
                "Fill every required field: API ID, API Hash, Bot Token and both channels.",
                "API ID must be numeric; API Hash must be non-empty.",
                "Repost mode is fixed to 'copy'; it cannot be changed.",
            ],
        },
        "ar": {
            "title": "الإعدادات مرفوضة",
            "message": "لم تجتز الإعدادات التحقق.",
            "hint": "راجع الحقول المحددة وصحّح المشكلة المذكورة.",
            "steps": [
                "املأ كل الحقول المطلوبة: معرّف API، هاش API، توكن البوت، والقناتين.",
                "معرّف API يجب أن يكون رقمياً؛ هاش API يجب ألا يكون فارغاً.",
                "وضع النشر ثابت على 'copy' ولا يمكن تغييره.",
            ],
        },
    },
    "ALREADY_RUNNING": {
        "status": 200,
        "en": {
            "title": "Already running",
            "message": "The reposter is already running; start was ignored.",
            "hint": "Stop it first if you want to restart with new settings.",
            "steps": ["Press Stop, change any settings, then press Start again."],
        },
        "ar": {
            "title": "يعمل بالفعل",
            "message": "الناشر يعمل بالفعل؛ تم تجاهل أمر التشغيل.",
            "hint": "أوقفه أولاً إن أردت إعادة التشغيل بإعدادات جديدة.",
            "steps": ["اضغط إيقاف، عدّل الإعدادات، ثم اضغط تشغيل مجدداً."],
        },
    },
    "SESSION_LOCKED": {
        "status": 409,
        "en": {
            "title": "Session file is busy",
            "message": "The Telegram session file is in use by another operation.",
            "hint": "Wait a moment, then press Start again.",
            "steps": [
                "Wait 2-3 seconds for the previous operation to release the session file.",
                "Press Start again.",
                "If it persists, use Stop, then Start, to reset both clients.",
            ],
        },
        "ar": {
            "title": "ملف الجلسة مشغول",
            "message": "ملف جلسة تلغرام مستخدم من عملية أخرى.",
            "hint": "انتظر لحظة ثم اضغط Start مجدداً.",
            "steps": [
                "انتظر 2-3 ثوانٍ حتى تُحرِّر العملية السابقة ملف الجلسة.",
                "اضغط Start مرة أخرى.",
                "إن استمرّ الأمر، استخدم Stop ثم Start لإعادة تصفير العميلين.",
            ],
        },
    },
    "INVALID_API_CREDENTIALS": {
        "status": 400,
        "en": {
            "title": "API ID / API Hash pair is invalid",
            "message": "Telegram rejected the API ID and API Hash combination.",
            "hint": "Re-copy both values from my.telegram.org exactly, with no extra spaces.",
            "steps": [
                "Open https://my.telegram.org and sign in with your phone number.",
                "Open 'API development tools' and copy 'App api_id' and 'App api_hash'.",
                "Paste both into the configuration fields and press Save.",
                "Make sure the API Hash is the full 32-character value, not a masked one with '*'.",
            ],
        },
        "ar": {
            "title": "زوج معرّف API وهاش API غير صالح",
            "message": "رفض تلغرام اجتماع معرّف API وهاش API.",
            "hint": "أعد نسخ القيمتين من my.telegram.org بدقة، بلا مسافات زائدة.",
            "steps": [
                "افتح https://my.telegram.org وسجّل الدخول برقم هاتفك.",
                "افتح 'API development tools' وانسخ 'App api_id' و'App api_hash'.",
                "الصق القيمتين في حقول الإعدادات ثم اضغط حفظ.",
                "تأكد أن هاش API هو القيمة الكاملة ذات 32 حرفاً، لا قيمة مُقنّعة فيها '*'.",
            ],
        },
    },
    "INVALID_API_HASH": {
        "status": 400,
        "en": {
            "title": "API Hash is masked or a placeholder",
            "message": "The stored API Hash contains '*' or is a placeholder, not a real value.",
            "hint": "Paste the real 32-character hash; do not copy the masked value shown in the dashboard.",
            "steps": [
                "Open https://my.telegram.org → API development tools.",
                "Copy 'App api_hash' in full — it has no '*' characters.",
                "Replace the current value in the API Hash field and press Save.",
            ],
        },
        "ar": {
            "title": "هاش API مُقنّع أو عنصر نائب",
            "message": "هاش API المخزّن يحتوي '*' أو هو عنصر نائب، لا قيمة حقيقية.",
            "hint": "الصق الهاش الحقيقي ذا 32 حرفاً؛ لا تنسخ القيمة المُقنّعة المعروضة في اللوحة.",
            "steps": [
                "افتح https://my.telegram.org ← API development tools.",
                "انسخ 'App api_hash' كاملاً — لا يحتوي أي '*'.",
                "استبدل القيمة الحالية في حقل هاش API ثم اضغط حفظ.",
            ],
        },
    },
    "LOGIN_PHONE_REQUIRED": {
        "status": 400,
        "en": {
            "title": "Phone number required",
            "message": "Enter the phone number of the Telegram user account to sign in.",
            "hint": "Use the international format with the country code, e.g. +2126XXXXXXXX.",
            "steps": [
                "Type the account phone number in the sign-in field.",
                "Then press 'Send code'.",
            ],
        },
        "ar": {
            "title": "رقم الهاتف مطلوب",
            "message": "أدخل رقم هاتف حساب تلغرام الذي تريد تسجيل الدخول به.",
            "hint": "استخدم الصيغة الدولية مع رمز الدولة، مثل +2126XXXXXXXX.",
            "steps": [
                "اكتب رقم هاتف الحساب في حقل تسجيل الدخول.",
                "ثم اضغط 'إرسال الرمز'.",
            ],
        },
    },
    "LOGIN_PHONE_INVALID": {
        "status": 400,
        "en": {
            "title": "Phone number is invalid",
            "message": "Telegram rejected that phone number.",
            "hint": "Include the country code and drop spaces or dashes, e.g. +2126XXXXXXXX.",
            "steps": [
                "Check the number against your Telegram account settings.",
                "Re-enter it in the international format, then send the code again.",
            ],
        },
        "ar": {
            "title": "رقم الهاتف غير صالح",
            "message": "رفض تلغرام رقم الهاتف هذا.",
            "hint": "أضف رمز الدولة واحذف المسافات والشرطات، مثل +2126XXXXXXXX.",
            "steps": [
                "راجع الرقم من إعدادات حسابك في تلغرام.",
                "أعد إدخاله بالصيغة الدولية ثم أرسل الرمز مجدداً.",
            ],
        },
    },
    "LOGIN_NO_CODE_REQUEST": {
        "status": 400,
        "en": {
            "title": "No login code was requested",
            "message": "You must send the login code first before entering it.",
            "hint": "Enter your phone number and press 'Send code', then enter the code.",
            "steps": [
                "Fill the phone number field.",
                "Press 'Send code' to receive the code inside Telegram.",
            ],
        },
        "ar": {
            "title": "لم يُطلب رمز الدخول بعد",
            "message": "يجب إرسال رمز الدخول أولاً قبل إدخاله.",
            "hint": "أدخل رقم هاتفك واضغط 'إرسال الرمز'، ثم أدخل الرمز.",
            "steps": [
                "املأ حقل رقم الهاتف.",
                "اضغط 'إرسال الرمز' ليصلك الرمز داخل تلغرام.",
            ],
        },
    },
    "LOGIN_CODE_REQUIRED": {
        "status": 400,
        "en": {
            "title": "Login code required",
            "message": "Enter the login code Telegram sent you inside the app.",
            "hint": "The code arrives in the Telegram app, not by SMS.",
            "steps": [
                "Open Telegram on your phone or desktop.",
                "Copy the login code and paste it into the code field.",
            ],
        },
        "ar": {
            "title": "رمز الدخول مطلوب",
            "message": "أدخل رمز الدخول الذي أرسله لك تلغرام داخل التطبيق.",
            "hint": "يصل الرمز داخل تطبيق تلغرام، لا برسالة نصية.",
            "steps": [
                "افتح تلغرام على هاتفك أو حاسوبك.",
                "انسخ رمز الدخول والصقه في حقل الرمز.",
            ],
        },
    },
    "LOGIN_CODE_INVALID": {
        "status": 400,
        "en": {
            "title": "Login code is wrong",
            "message": "The code you entered does not match the one Telegram sent.",
            "hint": "Re-check the digits; the code expires quickly.",
            "steps": [
                "Read the latest code inside the Telegram app.",
                "Enter it exactly, or press 'Send code' again for a fresh one.",
            ],
        },
        "ar": {
            "title": "رمز الدخول خاطئ",
            "message": "الرمز الذي أدخلته لا يطابق ما أرسله تلغرام.",
            "hint": "راجع الأرقام؛ فالرمز ينتهي سريعاً.",
            "steps": [
                "اقرأ أحدث رمز داخل تطبيق تلغرام.",
                "أدخله بدقة، أو اضغط 'إرسال الرمز' مجدداً للحصول على رمز جديد.",
            ],
        },
    },
    "LOGIN_CODE_EXPIRED": {
        "status": 400,
        "en": {
            "title": "Login code expired",
            "message": "Too much time passed before the code was entered.",
            "hint": "Request a new code and enter it right away.",
            "steps": [
                "Press 'Send code' again.",
                "Enter the fresh code promptly.",
            ],
        },
        "ar": {
            "title": "انتهت صلاحية رمز الدخول",
            "message": "مضى وقت طويل قبل إدخال الرمز.",
            "hint": "اطلب رمزاً جديداً وأدخله فوراً.",
            "steps": [
                "اضغط 'إرسال الرمز' مجدداً.",
                "أدخل الرمز الجديد بسرعة.",
            ],
        },
    },
    "LOGIN_NO_PASSWORD_NEEDED": {
        "status": 400,
        "en": {
            "title": "No password required",
            "message": "This account does not need a two-step verification password right now.",
            "hint": "Continue from the code step instead.",
            "steps": [
                "Request and enter a login code.",
                "A password is only asked when 2FA is enabled.",
            ],
        },
        "ar": {
            "title": "لا حاجة إلى كلمة المرور",
            "message": "هذا الحساب لا يحتاج كلمة تحقق بخطوتين الآن.",
            "hint": "تابع من خطوة الرمز بدلاً من ذلك.",
            "steps": [
                "اطلب رمز الدخول وأدخله.",
                "لا تُطلب كلمة المرور إلا عند تفعيل التحقق بخطوتين.",
            ],
        },
    },
    "LOGIN_PASSWORD_REQUIRED": {
        "status": 400,
        "en": {
            "title": "Two-step password required",
            "message": "This account has two-step verification enabled.",
            "hint": "Enter the password you set for two-step verification.",
            "steps": [
                "Type your Telegram two-step verification password.",
                "Press 'Sign in' to finish.",
            ],
        },
        "ar": {
            "title": "كلمة التحقق بخطوتين مطلوبة",
            "message": "هذا الحساب مفعّل عليه التحقق بخطوتين.",
            "hint": "أدخل كلمة المرور التي ضبطتها للتحقق بخطوتين.",
            "steps": [
                "اكتب كلمة مرور التحقق بخطوتين الخاصة بتلغرام.",
                "اضغط 'تسجيل الدخول' لإتمام العملية.",
            ],
        },
    },
    "LOGIN_PASSWORD_INVALID": {
        "status": 400,
        "en": {
            "title": "Two-step password is wrong",
            "message": "The two-step verification password did not match.",
            "hint": "Re-type the password carefully (it is case-sensitive).",
            "steps": [
                "Check the password in Telegram → Settings → Privacy → Two-step.",
                "Enter it again and press 'Sign in'.",
            ],
        },
        "ar": {
            "title": "كلمة التحقق بخطوتين خاطئة",
            "message": "كلمة مرور التحقق بخطوتين غير مطابقة.",
            "hint": "أعد كتابة كلمة المرور بعناية (فهي حساسة لحالة الأحرف).",
            "steps": [
                "راجع كلمة المرور في تلغرام ← الإعدادات ← الخصوصية ← التحقق بخطوتين.",
                "أدخلها مجدداً واضغط 'تسجيل الدخول'.",
            ],
        },
    },
    "INTERNAL_ERROR": {
        "status": 500,
        "en": {
            "title": "Unexpected error",
            "message": "An unexpected error occurred while starting the reposter.",
            "hint": "Check the server log for the full traceback, then retry.",
            "steps": [
                "Read the backend log (server console output).",
                "Fix the underlying issue, then press Start again.",
            ],
        },
        "ar": {
            "title": "خطأ غير متوقع",
            "message": "حدث خطأ غير متوقع أثناء تشغيل الناشر.",
            "hint": "راجع سجل الخادم لمعرفة التفاصيل الكاملة ثم أعد المحاولة.",
            "steps": [
                "اقرأ سجل الـ backend (مخرجات طرفية الخادم).",
                "أصلح المشكلة الأساسية ثم اضغط تشغيل مجدداً.",
            ],
        },
    },
    "AUTH_REQUIRED": {
        "status": 401,
        "en": {
            "title": "Sign in required",
            "message": "This dashboard is protected. Enter the dashboard password to continue.",
            "hint": "Use the password you set when you first opened the dashboard.",
            "steps": [
                "Type the dashboard password in the lock screen.",
                "Press 'Unlock'.",
                "If you forgot it, clear the dashboard password from the database and set a new one.",
            ],
        },
        "ar": {
            "title": "الدخول مطلوب",
            "message": "هذه اللوحة محمية بكلمة سر. أدخل كلمة سر اللوحة للمتابعة.",
            "hint": "استعمل كلمة السر التي أنشأتها عند أول فتح للوحة.",
            "steps": [
                "اكتب كلمة سر اللوحة في شاشة القفل.",
                "اضغط فتح.",
                "إن نسيتها، امسح كلمة السر من قاعدة البيانات وأنشئ جديدة.",
            ],
        },
    },
    "AUTH_SETUP_REQUIRED": {
        "status": 401,
        "en": {
            "title": "Create a dashboard password",
            "message": "No dashboard password exists yet. Create one now to protect the control panel.",
            "hint": "Pick a password of at least 6 characters and keep it somewhere safe.",
            "steps": [
                "Type the new password.",
                "Repeat it in the confirmation field.",
                "Press 'Create password'.",
            ],
        },
        "ar": {
            "title": "أنشئ كلمة سر للوحة",
            "message": "لا توجد كلمة سر بعد. أنشئ واحدة الآن لحماية لوحة التحكم.",
            "hint": "اختر كلمة سر من 6 أحرف على الأقل واحفظها في مكان آمن.",
            "steps": [
                "اكتب كلمة السر الجديدة.",
                "أعدها في حقل التأكيد.",
                "اضغط إنشاء كلمة السر.",
            ],
        },
    },
    "AUTH_INVALID_PASSWORD": {
        "status": 401,
        "en": {
            "title": "Wrong password",
            "message": "The password you entered does not match the dashboard password.",
            "hint": "Check the keyboard language and Caps Lock, then try again.",
            "steps": [
                "Re-type the password carefully.",
                "Make sure Caps Lock is off.",
                "After 5 failed attempts the form locks for one minute.",
            ],
        },
        "ar": {
            "title": "كلمة السر خاطئة",
            "message": "كلمة السر التي أدخلتها لا تطابق كلمة سر اللوحة.",
            "hint": "تحقق من لغة اللوحة ومفتاح Caps Lock ثم أعد المحاولة.",
            "steps": [
                "أعد كتابة كلمة السر بتأن.",
                "تأكد أن Caps Lock مغلق.",
                "بعد 5 محاولات فاشلة يُقفل النموذج دقيقة.",
            ],
        },
    },
    "AUTH_LOCKED": {
        "status": 429,
        "en": {
            "title": "Too many attempts",
            "message": "The dashboard is locked for a short while after repeated wrong passwords.",
            "hint": "Wait one minute, then try again.",
            "steps": [
                "Wait 60 seconds.",
                "Enter the correct password.",
            ],
        },
        "ar": {
            "title": "محاولات كثيرة",
            "message": "قُفلت اللوحة مؤقتا بعد تكرار كلمات سر خاطئة.",
            "hint": "انتظر دقيقة ثم أعد المحاولة.",
            "steps": [
                "انتظر 60 ثانية.",
                "أدخل كلمة السر الصحيحة.",
            ],
        },
    },
    "AUTH_PASSWORD_SHORT": {
        "status": 400,
        "en": {
            "title": "Password is too short",
            "message": "The dashboard password must be at least 6 characters long.",
            "hint": "Use 8 characters or more for real protection.",
            "steps": [
                "Type a longer password.",
                "Include letters and digits.",
            ],
        },
        "ar": {
            "title": "كلمة السر قصيرة",
            "message": "يجب أن تكون كلمة سر اللوحة 6 أحرف على الأقل.",
            "hint": "استعمل 8 أحرف أو أكثر لحماية حقيقية.",
            "steps": [
                "اكتب كلمة سر أطول.",
                "امزج بين الحروف والأرقام.",
            ],
        },
    },
    "AUTH_PASSWORD_MISMATCH": {
        "status": 400,
        "en": {
            "title": "Passwords do not match",
            "message": "The confirmation field does not match the new password.",
            "hint": "Type the same password twice.",
            "steps": [
                "Clear both fields.",
                "Type the password again in both.",
            ],
        },
        "ar": {
            "title": "كلمتا السر مختلفتان",
            "message": "حقل التأكيد لا يطابق كلمة السر الجديدة.",
            "hint": "اكتب نفس كلمة السر مرتين.",
            "steps": [
                "أفرغ الحقلين.",
                "أعد كتابة كلمة السر في الحقلين.",
            ],
        },
    },
}


def _split_steps(steps: List[str]) -> List[str]:
    return [s for s in (steps or []) if s]


def build_error(code: str, lang: str = "en", detail: Optional[str] = None) -> Dict[str, Any]:
    """Return a localised, structured error payload for ``code``.

    ``detail`` (optional) is the raw technical message; it is attached under
    ``detail`` so power users can still see the original exception text.
    """
    entry = CATALOG.get(code) or CATALOG["INTERNAL_ERROR"]
    block = entry.get(lang) or entry.get("en") or {}
    return {
        "code": code if code in CATALOG else "INTERNAL_ERROR",
        "title": block.get("title", "Error"),
        "message": block.get("message", ""),
        "hint": block.get("hint", ""),
        "steps": _split_steps(block.get("steps", [])),
        "detail": detail,
        "status": entry.get("status", 500),
    }


def classify(message: str) -> str:
    """Best-effort mapping from a raw exception string to a catalog code."""
    text = (message or "").lower()
    if "database is locked" in text or "session file is busy" in text:
        return "SESSION_LOCKED"
    if "api_id/api_hash combination is invalid" in text or "api_id/api_hash combination" in text:
        return "INVALID_API_CREDENTIALS"
    if "looks masked" in text or "placeholder" in text and "api_hash" in text:
        return "INVALID_API_HASH"
    if "api_id/api_hash are not configured" in text or "api_id" in text and "not configured" in text:
        return "MISSING_API_ID"
    if "api_hash must not be empty" in text:
        return "MISSING_API_HASH"
    if "api_id must be a positive integer" in text:
        return "INVALID_API_ID"
    if "bot_token is not configured" in text:
        return "MISSING_BOT_TOKEN"
    if "bot token is invalid" in text or "bot is not authorized" in text:
        return "INVALID_BOT_TOKEN"
    if "user session is not authorized" in text:
        return "USER_NOT_AUTHORIZED"
    if "source_channel and destination_channel are not configured" in text:
        return "MISSING_SOURCE_CHANNEL"
    if "source_channel" in text and "configured" in text:
        return "MISSING_SOURCE_CHANNEL"
    if "destination_channel" in text and "configured" in text:
        return "MISSING_DEST_CHANNEL"
    if "could not find the input entity" in text or "cannot find any entity" in text:
        return "CHANNEL_NOT_FOUND"
    if "flood" in text and "wait" in text:
        return "FLOOD_WAIT"
    if "repost_mode" in text:
        return "CONFIG_INVALID"
    return "INTERNAL_ERROR"


def from_exception(exc: BaseException, lang: str = "en") -> Dict[str, Any]:
    """Build a structured error payload from a caught exception."""
    code = classify(str(exc))
    return build_error(code, lang=lang, detail=str(exc))
