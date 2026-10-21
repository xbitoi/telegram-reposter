'use strict';

/* ============================================================
   Reposter — Telegram Auto-Reposter Dashboard
   WebSocket live feed + REST config/stats + Chart.js + EN/AR i18n

   Backend contract (verified live):
     WS  ws://localhost:8000/ws  -> frames are { event, data }
         events: stats | status | message | error | pong
     REST http://localhost:8000/api/*
   ============================================================ */

const API_BASE = 'http://localhost:8000';
const WS_URL = 'ws://localhost:8000/ws';
const FEED_CAP = 50;
const LATENCY_CAP = 100;
const LATENCY_FAST_MS = 1000;
const LATENCY_SLOW_MS = 2000;
const STATUS_POLL_MS = 15000;

/* ---------------- i18n ---------------- */
const I18N = {
  en: {
    subtitle: 'Telegram Auto-Reposter',
    running: 'Running',
    stopped: 'Stopped',
    ws_online: 'Live',
    ws_offline: 'Disconnected',
    ws_connecting: 'Connecting…',
    start: 'Start',
    stop: 'Stop',
    lang_toggle: 'EN / AR',
    messages_today: 'Messages Today',
    last_24h: 'last 24h',
    avg_latency: 'Avg Latency',
    end_to_end: 'end-to-end',
    success_rate: 'Success Rate',
    errors: 'Errors',
    total_logged: 'total logged',
    latency_chart: 'Latency — Last 100 Messages',
    hourly_chart: 'Messages / Hour — Last 24h',
    live_feed: 'Live Message Feed',
    config: 'Configuration',
    api_id: 'API ID',
    api_hash: 'API Hash',
    bot_token: 'Bot Token',
    source_channel: 'Source Channel',
    dest_channel: 'Destination Channel',
    repost_mode: 'Repost Mode',
    mode_copy: 'Copy',
    save: 'Save Configuration',
    recent_errors: 'Recent Errors',
    footer: 'Reposter Dashboard — local build',
    feed_empty: 'No messages yet — waiting for the stream…',
    errors_empty: 'No errors logged. All clear.',
    fast: '<1s',
    slow: '1–2s',
    very_slow: '>2s',
    toast_saved: 'Configuration saved',
    toast_saved_restarted: 'Configuration saved and the reposter restarted with the new bot',
    toast_save_fail: 'Failed to save configuration',
    toast_started: 'Reposter started',
    toast_stopped: 'Reposter stopped',
    toast_start_fail: 'Failed to start',
  toast_reset_fail: 'Could not reset the counters',
  toast_clear_fail: 'Could not clear the log',
    toast_stop_fail: 'Failed to stop',
    toast_cfg_loaded: 'Configuration loaded',
    toast_cfg_load_fail: 'Failed to load configuration',
    toast_ws_up: 'Live connection established',
    toast_ws_down: 'Connection lost — reconnecting…',
    toast_error: 'Error received',
    ok: 'OK',
    failed: 'FAILED',
    msg_unit: 'messages',
  reset_counters: 'Reset counters',
  clear_log: 'Clear log',
  confirm_reset: 'Reset all counters? The message history will be kept.',
  confirm_clear: 'Clear the whole log and delete all errors? This cannot be undone.',
  toast_reset: 'Counters reset',
  toast_cleared: 'Log cleared',
  type_text: 'Text',
  type_photo: 'Photo',
  type_video: 'Video',
  type_document: 'File',
  type_audio: 'Audio',
  type_voice: 'Voice',
  type_video_note: 'Video note',
  type_sticker: 'Sticker',
  type_gif: 'GIF',
  type_poll: 'Poll',
  type_location: 'Location',
  type_contact: 'Contact',
  type_unknown: 'Other',
    unknown_error: 'Unknown error',
    user_account: 'User Account',
    bot_account: 'Bot Account',
    online: 'Online',
    offline: 'Offline',
    idle: 'Idle',
    signed_in: 'Signed in',
    not_connected: 'Not connected',
    no_source: 'No source configured',
    source_ready: 'Listening',
    theme_toggle: 'Toggle theme',
    guide_title: 'How to get your credentials',
    guide_intro: 'Telegram needs three credentials: an API ID, an API Hash (from your developer account) and a Bot Token (from @BotFather). Follow the steps below.',
    guide_api_title: 'API ID & API Hash',
    guide_api_s1: 'Open my.telegram.org in your browser.',
    guide_api_s2: 'Sign in with your Telegram phone number (include the country code, e.g. +212...).',
    guide_api_s3: 'Enter the login code Telegram sends you inside the app.',
    guide_api_s4: 'Click "API development tools".',
    guide_api_s5: 'Fill the short form (app title and short name are enough).',
    guide_api_s6: 'Copy "App api_id" and "App api_hash" into the fields below.',
    guide_open: 'Open my.telegram.org',
    guide_bot_title: 'Bot Token',
    guide_bot_s1: 'Open Telegram and search for @BotFather.',
    guide_bot_s2: 'Send /newbot and choose a name and a username ending in "bot".',
    guide_bot_s3: 'Copy the token BotFather returns (looks like 123456:ABC-DEF...).',
    guide_bot_s4: 'Add the bot as an administrator of your destination channel.',
    guide_open_botfather: 'Open @BotFather',
    guide_ch_title: 'Channels',
    guide_ch_s1: 'Source: the channel to read from — the user account must have joined it.',
    guide_ch_s2: 'Destination: the channel to post into — the bot must be an admin there.',
    guide_ch_s3: 'Use @username for public channels, or the numeric ID (e.g. -1001234567890) for private ones.',
    guide_note: 'Your credentials never leave this machine: they are stored only in the local config file.',
    auth_locked_title: 'Dashboard locked',
    auth_locked_sub: 'Enter the password to open the control panel.',
    auth_password: 'Password',
    auth_confirm: 'Confirm password',
    auth_unlock: 'Unlock',
    auth_create: 'Create password',
    auth_saving: 'Please wait...',
    auth_note: 'The password is local to this machine and stored only as a hash.',
    auth_setup_title: 'Protect your dashboard',
    auth_setup_sub: 'Set a password now. You will type it every time you open this control panel.',
    auth_change_title: 'Change dashboard password',
    auth_change_sub: 'Confirm the current password, then choose a new one.',
    auth_change_current: 'Current password',
    auth_new: 'New password',
    auth_update: 'Update password',
    auth_unlocked: 'Unlocked',
    auth_locked_badge: 'Locked',
    auth_too_short: 'The password must be at least 6 characters.',
    auth_mismatch: 'The two passwords do not match.',
    auth_error_generic: 'Could not complete the request.',
    confirm_disable_lock: 'Turn off the password lock? The dashboard will open without a password on this machine.',
    access_toggle_label: 'Password lock',
    access_toggle_off_hint: 'Off - anyone on this machine can open the dashboard.',
    access_toggle_on_hint: 'On - the password is required to open the dashboard.',
    auth_lock_disabled: 'Lock disabled',
    auth_lock_enabled: 'Lock enabled',
    dev_by: 'Developed by',
    toast_lock_on: 'Password lock enabled',
    toast_lock_off: 'Password lock disabled',
    auth_need_password: 'Type a password first to turn the lock on.',
    access_title: 'Dashboard access',
    access_intro: 'The dashboard password keeps this control panel private on this machine. Change it whenever you like.',
    access_change: 'Change password',
    access_lock: 'Lock now',
    toast_auth_welcome: 'Dashboard unlocked',
    toast_auth_setup: 'Password created — dashboard unlocked',
    toast_auth_changed: 'Password updated',
    toast_auth_locked: 'Dashboard locked',
    toast_auth_logout: 'Signed out of the dashboard',
    confirm: 'Confirm',
    cancel: 'Cancel',
    confirm_title_reset: 'Reset counters?',
    confirm_title_clear: 'Clear the whole log?',
    error_title: 'Error',
    copied: 'Copied to clipboard',
    copy_failed: 'Copy failed',
    login_title: 'Sign in your user account',
    login_intro: 'A user account must sign in once so the reposter can read any source channel. After that the session is stored and you never repeat this.',
    login_state_idle: 'Not signed in',
    login_state_code_sent: 'Code sent',
    login_state_password_needed: '2FA required',
    login_state_authorized: 'Signed in',
    login_phone_label: 'Phone number (international format)',
    login_send_code: 'Send code',
    login_resend: 'Resend code',
    login_code_label: 'Login code (sent inside Telegram)',
    login_verify: 'Verify',
    login_password_label: 'Two-step verification password',
    login_sign_in: 'Sign in',
    login_signed_in: 'Signed in',
    login_logout: 'Sign out',
    login_success: 'Signed in successfully',
    login_code_sent_toast: 'Login code sent — check Telegram',
    login_password_needed_toast: 'Two-step verification required'
  },
  ar: {
    subtitle: 'مُعيد النشر التلقائي لتيليجرام',
    running: 'يعمل',
    stopped: 'متوقف',
    ws_online: 'متصل',
    ws_offline: 'منقطع',
    ws_connecting: 'جارٍ الاتصال…',
    start: 'تشغيل',
    stop: 'إيقاف',
    lang_toggle: 'AR / EN',
    messages_today: 'رسائل اليوم',
    last_24h: 'آخر 24 ساعة',
    avg_latency: 'متوسط التأخير',
    end_to_end: 'من البداية للنهاية',
    success_rate: 'نسبة النجاح',
    errors: 'الأخطاء',
    total_logged: 'إجمالي المسجل',
    latency_chart: 'التأخير — آخر 100 رسالة',
    hourly_chart: 'الرسائل في الساعة — آخر 24 ساعة',
    live_feed: 'بث الرسائل المباشر',
    config: 'الإعدادات',
    api_id: 'معرف API',
    api_hash: 'هاش API',
    bot_token: 'توكن البوت',
    source_channel: 'قناة المصدر',
    dest_channel: 'قناة الوجهة',
    repost_mode: 'وضع النشر',
    mode_copy: 'نسخ',
    save: 'حفظ الإعدادات',
    recent_errors: 'الأخطاء الأخيرة',
    footer: 'لوحة التحكم — نسخة محلية',
    feed_empty: 'لا رسائل بعد — في انتظار البث…',
    errors_empty: 'لا أخطاء مسجلة. كل شيء سليم.',
    fast: '<1 ث',
    slow: '1–2 ث',
    very_slow: '>2 ث',
    toast_saved: 'تم حفظ الإعدادات',
    toast_saved_restarted: 'تم حفظ الإعدادات وإعادة تشغيل الناشر بالبوت الجديد',
    toast_save_fail: 'فشل حفظ الإعدادات',
    toast_started: 'تم تشغيل الناشر',
    toast_stopped: 'تم إيقاف الناشر',
    toast_start_fail: 'فشل التشغيل',
  toast_reset_fail: 'تعذر تصفير العدادات',
  toast_clear_fail: 'تعذر مسح السجل',
    toast_stop_fail: 'فشل الإيقاف',
    toast_cfg_loaded: 'تم تحميل الإعدادات',
    toast_cfg_load_fail: 'فشل تحميل الإعدادات',
    toast_ws_up: 'تم إنشاء الاتصال المباشر',
    toast_ws_down: 'انقطع الاتصال — جارٍ إعادة الاتصال…',
    toast_error: 'تم استلام خطأ',
    ok: 'نجح',
    failed: 'فشل',
    msg_unit: 'رسالة',
  reset_counters: 'تصفير العدادات',
  clear_log: 'مسح السجل',
  confirm_reset: 'هل تريد تصفير جميع العدادات؟ يبقى السجل كما هو.',
  confirm_clear: 'هل تريد مسح السجل كاملا وحذف الأخطاء؟ لا يمكن التراجع.',
  toast_reset: 'تم تصفير العدادات',
  toast_cleared: 'تم مسح السجل',
  type_text: 'نص',
  type_photo: 'صورة',
  type_video: 'فيديو',
  type_document: 'ملف',
  type_audio: 'صوت',
  type_voice: 'رسالة صوتية',
  type_video_note: 'فيديو دائري',
  type_sticker: 'ملصق',
  type_gif: 'متحركة',
  type_poll: 'استطلاع',
  type_location: 'موقع',
  type_contact: 'جهة اتصال',
  type_unknown: 'أخرى',
    unknown_error: 'خطأ غير معروف',
    user_account: 'حساب المستخدم',
    bot_account: 'حساب البوت',
    online: 'متصل',
    offline: 'غير متصل',
    idle: 'خامل',
    signed_in: 'مسجل الدخول',
    not_connected: 'غير موصول',
    no_source: 'لا قناة مصدر محددة',
    source_ready: 'يستمع',
    theme_toggle: 'تبديل المظهر',
    guide_title: 'كيف تحصل على مفاتيحك',
    guide_intro: 'يحتاج تلغرام إلى ثلاثة مفاتيح: معرّف API، وهاش API (من حساب المطوّر)، وتوكن بوت (من @BotFather). اتبع الخطوات أدناه.',
    guide_api_title: 'معرّف API وهاش API',
    guide_api_s1: 'افتح my.telegram.org في متصفحك.',
    guide_api_s2: 'سجّل الدخول برقم هاتفك المتصل بتلغرام (مع رمز الدولة، مثل +212...).',
    guide_api_s3: 'أدخل رمز الدخول الذي يرسله تلغرام داخل التطبيق.',
    guide_api_s4: 'اضغط على "API development tools".',
    guide_api_s5: 'املأ النموذج القصير (اسم التطبيق والاسم المختصر يكفيان).',
    guide_api_s6: 'انسخ "App api_id" و"App api_hash" إلى الحقلين أدناه.',
    guide_open: 'افتح my.telegram.org',
    guide_bot_title: 'توكن البوت',
    guide_bot_s1: 'افتح تلغرام وابحث عن @BotFather.',
    guide_bot_s2: 'أرسل /newbot واختر اسماً واسم مستخدم ينتهي بـ "bot".',
    guide_bot_s3: 'انسخ التوكن الذي يعيده BotFather (يبدو مثل 123456:ABC-DEF...).',
    guide_bot_s4: 'أضف البوت أدمن في قناة الوجهة.',
    guide_open_botfather: 'افتح @BotFather',
    guide_ch_title: 'القنوات',
    guide_ch_s1: 'المصدر: القناة التي تُقرأ منها — ويجب أن يكون حساب المستخدم قد انضم إليها.',
    guide_ch_s2: 'الوجهة: القناة التي يُنشر فيها — ويجب أن يكون البوت أدمن فيها.',
    guide_ch_s3: 'استخدم @username للقنوات العامة، أو المعرّف الرقمي (مثل -1001234567890) للخاصة.',
    guide_note: 'مفاتيحك لا تغادر هذا الجهاز أبداً: تُخزَّن فقط في ملف الإعدادات المحلي.',
    auth_locked_title: 'اللوحة مقفلة',
    auth_locked_sub: 'أدخل كلمة السر لفتح لوحة التحكم.',
    auth_password: 'كلمة السر',
    auth_confirm: 'تأكيد كلمة السر',
    auth_unlock: 'فتح',
    auth_create: 'إنشاء كلمة السر',
    auth_saving: 'انتطر قليلا...',
    auth_note: 'كلمة السر محلية على هذه الجهة ومحفوظة كبصمة فقط.',
    auth_setup_title: 'احمِ لوحتك',
    auth_setup_sub: 'عيّن كلمة سر الآن. ستكتبها في كل مرة تفتح فيها لوحة التحكم.',
    auth_change_title: 'تغيير كلمة سر اللوحة',
    auth_change_sub: 'أكد كلمة السر الحالية ثم اختر جديدة.',
    auth_change_current: 'كلمة السر الحالية',
    auth_new: 'كلمة السر الجديدة',
    auth_update: 'تحديث كلمة السر',
    auth_unlocked: 'مفتوحة',
    auth_locked_badge: 'مقفلة',
    auth_too_short: 'يجب أن تكون كلمة السر 6 أحرف على الأقل.',
    auth_mismatch: 'كلمتا السر لا تتطابقان.',
    auth_error_generic: 'تعذر إتمام الطلب.',
    confirm_disable_lock: 'أتعطيل قفل كلمة السر؟ ستُفتح اللوحة بلا كلمة سر على هذه الجهة.',
    access_toggle_label: 'قفل كلمة السر',
    access_toggle_off_hint: 'مغلق - يستطيع كل من على هذه الجهة فتح اللوحة.',
    access_toggle_on_hint: 'مفتوح - كلمة السر مطلوبة لفتح اللوحة.',
    auth_lock_disabled: 'القفل معطل',
    auth_lock_enabled: 'القفل مفعل',
    dev_by: 'تطوير',
    toast_lock_on: 'فُعّل قفل كلمة السر',
    toast_lock_off: 'عُطّل قفل كلمة السر',
    auth_need_password: 'اكتب كلمة سر أولا لتفعيل القفل.',
    access_title: 'الوصول إلى اللوحة',
    access_intro: 'كلمة سر اللوحة تحفظ لوحة التحكم خاصة على هذه الجهة. غيرها متى شئت.',
    access_change: 'تغيير كلمة السر',
    access_lock: 'اقفل الآن',
    toast_auth_welcome: 'فُتحت اللوحة',
    toast_auth_setup: 'أُنشئت كلمة السر وفُتحت اللوحة',
    toast_auth_changed: 'حُدّثت كلمة السر',
    toast_auth_locked: 'قُفلت اللوحة',
    toast_auth_logout: 'خرجت من اللوحة',
    confirm: 'تأكيد',
    cancel: 'إلغاء',
    confirm_title_reset: 'تصفير العدادات؟',
    confirm_title_clear: 'مسح السجل كاملا؟',
    error_title: 'خطأ',
    copied: 'تم النسخ إلى الحافظة',
    copy_failed: 'فشل النسخ',
    login_title: 'سجّل دخول حساب المستخدم',
    login_intro: 'يجب أن يسجّل حساب المستخدم الدخول مرة واحدة ليتمكن الناشر من قراءة أي قناة مصدر. بعد ذلك تُحفظ الجلسة ولن تعيد هذه الخطوات أبداً.',
    login_state_idle: 'غير مسجّل',
    login_state_code_sent: 'أُرسل الرمز',
    login_state_password_needed: 'التحقق بخطوتين مطلوب',
    login_state_authorized: 'مسجّل الدخول',
    login_phone_label: 'رقم الهاتف (بالصيغة الدولية)',
    login_send_code: 'إرسال الرمز',
    login_resend: 'إعادة إرسال الرمز',
    login_code_label: 'رمز الدخول (يُرسَل داخل تلغرام)',
    login_verify: 'تحقق',
    login_password_label: 'كلمة مرور التحقق بخطوتين',
    login_sign_in: 'تسجيل الدخول',
    login_signed_in: 'تم تسجيل الدخول',
    login_logout: 'تسجيل الخروج',
    login_success: 'تم تسجيل الدخول بنجاح',
    login_code_sent_toast: 'أُرسل رمز الدخول — تحقق من تلغرام',
    login_password_needed_toast: 'التحقق بخطوتين مطلوب'
  }
};

let lang = 'en';

function t(key) {
  return (I18N[lang] && I18N[lang][key]) || I18N.en[key] || key;
}

function locale() {
  return lang === 'ar' ? 'ar-EG-u-nu-latn' : 'en-US';
}

/* ---------------- Formatting ---------------- */
function fmtNum(n, digits) {
  const num = Number(n);
  if (n === null || n === undefined || Number.isNaN(num)) return '0';
  return new Intl.NumberFormat(locale(), {
    maximumFractionDigits: digits === undefined ? 0 : digits,
    minimumFractionDigits: digits === undefined ? 0 : digits
  }).format(num);
}

function fmtTime(ts) {
  const d = ts instanceof Date ? ts : new Date(ts);
  if (Number.isNaN(d.getTime())) return '';
  return new Intl.DateTimeFormat(locale(), {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  }).format(d);
}

/* ---------------- DOM helpers ---------------- */
function $(id) { return document.getElementById(id); }

function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}

/* ---------------- Toasts ---------------- */
function toast(message, kind) {
  const container = $('toastContainer');
  if (!container) return;
  const el = document.createElement('div');
  el.className = 'toast toast-' + (kind || 'info');
  el.textContent = message;
  container.appendChild(el);
  setTimeout(function () {
    el.classList.add('leaving');
    setTimeout(function () { el.remove(); }, 320);
  }, 3800);
}

/* A richer toast carrying a title + hint for structured errors. */
function toastDetailed(title, hint, kind) {
  const container = $('toastContainer');
  if (!container) return;
  const el = document.createElement('div');
  el.className = 'toast toast-detail toast-' + (kind || 'error');

  const titleEl = document.createElement('div');
  titleEl.className = 'td-title';
  titleEl.textContent = title || t('error_title');

  const hintEl = document.createElement('div');
  hintEl.className = 'td-hint';
  hintEl.textContent = hint || '';

  el.appendChild(titleEl);
  if (hint) el.appendChild(hintEl);
  container.appendChild(el);
  setTimeout(function () {
    el.classList.add('leaving');
    setTimeout(function () { el.remove(); }, 320);
  }, 6000);
}

/* Copy text to the clipboard, tolerating missing Clipboard API. */
function copyText(text) {
  const value = String(text == null ? '' : text);
  if (!value) return;
  function done() { toast(t('copied'), 'success'); }
  function fail() { toast(t('copy_failed'), 'error'); }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(value).then(done, fail);
    return;
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = value;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    done();
  } catch (err) { fail(); }
}

/* ---------------- WebSocket ---------------- */
let ws = null;
let wsRetry = 0;
let wsTimer = null;
const WS_RETRY_BASE = 1000;
const WS_RETRY_MAX = 30000;

function setWsState(state) {
  const pill = $('wsPill');
  const label = $('wsLabel');
  if (!pill || !label) return;
  pill.dataset.state = state;
  if (state === 'connected') label.textContent = t('ws_online');
  else if (state === 'connecting') label.textContent = t('ws_connecting');
  else label.textContent = t('ws_offline');
}

function connectWS() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  clearTimeout(wsTimer);
  setWsState('connecting');

  try {
    ws = new WebSocket(WS_URL);
  } catch (err) {
    scheduleReconnect();
    return;
  }

  ws.onopen = function () {
    wsRetry = 0;
    setWsState('connected');
    setText('connInfo', WS_URL.replace('ws://', ''));
    toast(t('toast_ws_up'), 'success');
  };

  ws.onmessage = function (evt) {
    let payload;
    try {
      payload = JSON.parse(evt.data);
    } catch (err) {
      return; // tolerate non-JSON frames
    }
    handleMessage(payload);
  };

  ws.onclose = function () {
    setWsState('disconnected');
    scheduleReconnect();
  };

  ws.onerror = function () {
    try { ws.close(); } catch (err) { /* noop */ }
  };
}

function scheduleReconnect() {
  const delay = Math.min(WS_RETRY_BASE * Math.pow(2, wsRetry), WS_RETRY_MAX);
  wsRetry = Math.min(wsRetry + 1, 20);
  clearTimeout(wsTimer);
  wsTimer = setTimeout(connectWS, delay);
}

/* ---------------- Incoming message router ---------------- */
function handleMessage(payload) {
  if (!payload || typeof payload !== 'object') return;

  const type = String(payload.event || payload.type || '').toLowerCase();
  const data = payload.data !== undefined ? payload.data : payload;

  switch (type) {
    case 'message':
    case 'new_message':
      addFeedItem(data);
      pushLatency(latencyOf(data));
      bumpHourly(timeOf(data));
      break;
    case 'stats':
      updateStats(data);
      seedFromSnapshot(data);
      break;
    case 'error':
      addErrorItem(data);
      break;
    case 'status':
      updateRuntime(data);
      break;
    case 'pong':
    case '':
      break;
    default:
      if (data && (data.latency_ms !== undefined || data.message_text !== undefined || data.text !== undefined)) {
        addFeedItem(data);
      } else if (data && (data.messages_last_24h !== undefined || data.total_messages !== undefined)) {
        updateStats(data);
      }
      break;
  }
}

function latencyOf(d) {
  return Number(d && (d.latency_ms !== undefined ? d.latency_ms : d.latency));
}

function timeOf(d) {
  return d && (d.forwarded_at || d.timestamp || d.ts || d.time) || Date.now();
}

/* ---------------- Runtime status ---------------- */
function updateRuntime(data) {
  const running = data === true || (data && (
    data.running === true ||
    data.status === 'running' ||
    data.state === 'running' ||
    data.is_running === true
  ));
  const pill = $('runtimePill');
  const label = $('runtimeLabel');
  if (pill && label) {
    pill.dataset.state = running ? 'running' : 'stopped';
    label.textContent = running ? t('running') : t('stopped');
  }
  const startBtn = $('startBtn');
  const stopBtn = $('stopBtn');
  if (startBtn) startBtn.disabled = running;
  if (stopBtn) stopBtn.disabled = !running;

  // Status events also carry account identities — render them too.
  if (data && typeof data === 'object') renderAccounts(data);
}

/* ---------------- Account identities (user / bot / source) ---------------- */
function setAccount(cardId, stateId, nameId, metaId, opts) {
  const card = $(cardId);
  const stateEl = $(stateId);
  const nameEl = $(nameId);
  const metaEl = $(metaId);

  const state = opts.state || 'off'; // 'online' | 'idle' | 'off'
  if (card) card.dataset.state = state;
  if (stateEl) {
    stateEl.dataset.state = state;
    const label = stateEl.querySelector('span');
    if (label) label.textContent = opts.stateLabel || t('offline');
  }
  if (nameEl) nameEl.textContent = opts.name || '—';
  if (metaEl) metaEl.textContent = opts.meta || '';
}

function accountStateFor(obj, running, error) {
  if (obj === true) return { state: 'online', label: t('online') };
  const known = obj && (obj.name || obj.username || obj.id);
  if (!obj || !obj.connected) {
    if (known) return { state: 'idle', label: t('signed_in') };
    if (error) return { state: 'off', label: t('offline') };
    return { state: 'off', label: t('offline') };
  }
  if (!running) return { state: 'idle', label: t('signed_in') };
  const authorized = obj.authorized === undefined ? true : obj.authorized;
  if (!authorized) return { state: 'idle', label: t('idle') };
  return { state: 'online', label: t('online') };
}

function accountMeta(obj, error) {
  if (!obj || typeof obj !== 'object') return t('not_connected');
  const handle = obj.username ? '@' + obj.username : (obj.id ? 'ID ' + obj.id : '');
  if (obj.connected) return handle || t('online');
  // Identity is known but the client is idle: still show who it is.
  if (handle) return handle;
  if (error) return String(error).slice(0, 90);
  return t('not_connected');
}

function renderAccounts(data) {
  if (!data || typeof data !== 'object') return;

  const user = (data.user && typeof data.user === 'object') ? data.user : {};
  const bot = (data.bot && typeof data.bot === 'object') ? data.bot : {};
  const running = data.running === true;

  // User account
  const uState = accountStateFor(user, running, data.user_error);
  const uName = user.name || user.username || (user.username ? '@' + user.username : '');
  setAccount('userCard', 'userState', 'userName', 'userMeta', {
    state: uState.state,
    stateLabel: uState.label,
    name: uName || '—',
    meta: accountMeta(user, data.user_error)
  });

  // Bot account
  const bState = accountStateFor(bot, running, data.bot_error);
  const bName = bot.name || bot.username || (bot.username ? '@' + bot.username : '');
  setAccount('botCard', 'botState', 'botName', 'botMeta', {
    state: bState.state,
    stateLabel: bState.label,
    name: bName || '—',
    meta: accountMeta(bot, data.bot_error)
  });

  // Source channel
  const sourceTitle = data.source_title || data.source_channel || '';
  const sState = sourceTitle
    ? (running ? { state: 'online', label: t('source_ready') } : { state: 'idle', label: t('idle') })
    : { state: 'off', label: t('idle') };
  setAccount('sourceCard', 'sourceState', 'sourceName', 'sourceMeta', {
    state: sState.state,
    stateLabel: sState.label,
    name: sourceTitle || '—',
    meta: sourceTitle ? String(sourceTitle) : t('no_source')
  });
}

/* ---------------- Theme (day / night) ---------------- */
const THEME_KEY = 'reposter-theme';

function setTheme(theme) {
  const t2 = theme === 'light' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', t2);
  try { localStorage.setItem(THEME_KEY, t2); } catch (err) { /* private mode */ }
}

function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem(THEME_KEY); } catch (err) { /* ignore */ }
  if (saved) {
    setTheme(saved);
  } else {
    const prefersLight = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
    setTheme(prefersLight ? 'light' : 'dark');
  }
}

function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme');
  setTheme(cur === 'light' ? 'dark' : 'light');
  if (latencyChart) latencyChart.update('none');
  if (hourlyChart) hourlyChart.update('none');
}

/* ---------------- Stat cards (animated count-up) ---------------- */
const statAnim = {};

function animateValue(id, target, decimals) {
  const el = $(id);
  if (!el) return;
  const to = Number(target) || 0;
  const from = statAnim[id] !== undefined ? statAnim[id] : 0;
  if (from === to) { el.textContent = fmtNum(to, decimals); return; }

  const start = performance.now();
  const dur = 600;
  function frame(now) {
    const p = Math.min((now - start) / dur, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    const val = from + (to - from) * eased;
    el.textContent = fmtNum(val, decimals);
    if (p < 1) requestAnimationFrame(frame);
  }
  const wrap = el.closest('.stat-value');
  if (wrap) {
    wrap.classList.remove('pulse');
    void wrap.offsetWidth;
    wrap.classList.add('pulse');
  }
  requestAnimationFrame(frame);
  statAnim[id] = to;
}

function updateStats(data) {
  if (!data || typeof data !== 'object') return;
  const messages = data.messages_last_24h;
  animateValue(
    'statMessages',
    (messages !== undefined ? messages
      : (data.messages_last_days !== undefined ? data.messages_last_days : data.total_messages)) || 0
  );
  const avg = data.avg_latency_ms !== undefined ? data.avg_latency_ms
    : (data.avg_latency !== undefined ? data.avg_latency : 0);
  animateValue('statLatency', avg, 0);
  animateValue('statSuccess', (data.success_rate !== undefined ? data.success_rate : 100), 1);
  animateValue('statErrors', (data.errors_last_days !== undefined ? data.errors_last_days
    : (data.errors !== undefined ? data.errors : 0)));
}

/* ---------------- Charts ---------------- */
let latencyChart = null;
let hourlyChart = null;
const latencyData = [];
const hourlyData = new Array(24).fill(0);

function latencyColor(ms) {
  if (ms < LATENCY_FAST_MS) return '#10b981';
  if (ms < LATENCY_SLOW_MS) return '#f59e0b';
  return '#ef4444';
}

function initCharts() {
  if (typeof Chart === 'undefined') return;

  Chart.defaults.font.family = "'Cairo', 'Segoe UI', sans-serif";
  Chart.defaults.color = '#9a9cb8';
  Chart.defaults.borderColor = 'rgba(38, 38, 74, 0.8)';

  const lCanvas = $('latencyChart');
  if (lCanvas) {
    const ctxL = lCanvas.getContext('2d');
    const gradL = ctxL.createLinearGradient(0, 0, 0, 260);
    gradL.addColorStop(0, 'rgba(74, 158, 255, 0.35)');
    gradL.addColorStop(1, 'rgba(74, 158, 255, 0.02)');

    latencyChart = new Chart(ctxL, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'Latency (ms)',
          data: [],
          fill: true,
          backgroundColor: gradL,
          borderColor: '#4a9eff',
          borderWidth: 2,
          tension: 0.35,
          pointRadius: 3.5,
          pointHoverRadius: 5.5,
          pointBackgroundColor: [],
          pointBorderColor: 'rgba(15,15,35,0.9)',
          pointBorderWidth: 1.5
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 350 },
        interaction: { mode: 'nearest', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1c1c3a',
            borderColor: '#26264a',
            borderWidth: 1,
            titleColor: '#e8e9f3',
            bodyColor: '#9a9cb8',
            callbacks: { label: function (c) { return ' ' + fmtNum(c.parsed.y, 0) + ' ms'; } }
          }
        },
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: 10, maxRotation: 0 } },
          y: {
            grid: { color: 'rgba(38,38,74,0.55)' },
            ticks: { callback: function (v) { return fmtNum(v, 0); } },
            beginAtZero: true
          }
        }
      }
    });
  }

  const hCanvas = $('hourlyChart');
  if (hCanvas) {
    hourlyChart = new Chart(hCanvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: Array.from({ length: 24 }, function (_, i) { return String(i).padStart(2, '0') + ':00'; }),
        datasets: [{
          label: 'Messages',
          data: hourlyData.slice(),
          backgroundColor: 'rgba(74, 158, 255, 0.55)',
          hoverBackgroundColor: '#4a9eff',
          borderRadius: 5,
          borderSkipped: false,
          maxBarThickness: 22
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 350 },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1c1c3a',
            borderColor: '#26264a',
            borderWidth: 1,
            callbacks: { label: function (c) { return ' ' + fmtNum(c.parsed.y, 0) + ' ' + t('msg_unit'); } }
          }
        },
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: 12, maxRotation: 0 } },
          y: {
            grid: { color: 'rgba(38,38,74,0.55)' },
            beginAtZero: true,
            ticks: { precision: 0, callback: function (v) { return fmtNum(v, 0); } }
          }
        }
      }
    });
  }
}

function pushLatency(ms) {
  if (!Number.isFinite(ms)) return;
  latencyData.push(ms);
  if (latencyData.length > LATENCY_CAP) latencyData.shift();
  if (!latencyChart) return;
  const c = latencyChart;
  c.data.labels = latencyData.map(function (_, i) { return '#' + (i + 1); });
  c.data.datasets[0].data = latencyData.slice();
  c.data.datasets[0].pointBackgroundColor = latencyData.map(latencyColor);
  c.update('none');
}

function bumpHourly(ts) {
  const d = ts instanceof Date ? ts : new Date(ts);
  if (Number.isNaN(d.getTime())) return;
  const h = d.getHours();
  hourlyData[h] = (hourlyData[h] || 0) + 1;
  renderHourly();
}

function renderHourly() {
  if (!hourlyChart) return;
  hourlyChart.data.datasets[0].data = hourlyData.slice();
  hourlyChart.update('none');
}

function setHourlyBuckets(buckets) {
  if (!Array.isArray(buckets) || !buckets.length) return;
  hourlyData.fill(0);
  buckets.forEach(function (b) {
    const d = new Date(b.hour);
    if (!Number.isNaN(d.getTime())) {
      hourlyData[d.getHours()] = Number(b.count) || 0;
    }
  });
  renderHourly();
}

async function loadHourlyFromAPI() {
  try {
    const res = await fetch(API_BASE + '/api/stats/hourly?hours=24');
    if (!res.ok) return;
    const j = await res.json();
    setHourlyBuckets(j && j.buckets);
  } catch (err) { /* backend offline — charts stay live via WS */ }
}

/* Seed charts + feed from a realtime stats snapshot (on first paint). */
let seededFromSnapshot = false;
function seedFromSnapshot(data) {
  if (!data || typeof data !== 'object') return;
  if (Array.isArray(data.messages_per_hour) && !hourlyChartHasData()) {
    setHourlyBuckets(data.messages_per_hour);
  }
  if (!seededFromSnapshot && Array.isArray(data.recent_messages) && data.recent_messages.length) {
    const list = $('feedList');
    const empty = list && list.querySelector('.feed-empty');
    if (empty) empty.remove();
    data.recent_messages.slice().reverse().forEach(function (m) {
      appendFeedItem(m, true);
      pushLatency(latencyOf(m));
    });
    seededFromSnapshot = true;
  }
}

function hourlyChartHasData() {
  return hourlyData.some(function (v) { return v > 0; });
}

/* ---------------- Live feed ---------------- */
function latencyClass(ms) {
  if (ms < LATENCY_FAST_MS) return 'latency-fast';
  if (ms < LATENCY_SLOW_MS) return 'latency-medium';
  return 'latency-slow';
}

function statusOk(data) {
  if (!data || data.status === undefined || data.status === null) return true;
  const s = String(data.status).toLowerCase();
  return s === 'ok' || s === 'success' || s === 'sent' || s === 'forwarded';
}

/* ---------------- Content types ---------------- */
const TYPE_KEYS = ['text', 'photo', 'video', 'document', 'audio', 'voice',
  'video_note', 'sticker', 'gif', 'poll', 'location', 'contact'];

function normalizeType(value) {
  const kind = String(value || '').toLowerCase().replace(/[\s-]+/g, '_');
  return TYPE_KEYS.indexOf(kind) >= 0 ? kind : 'unknown';
}

function typeLabel(kind) {
  return t('type_' + normalizeType(kind));
}

function buildFeedItem(data) {
  const src = String(data.source_channel || data.source || data.channel || data.from || '—');
  const text = String(data.message_text || data.text || data.preview || data.message || data.content || '');
  const preview = text.length > 100 ? text.slice(0, 100) + '…' : text;
  const ms = latencyOf(data);
  const ok = statusOk(data);
  const ts = timeOf(data);

  const li = document.createElement('li');
  li.className = 'feed-item';

  const srcEl = document.createElement('span');
  srcEl.className = 'feed-src';
  srcEl.textContent = src;

  const kind = normalizeType(data.content_type || data.type || '');
  const typeEl = document.createElement('span');
  typeEl.className = 'feed-type';
  typeEl.dataset.kind = kind;
  typeEl.textContent = typeLabel(kind);

  const prevEl = document.createElement('span');
  prevEl.className = 'feed-preview';
  prevEl.textContent = preview || '—';
  prevEl.title = text;

  const meta = document.createElement('span');
  meta.className = 'feed-meta';

  const chip = document.createElement('span');
  chip.className = 'latency-chip ' + latencyClass(ms || 0);
  chip.textContent = fmtNum(ms || 0, 0) + ' ms';

  const timeEl = document.createElement('span');
  timeEl.className = 'feed-time';
  timeEl.textContent = fmtTime(ts);

  const statusEl = document.createElement('span');
  statusEl.className = 'feed-status ' + (ok ? 'ok' : 'fail');
  statusEl.textContent = ok ? t('ok') : t('failed');

  meta.appendChild(chip);
  meta.appendChild(timeEl);
  meta.appendChild(statusEl);

  li.appendChild(srcEl);
  li.appendChild(typeEl);
  li.appendChild(prevEl);
  li.appendChild(meta);
  return li;
}

function updateFeedCount() {
  const list = $('feedList');
  if (list) setText('feedCount', fmtNum(list.children.length, 0));
}

function appendFeedItem(data, quiet) {
  const list = $('feedList');
  if (!list) return;

  // The feed is seeded from the REST list and then kept live by WebSocket
  // events, so the same message can arrive twice. Deduplicate on the DB row id
  // (falling back to the source message id).
  const key = String(
    (data && (data.id || data.row_id || data.source_msg_id)) ||
    ((data && data.source_channel) || '') + '|' + timeOf(data) + '|' + (data && data.text_preview)
  );
  if (list.querySelector('[data-key="' + key.replace(/"/g, '') + '"]')) return;

  const empty = list.querySelector('.feed-empty');
  if (empty) empty.remove();
  const item = buildFeedItem(data);
  item.dataset.key = key;
  list.prepend(item);
  while (list.children.length > FEED_CAP) list.lastElementChild.remove();
  if (!quiet) {
    updateFeedCount();
    bumpHourly(timeOf(data));
  } else {
    updateFeedCount();
  }
}

function addFeedItem(data) {
  if (!data || typeof data !== 'object') return;
  appendFeedItem(data, false);
}

/* ---------------- Errors ---------------- */
function addErrorItem(data) {
  const list = $('errorsList');
  if (!list) return;

  const empty = list.querySelector('.errors-empty');
  if (empty) empty.remove();

  const d = (data && typeof data === 'object') ? data : {};
  const ts = d.forwarded_at || d.timestamp || d.ts || Date.now();

  // Structured fields (from the backend error catalog) if present.
  const code = d.code || null;
  const title = d.title || null;
  const explain = d.explain || d.message || d.error || d.text || null;
  const hint = d.hint || null;
  const steps = Array.isArray(d.steps) ? d.steps.filter(Boolean) : [];
  const detail = d.detail || d.error_msg || null;
  const raw = typeof data === 'string' ? data : null;

  const li = document.createElement('li');
  li.className = 'error-item' + ((title || steps.length) ? ' err-detailed' : '');

  const head = document.createElement('div');
  head.className = 'err-head';

  if (code) {
    const badge = document.createElement('span');
    badge.className = 'err-badge';
    badge.textContent = code;
    head.appendChild(badge);
  }

  const titleEl = document.createElement('span');
  titleEl.className = 'err-title';
  titleEl.textContent = title || t('error_title');
  head.appendChild(titleEl);

  const timeEl = document.createElement('span');
  timeEl.className = 'err-time';
  timeEl.style.marginInlineStart = 'auto';
  timeEl.textContent = fmtTime(ts);
  head.appendChild(timeEl);

  li.appendChild(head);

  const msgText = raw || explain || t('unknown_error');
  const msgEl = document.createElement('div');
  msgEl.className = 'err-msg';
  msgEl.textContent = String(msgText).slice(0, 400);
  li.appendChild(msgEl);

  if (hint) {
    const hintEl = document.createElement('div');
    hintEl.className = 'err-hint';
    hintEl.textContent = hint;
    li.appendChild(hintEl);
  }

  if (steps.length) {
    const ol = document.createElement('ol');
    ol.className = 'err-steps';
    steps.forEach(function (s) {
      const stepLi = document.createElement('li');
      stepLi.textContent = String(s);
      ol.appendChild(stepLi);
    });
    li.appendChild(ol);
  }

  if (detail && detail !== msgText) {
    const detEl = document.createElement('div');
    detEl.className = 'err-detail';
    detEl.textContent = String(detail).slice(0, 500);
    li.appendChild(detEl);
  }

  list.prepend(li);
  while (list.children.length > 30) list.lastElementChild.remove();

  const count = $('errorCount');
  if (count) count.textContent = fmtNum(list.children.length, 0);
  animateValue('statErrors', statAnim.statErrors !== undefined ? statAnim.statErrors + 1 : list.children.length);
}

/* ---------------- REST ---------------- */
async function api(path, options) {
  const res = await fetch(API_BASE + path, Object.assign({
    headers: { 'Content-Type': 'application/json' }
  }, options || {}));
  if (!res.ok) {
    // Try to read the structured error the backend sends in `detail`.
    let payload = null;
    try { payload = await res.json(); } catch (err) { /* not JSON */ }
    const detail = payload && payload.detail;
    const err = new Error('HTTP ' + res.status + ' ' + path);
    err.status = res.status;
    if (detail && typeof detail === 'object') {
      err.structured = detail;
    } else if (typeof detail === 'string') {
      err.structured = { title: t('error_title'), message: detail };
    }
    // A locked dashboard: drop the live view and show the gate again.
    if (res.status === 401 && !path.startsWith('/api/auth/')) {
      handleAuthExpired();
    }
    throw err;
  }
  return res.json();
}

/* The session cookie expired or was revoked: re-open the lock screen. */
let reAuthing = false;
function handleAuthExpired() {
  if (reAuthing) return;
  reAuthing = true;
  appUnlocked = false;
  if (ws) { try { ws.close(); } catch (e) { /* ignore */ } }
  if (isAuthGateHidden()) { document.body.classList.remove('locked'); }
  else openAuth('login');
  setTimeout(function () { reAuthing = false; }, 1500);
}

/* Surface a structured error both as a detailed toast and in the error list. */
function reportError(err, fallbackKey) {
  const s = err && err.structured;
  if (s && (s.title || s.message || s.hint || (s.steps && s.steps.length))) {
    toastDetailed(s.title || t('error_title'), s.hint || s.message || '', 'error');
    addErrorItem({
      code: s.code,
      title: s.title,
      explain: s.message,
      hint: s.hint,
      steps: s.steps,
      detail: s.detail,
      timestamp: Date.now()
    });
  } else {
    toast(t(fallbackKey), 'error');
  }
}

async function loadConfig() {
  try {
    const cfg = await api('/api/config');
    if (!cfg || typeof cfg !== 'object') return;
    const set = function (id, val) { const el = $(id); if (el) el.value = val; };
    set('cfgApiId', cfg.api_id != null ? cfg.api_id : '');
    set('cfgApiHash', cfg.api_hash != null ? cfg.api_hash : '');
    set('cfgBotToken', cfg.bot_token != null ? cfg.bot_token : '');
    set('cfgSource', cfg.source_channel != null ? cfg.source_channel : '');
    set('cfgDest', cfg.destination_channel != null ? cfg.destination_channel : '');
    const mode = $('cfgMode');
    if (mode) mode.value = cfg.repost_mode || 'copy';
  } catch (err) {
    toast(t('toast_cfg_load_fail'), 'error');
  }
}

async function saveConfig(e) {
  e.preventDefault();
  const val = function (id) { const el = $(id); return el ? el.value.trim() : ''; };

  // Secrets are never sent back as masked values: a field left untouched
  // (or still showing the masked placeholder) is omitted so the stored
  // real value is preserved. Only a freshly typed value replaces it.
  const apiHash = val('cfgApiHash');
  const botToken = val('cfgBotToken');

  const body = {
    api_id: val('cfgApiId'),
    source_channel: val('cfgSource'),
    destination_channel: val('cfgDest'),
    repost_mode: 'copy'
  };
  if (apiHash && apiHash.indexOf('*') === -1) body.api_hash = apiHash;
  if (botToken && botToken.indexOf('*') === -1) body.bot_token = botToken;

  try {
    const res = await api('/api/config?lang=' + lang, { method: 'POST', body: JSON.stringify(body) });
    // The response carries a fresh status snapshot (and whether a running
    // reposter was restarted) so the account cards update immediately.
    if (res && res.status) updateRuntime(res.status);
    if (res && res.restart_error) {
      reportError(res.restart_error, 'toast_save_fail');
    } else if (res && res.restarted) {
      toast(t('toast_saved_restarted'), 'success');
    } else {
      toast(t('toast_saved'), 'success');
    }
    loadConfig();
    if (!res || !res.status) loadStatus();
  } catch (err) {
    reportError(err, 'toast_save_fail');
  }
}

async function startReposter() {
  try {
    const res = await api('/api/start?lang=' + lang, { method: 'POST' });
    updateRuntime({ running: true });
    if (res && res.status === 'already_running' && res.error) {
      toastDetailed(res.error.title || t('error_title'), res.error.hint || res.error.message || '', 'info');
    } else {
      toast(t('toast_started'), 'success');
    }
  } catch (err) {
    reportError(err, 'toast_start_fail');
  }
}

async function stopReposter() {
  try {
    await api('/api/stop', { method: 'POST' });
    updateRuntime({ running: false });
    toast(t('toast_stopped'), 'info');
  } catch (err) {
    toast(t('toast_stop_fail'), 'error');
  }
}

async function loadHeadlineStats() {
  try {
    const s = await api('/api/stats?days=1');
    updateStats(s);
  } catch (err) { /* WS will populate */ }
}

/* ---------------- Confirm modal (replaces window.confirm) ---------------- */
let confirmAcceptFn = null;

function modalConfirm(opts) {
  return new Promise(function (resolve) {
    const overlay = $('confirmOverlay');
    if (!overlay) { resolve(false); return; }

    const icon = $('confirmIcon');
    const title = $('confirmTitle');
    const msg = $('confirmMessage');
    const accept = $('confirmAccept');
    const cancel = $('confirmCancel');

    if (icon) icon.dataset.tone = (opts && opts.tone) || 'danger';
    if (title) title.textContent = (opts && opts.title) || t('confirm');
    if (msg) msg.textContent = (opts && opts.message) || '';
    if (accept) {
      accept.textContent = (opts && opts.acceptLabel) || t('confirm');
      accept.className = 'btn ' + (((opts && opts.tone) === 'info') ? 'btn-primary' : 'btn-danger');
    }
    if (cancel) cancel.textContent = t('cancel');

    confirmAcceptFn = function () { closeConfirm(); resolve(true); };
    overlay.hidden = false;
    overlay.classList.remove('collapsed');
    if (accept) accept.focus();
  });
}

function closeConfirm() {
  const overlay = $('confirmOverlay');
  if (overlay) { overlay.classList.add('collapsed'); overlay.hidden = true; }
  confirmAcceptFn = null;
}

/* ---------------- Dashboard lock / gate ---------------- */
let appUnlocked = false;
let bootRan = false;
let authMode = 'login'; // login | setup | change

function setAuthError(errObj) {
  const box = $('authError');
  if (!box) return;
  if (!errObj) { box.classList.add('collapsed'); box.textContent = ''; return; }
  box.textContent = '';
  const strong = document.createElement('strong');
  strong.textContent = errObj.title || t('error_title');
  box.appendChild(strong);
  const span = document.createElement('span');
  span.textContent = errObj.message || errObj.detail || '';
  box.appendChild(span);
  box.classList.remove('collapsed');
}

function openAuth(mode) {
  // The lock screen is UX-HIDDEN: skip it entirely.
  if (isAuthGateHidden()) { document.body.classList.remove('locked'); return; }

  authMode = mode || 'login';
  const overlay = $('authOverlay');
  const title = $('authTitle');
  const sub = $('authSubtitle');
  const curField = $('authCurrentField');
  const curLabel = $('authCurrentLabel');
  const confirmField = $('authConfirmField');
  const submitLabel = $('authSubmitLabel');
  const note = $('authNote');

  const isSetup = authMode === 'setup';
  const isChange = authMode === 'change';
  const isDisable = authMode === 'disable';

  if (title) {
    title.textContent = isSetup ? t('auth_setup_title')
      : (isChange ? t('auth_change_title')
        : (isDisable ? t('access_toggle_label') : t('auth_locked_title')));
  }
  if (sub) {
    sub.textContent = isSetup ? t('auth_setup_sub')
      : (isChange ? t('auth_change_sub')
        : (isDisable ? t('confirm_disable_lock') : t('auth_locked_sub')));
  }
  if (curLabel) curLabel.textContent = isChange ? t('auth_change_current') : t('auth_password');
  if (curField) curField.classList.remove('collapsed');
  // setup + change both need a confirmation field (disable does not)
  if (confirmField) confirmField.classList.toggle('collapsed', !(isSetup || isChange));
  if (submitLabel) {
    submitLabel.textContent = isSetup ? t('auth_create')
      : (isChange ? t('auth_update')
        : (isDisable ? t('confirm') : t('auth_unlock')));
  }
  if (note) note.textContent = t('auth_note');

  const cur = $('authCurrent');
  const conf = $('authConfirm');
  if (cur) cur.value = '';
  if (conf) conf.value = '';
  setAuthError(null);

  document.body.classList.add('locked');
  if (overlay) { overlay.hidden = false; overlay.classList.remove('collapsed'); }
  if (cur) cur.focus();
}

function closeAuth() {
  const overlay = $('authOverlay');
  if (overlay) { overlay.classList.add('collapsed'); overlay.hidden = true; }
  document.body.classList.remove('locked');
}

function setAuthLoading(on) {
  const btn = $('authSubmit');
  if (btn) btn.classList.toggle('loading', !!on);
  const cur = $('authCurrent');
  if (cur) cur.disabled = !!on;
}

async function submitAuth(e) {
  if (e) e.preventDefault();
  const cur = $('authCurrent');
  const conf = $('authConfirm');
  const first = cur ? cur.value : '';
  const second = conf ? conf.value : '';
  setAuthError(null);

  let path = '/api/auth/login';
  let body = { password: first };

  if (authMode === 'setup') {
    if (first.length < 6) { setAuthError({ title: t('error_title'), message: t('auth_too_short') }); return; }
    if (second !== first) { setAuthError({ title: t('error_title'), message: t('auth_mismatch') }); return; }
    path = '/api/auth/setup';
  } else if (authMode === 'change') {
    // Field 1 holds the current password, the confirmation field the new one.
    if (second.length < 6) { setAuthError({ title: t('error_title'), message: t('auth_too_short') }); return; }
    path = '/api/auth/password';
    body = { current: first, new_password: second, confirm: second };
  } else if (authMode === 'disable') {
    path = '/api/auth/disable';
    body = { password: first };
  }

  setAuthLoading(true);
  try {
    await api(path, { method: 'POST', body: JSON.stringify(body) });
    const wasSetup = authMode === 'setup';
    const wasChange = authMode === 'change';
    const wasDisable = authMode === 'disable';

    closeAuth();

    if (wasDisable) {
      lastAuthState = { configured: false, enabled: false, authenticated: true };
      renderAccessState(lastAuthState);
      toast(t('toast_lock_off'), 'info');
      return;
    }

    lastAuthState = { configured: true, enabled: true, authenticated: true };
    renderAccessState(lastAuthState);
    toast(wasSetup ? t('toast_lock_on') : (wasChange ? t('toast_auth_changed') : t('toast_auth_welcome')), 'success');
    if (wasChange) return;
    unlockApp();
  } catch (err) {
    if (authMode === 'change') { toast(t('auth_error_generic'), 'error'); }
    if (err.structured) setAuthError(err.structured);
    else setAuthError({ title: t('error_title'), message: t('auth_error_generic') });
  } finally {
    setAuthLoading(false);
  }
}

/* Release the dashboard: fade the lock, start the live stream + data load. */
function unlockApp() {
  appUnlocked = true;
  document.body.classList.remove('locked');
  if (lastAuthState && lastAuthState.enabled) renderAccessState(lastAuthState);
  if (!bootRan) { bootRan = true; bootApp(); }
}

/* Ask the backend whether this browser is unlocked, then gate accordingly. */
async function checkAuth() {
  let state = { configured: false, enabled: false, authenticated: true };
  try {
    state = await api('/api/auth/state');
  } catch (err) { /* backend down: gate will show on next poll */ }

  renderAccessState(state);

  // The lock screen is hidden from the interface (UX-HIDDEN): never block.
  if (isAuthGateHidden()) {
    document.body.classList.remove('locked');
    unlockApp();
    return;
  }

  if (state && state.authenticated) {
    unlockApp();
    return;
  }
  openAuth(state && !state.configured ? 'setup' : 'login');
}

/* True when the lock overlay is marked as UX-HIDDEN in the markup. */
function isAuthGateHidden() {
  const overlay = $('authOverlay');
  return !!(overlay && overlay.hasAttribute('data-ux-hidden'));
}

/* Reflect the lock state in the access card (switch + labels). */
function renderAccessState(state) {
  const enabled = !!(state && state.enabled);
  const sw = $('authSwitch');
  if (sw) sw.setAttribute('aria-checked', String(enabled));

  const label = $('accessStateLabel');
  if (label) label.textContent = enabled ? t('auth_lock_enabled') : t('auth_lock_disabled');

  const lock = $('accessState');
  if (lock) lock.dataset.state = enabled ? 'locked' : 'unlocked';

  const hint = $('accessToggleHint');
  if (hint) hint.textContent = enabled ? t('access_toggle_on_hint') : t('access_toggle_off_hint');

  const changeBtn = $('changePasswordBtn');
  if (changeBtn) changeBtn.classList.toggle('collapsed', !enabled);
  const lockBtn = $('lockNowBtn');
  if (lockBtn) lockBtn.classList.toggle('collapsed', !enabled);

  lastAuthState = state || null;
}

let lastAuthState = null;

/* Flip the password lock on or off from the access card switch. */
async function toggleAuthLock() {
  const enabled = !!(lastAuthState && lastAuthState.enabled);
  if (!enabled) {
    // Turning ON: reuse the gate modal in setup mode to choose a password.
    openAuth('setup');
    return;
  }
  // Turning OFF: ask for the current password, then clear it.
  const ok = await modalConfirm({
    tone: 'warning',
    title: t('access_toggle_label'),
    message: t('confirm_disable_lock'),
    acceptLabel: t('confirm'),
  });
  if (!ok) return;
  openAuth('disable');
}

async function lockNow() {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch (err) { /* ignore */ }
  appUnlocked = false;
  if (lastAuthState) lastAuthState.authenticated = false;
  if (ws) { try { ws.close(); } catch (e) { /* ignore */ } }
  openAuth('login');
  toast(t('toast_auth_locked'), 'info');
}

async function changePassword() {
  openAuth('change');
  setAuthError(null);

  const cur = $('authCurrent');
  const conf = $('authConfirm');
  const curLabel = $('authCurrentLabel');
  const note = $('authNote');
  if (cur) cur.value = '';
  if (conf) conf.value = '';
  if (curLabel) curLabel.textContent = t('auth_change_current');
  if (note) note.textContent = t('auth_change_sub');
}

/* ---------------- Maintenance buttons ---------------- */
async function resetCounters() {
  const ok = await modalConfirm({
    tone: 'warning',
    title: t('confirm_title_reset'),
    message: t('confirm_reset'),
    acceptLabel: t('confirm'),
  });
  if (!ok) return;
  try {
    const res = await api('/api/stats/reset', { method: 'POST' });
    if (res && res.stats) updateStats(res.stats);
    if (res && res.hourly) setHourlyBuckets(res.hourly);
    resetCharts();
    toast(t('toast_reset'), 'success');
  } catch (err) {
    reportError(err, 'toast_reset_fail');
  }
}

async function clearLogHistory() {
  const ok = await modalConfirm({
    tone: 'danger',
    title: t('confirm_title_clear'),
    message: t('confirm_clear'),
    acceptLabel: t('confirm'),
  });
  if (!ok) return;
  try {
    const res = await api('/api/messages/clear', { method: 'POST' });
    if (res && res.stats) updateStats(res.stats);
    if (res && res.hourly) setHourlyBuckets(res.hourly);
    else resetCharts();

    const feed = $('feedList');
    if (feed) {
      feed.textContent = '';
      const empty = document.createElement('li');
      empty.className = 'feed-empty';
      empty.textContent = t('feed_empty');
      feed.appendChild(empty);
      updateFeedCount();
    }
    const errs = $('errorsList');
    if (errs) {
      errs.textContent = '';
      const empty = document.createElement('li');
      empty.className = 'feed-empty errors-empty';
      empty.textContent = t('errors_empty');
      errs.appendChild(empty);
      const errCount = $('errorCount');
      if (errCount) errCount.textContent = '0';
    }
    toast(t('toast_cleared'), 'success');
  } catch (err) {
    reportError(err, 'toast_clear_fail');
  }
}

/* Zero the local chart series so the graphs match the reset counters. */
function resetCharts() {
  latencyData.length = 0;
  if (latencyChart) {
    latencyChart.data.labels = [];
    latencyChart.data.datasets[0].data = [];
    latencyChart.update('none');
  }
  hourlyData.fill(0);
  if (hourlyChart) {
    hourlyChart.data.datasets[0].data = hourlyData.slice();
    hourlyChart.update('none');
  }
}

async function loadInitialFeed() {
  try {
    const r = await api('/api/messages?limit=' + FEED_CAP);
    const rows = r && r.messages;
    if (!Array.isArray(rows) || !rows.length) return;
    const list = $('feedList');
    const empty = list && list.querySelector('.feed-empty');
    if (empty) empty.remove();
    rows.slice().reverse().forEach(function (m) {
      appendFeedItem(m, true);
      pushLatency(latencyOf(m));
      if (seededFromSnapshot === false) bumpHourly(timeOf(m));
    });
    seededFromSnapshot = true;
    renderHourly();
  } catch (err) { /* optional */ }
}

async function loadErrors() {
  try {
    const r = await api('/api/errors?limit=30&lang=' + lang);
    const rows = r && r.errors;
    if (!Array.isArray(rows) || !rows.length) return;
    const list = $('errorsList');
    const empty = list && list.querySelector('.errors-empty');
    if (empty) empty.remove();
    rows.slice().reverse().forEach(function (e) { addErrorItem(e); });
  } catch (err) { /* optional */ }
}

async function pollStatus() {
  try {
    const st = await api('/api/status');
    updateRuntime(st);
  } catch (err) { /* backend may be down; WS keeps UI alive */ }
}

/* ---------------- i18n apply ---------------- */
function applyLang() {
  const html = document.documentElement;
  html.lang = lang;
  html.dir = lang === 'ar' ? 'rtl' : 'ltr';

  document.querySelectorAll('[data-i18n]').forEach(function (el) {
    const key = el.getAttribute('data-i18n');
    const val = t(key);
    if (val !== undefined && val !== null) el.textContent = val;
  });

  // Translate an element's value attribute (used by read-only inputs such as
  // the fixed "Copy" repost-mode field).
  document.querySelectorAll('[data-i18n-value]').forEach(function (el) {
    const key = el.getAttribute('data-i18n-value');
    const val = t(key);
    if (val !== undefined && val !== null) el.value = val;
  });

  const langBtn = $('langToggle');
  if (langBtn) langBtn.textContent = t('lang_toggle');

  // Refresh empty states
  const feedEmpty = document.querySelector('.feed-empty:not(.errors-empty)');
  if (feedEmpty) feedEmpty.textContent = t('feed_empty');
  const errEmpty = document.querySelector('.errors-empty');
  if (errEmpty) errEmpty.textContent = t('errors_empty');

  // Re-translate content-type badges already rendered in the feed
  document.querySelectorAll('.feed-type').forEach(function (el) {
    el.textContent = typeLabel(el.dataset.kind);
  });

  updateFeedCount();
  const errCount = $('errorCount');
  const errs = $('errorsList');
  if (errCount && errs) errCount.textContent = fmtNum(errs.children.length, 0);

  if (latencyChart) latencyChart.update('none');
  if (hourlyChart) hourlyChart.update('none');

  if (lastLoginStatus) renderLogin(lastLoginStatus);

  // Re-label the modals if they are open (language may switch while locked).
  const authOverlay = $('authOverlay');
  if (authOverlay && !authOverlay.hidden) openAuth(authMode);

  // Refresh the access card labels in the new language.
  if (lastAuthState) renderAccessState(lastAuthState);
}

function toggleLang() {
  lang = lang === 'en' ? 'ar' : 'en';
  applyLang();
}

/* ---------------- User-account login ---------------- */
let lastLoginStatus = null;
const LOGIN_STEPS = {
  idle: 'loginStepPhone',
  code_sent: 'loginStepCode',
  password_needed: 'loginStepPassword',
  authorized: 'loginStepDone'
};

function showLoginError(errObj) {
  const box = $('loginError');
  if (!box) return;
  if (!errObj) { box.classList.add('collapsed'); box.textContent = ''; return; }
  box.textContent = '';
  const title = document.createElement('span');
  title.className = 'le-title';
  title.textContent = errObj.title || t('error_title');
  box.appendChild(title);
  const body = document.createElement('span');
  body.textContent = errObj.message || '';
  box.appendChild(body);
  if (errObj.hint) {
    const hint = document.createElement('span');
    hint.className = 'le-hint';
    hint.textContent = errObj.hint;
    box.appendChild(hint);
  }
  box.classList.remove('collapsed');
}

function clearLoginError() { showLoginError(null); }

/* Which step the card was last auto-collapsed for, so a manual expand is not
   undone by the 15-second status poll. */
let loginAutoStep = null;

function setLoginCollapsed(collapsed) {
  const body = $('loginBody');
  const toggle = $('loginToggle');
  if (!body) return;
  body.classList.toggle('collapsed', collapsed);
  if (toggle) toggle.setAttribute('aria-expanded', String(!collapsed));
}

function renderLogin(status) {
  const step = (status && status.step) || 'idle';
  const pill = $('loginPill');
  const pillLabel = $('loginPillLabel');
  if (pill) pill.dataset.state = step;
  if (pillLabel) {
    const key = 'login_state_' + step;
    const label = t(key);
    pillLabel.textContent = (label && label !== key) ? label : t('login_state_idle');
  }

  // Show only the panel that matches the current step.
  Object.keys(LOGIN_STEPS).forEach(function (key) {
    const el = $(LOGIN_STEPS[key]);
    if (el) el.classList.toggle('collapsed', key !== step);
  });

  // Once a session is registered the whole card folds away automatically: on
  // the first load and right after the session is saved. A manual expand is
  // respected until the step changes again.
  if (step === 'authorized' && loginAutoStep !== 'authorized') {
    setLoginCollapsed(true);
    loginAutoStep = 'authorized';
  } else if (step !== 'authorized') {
    setLoginCollapsed(false);
    loginAutoStep = step;
  }

  // Fill the authorized summary.
  if (step === 'authorized' && status && status.user) {
    const nameEl = $('loginUserName');
    const metaEl = $('loginUserMeta');
    const u = status.user;
    if (nameEl) nameEl.textContent = u.name || t('login_signed_in');
    if (metaEl) {
      const bits = [];
      if (u.username) bits.push('@' + u.username);
      if (u.id) bits.push('id ' + u.id);
      if (u.phone) bits.push(u.phone);
      metaEl.textContent = bits.join(' · ');
    }
  }

  // Keep the phone field populated so a reload shows what was entered.
  if (status && status.phone) {
    const phoneEl = $('loginPhone');
    if (phoneEl && !phoneEl.value) phoneEl.value = status.phone;
  }
}

async function loadLoginStatus() {
  try {
    const st = await api('/api/login/status?lang=' + lang);
    lastLoginStatus = st;
    renderLogin(st);
  } catch (err) { /* backend may be starting; non-fatal */ }
}

function handleLoginResult(res) {
  if (res && res.status) { lastLoginStatus = res.status; renderLogin(res.status); }
  if (res && res.error) {
    showLoginError(res.error);
    toastDetailed(res.error.title || t('error_title'), res.error.hint || res.error.message || '', 'error');
    return false;
  }
  clearLoginError();
  return true;
}

async function loginStart() {
  const phoneEl = $('loginPhone');
  const phone = phoneEl ? phoneEl.value.trim() : '';
  try {
    const res = await api('/api/login/start?lang=' + lang, {
      method: 'POST', body: JSON.stringify({ phone: phone })
    });
    if (handleLoginResult(res)) {
      if (res.status && res.status.step === 'authorized') {
        toast(t('login_success'), 'success');
      } else {
        toast(t('login_code_sent_toast'), 'success');
        const codeEl = $('loginCode');
        if (codeEl) codeEl.focus();
      }
    }
  } catch (err) {
    if (err.structured) { handleLoginResult({ error: err.structured }); }
    else toast(t('toast_start_fail'), 'error');
  }
}

async function loginSubmitCode() {
  const codeEl = $('loginCode');
  const code = codeEl ? codeEl.value.trim() : '';
  try {
    const res = await api('/api/login/code?lang=' + lang, {
      method: 'POST', body: JSON.stringify({ code: code })
    });
    if (handleLoginResult(res)) {
      if (res.status && res.status.step === 'authorized') {
        toast(t('login_success'), 'success');
      } else if (res.status && res.status.step === 'password_needed') {
        toast(t('login_password_needed_toast'), 'info');
        const passEl = $('loginPassword');
        if (passEl) passEl.focus();
      }
    }
  } catch (err) {
    if (err.structured) { handleLoginResult({ error: err.structured }); }
    else toast(t('toast_start_fail'), 'error');
  }
}

async function loginSubmitPassword() {
  const passEl = $('loginPassword');
  const password = passEl ? passEl.value : '';
  try {
    const res = await api('/api/login/password?lang=' + lang, {
      method: 'POST', body: JSON.stringify({ password: password })
    });
    if (handleLoginResult(res)) toast(t('login_success'), 'success');
  } catch (err) {
    if (err.structured) { handleLoginResult({ error: err.structured }); }
    else toast(t('toast_start_fail'), 'error');
  }
}

async function loginLogout() {
  try {
    const st = await api('/api/login/logout', { method: 'POST' });
    renderLogin(st);
    clearLoginError();
    toast(t('login_logout'), 'info');
  } catch (err) {
    toast(t('toast_stop_fail'), 'error');
  }
}

/* ---------------- Boot ---------------- */
function boot() {
  initTheme();

  // Dashboard lock wiring (always active, even before unlock)
  const authForm = $('authForm');
  if (authForm) authForm.addEventListener('submit', submitAuth);
  const confirmAccept = $('confirmAccept');
  if (confirmAccept) confirmAccept.addEventListener('click', function () {
    if (confirmAcceptFn) confirmAcceptFn();
  });
  const confirmCancel = $('confirmCancel');
  if (confirmCancel) confirmCancel.addEventListener('click', closeConfirm);
  const confirmOverlay = $('confirmOverlay');
  if (confirmOverlay) confirmOverlay.addEventListener('click', function (e) {
    if (e.target === confirmOverlay) closeConfirm();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (confirmOverlay && !confirmOverlay.hidden) closeConfirm();
  });

  // Reveal-password buttons inside the auth modal
  document.querySelectorAll('.reveal-btn[data-reveal]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const input = $(btn.getAttribute('data-reveal'));
      if (!input) return;
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.classList.toggle('on', show);
    });
  });

  const accessToggle = $('accessToggle');
  if (accessToggle) {
    accessToggle.addEventListener('click', function () {
      const body = $('accessBody');
      if (!body) return;
      const collapsed = body.classList.toggle('collapsed');
      accessToggle.setAttribute('aria-expanded', String(!collapsed));
    });
  }
  const changeBtn = $('changePasswordBtn');
  if (changeBtn) changeBtn.addEventListener('click', changePassword);
  const lockBtn = $('lockNowBtn');
  if (lockBtn) lockBtn.addEventListener('click', lockNow);
  const authSwitch = $('authSwitch');
  if (authSwitch) authSwitch.addEventListener('click', toggleAuthLock);

  // Gate the whole dashboard behind the password modal.
  checkAuth();
}

/* Everything below runs only once the dashboard is unlocked. */
function bootApp() {
  initCharts();

  // Empty states
  const feed = $('feedList');
  if (feed && !feed.children.length) {
    const feedEmpty = document.createElement('li');
    feedEmpty.className = 'feed-empty';
    feedEmpty.textContent = t('feed_empty');
    feed.appendChild(feedEmpty);
  }
  const errs = $('errorsList');
  if (errs && !errs.children.length) {
    const errEmpty = document.createElement('li');
    errEmpty.className = 'feed-empty errors-empty';
    errEmpty.textContent = t('errors_empty');
    errs.appendChild(errEmpty);
  }

  // Wire controls
  const cfgForm = $('configForm');
  if (cfgForm) cfgForm.addEventListener('submit', saveConfig);
  const startBtn = $('startBtn');
  if (startBtn) startBtn.addEventListener('click', startReposter);
  const stopBtn = $('stopBtn');
  if (stopBtn) stopBtn.addEventListener('click', stopReposter);
  const langBtn = $('langToggle');
  if (langBtn) langBtn.addEventListener('click', toggleLang);

  const themeBtn = $('themeToggle');
  if (themeBtn) themeBtn.addEventListener('click', toggleTheme);

  const resetBtn = $('resetCounters');
  if (resetBtn) resetBtn.addEventListener('click', resetCounters);
  const clearBtn = $('clearLog');
  if (clearBtn) clearBtn.addEventListener('click', clearLogHistory);

  const loginToggle = $('loginToggle');
  if (loginToggle) {
    loginToggle.addEventListener('click', function () {
      const body = $('loginBody');
      if (!body) return;
      const collapsed = body.classList.toggle('collapsed');
      loginToggle.setAttribute('aria-expanded', String(!collapsed));
    });
  }

  const cfgToggle = $('configToggle');
  if (cfgToggle) {
    cfgToggle.addEventListener('click', function () {
      const body = $('configBody');
      if (!body) return;
      const collapsed = body.classList.toggle('collapsed');
      cfgToggle.setAttribute('aria-expanded', String(!collapsed));
    });
  }

  const guideToggle = $('guideToggle');
  if (guideToggle) {
    guideToggle.addEventListener('click', function () {
      const body = $('guideBody');
      if (!body) return;
      const collapsed = body.classList.toggle('collapsed');
      guideToggle.setAttribute('aria-expanded', String(!collapsed));
    });
  }

  // Copy-to-clipboard buttons on credential fields
  document.querySelectorAll('.copy-btn[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const target = $(btn.getAttribute('data-copy'));
      if (target) copyText(target.value);
    });
  });

  // User-account login wiring
  const loginSend = $('loginSendCode');
  if (loginSend) loginSend.addEventListener('click', loginStart);
  const loginPhoneEl = $('loginPhone');
  if (loginPhoneEl) loginPhoneEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); loginStart(); }
  });
  const loginVerify = $('loginSubmitCode');
  if (loginVerify) loginVerify.addEventListener('click', loginSubmitCode);
  const loginCodeEl = $('loginCode');
  if (loginCodeEl) loginCodeEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); loginSubmitCode(); }
  });
  const loginResend = $('loginResend');
  if (loginResend) loginResend.addEventListener('click', loginStart);
  const loginSignIn = $('loginSubmitPassword');
  if (loginSignIn) loginSignIn.addEventListener('click', loginSubmitPassword);
  const loginPassEl = $('loginPassword');
  if (loginPassEl) loginPassEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); loginSubmitPassword(); }
  });
  const loginOut = $('loginLogout');
  if (loginOut) loginOut.addEventListener('click', loginLogout);

  updateRuntime({ running: false });

  connectWS();
  loadConfig();
  loadHourlyFromAPI();
  loadHeadlineStats();
  loadInitialFeed().then(loadErrors);
  loadLoginStatus();
  pollStatus();
  setInterval(pollStatus, STATUS_POLL_MS);
}

document.addEventListener('DOMContentLoaded', boot);
