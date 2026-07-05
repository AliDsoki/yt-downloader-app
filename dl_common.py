# -*- coding: utf-8 -*-
"""
dl_common.py
كود مشترك بين main.py (الواجهة) و service.py (خدمة التحميل في الخلفية).
الملفين دول بيشتغلوا في بروسيسين منفصلين على أندرويد، فبيتواصلوا مع
بعض عن طريق ملفات JSON بسيطة بدل الاتصال المباشر:

  - QUEUE_FILE   : قائمة كل ملفات التحميل (المنتظرة/الجارية/الخلصانة)
  - STATUS_FILE  : حالة كل تحميل لحظيًا (النسبة، الحالة، الخ)
  - CONTROL_FILE : أوامر من الواجهة للسيرفس (إيقاف مؤقت/إلغاء)
  - SETTINGS_FILE: إعدادات المستخدم (عدد التحميلات المتزامنة، الخ)

كل القراءة والكتابة بتتم بطريقة "atomic" (كتابة لملف مؤقت ثم استبدال)
عشان لو البروسيسين حاولوا يكتبوا في نفس اللحظة، الملف مايتلخبطش.
"""
import os
import json

PRIVATE_DIR = os.environ.get("ANDROID_PRIVATE", os.path.expanduser("~"))

STATUS_FILE = os.path.join(PRIVATE_DIR, "downloads_status.json")
QUEUE_FILE = os.path.join(PRIVATE_DIR, "downloads_queue.json")
CONTROL_FILE = os.path.join(PRIVATE_DIR, "downloads_control.json")
SETTINGS_FILE = os.path.join(PRIVATE_DIR, "app_settings.json")
STORAGE_PREF_FILE = os.path.join(PRIVATE_DIR, "storage_uri.txt")
DOWNLOAD_LOG_FILE = os.path.join(PRIVATE_DIR, "download_log.txt")
ERROR_LOG_FILE = os.path.join(PRIVATE_DIR, "error_log.txt")
TEMP_ROOT = os.path.join(PRIVATE_DIR, "tmp_downloads")

# فولدر افتراضي (fallback) لو المستخدم مختارش مجلد تخزين يدوي عن طريق SAF
SAVE_DIR = "/sdcard/Download"

DEFAULT_SETTINGS = {"max_concurrent": 2}

# كل عنصر: (المفتاح الداخلي, النص المعروض على الزرار, format selector بتاع yt-dlp)
# صف الصوت (2) ثم صفين فيديو (3+3) - ده بالظبط ترتيب الجودات المطلوب
QUALITY_OPTIONS = [
    ("worst_audio", "Worst Audio", "worstaudio"),
    ("best_audio", "Best Audio", "bestaudio"),
    ("144p", "144p", "bestvideo[height<=144]+bestaudio/best[height<=144]"),
    ("240p", "240p", "bestvideo[height<=240]+bestaudio/best[height<=240]"),
    ("360p", "360p", "bestvideo[height<=360]+bestaudio/best[height<=360]"),
    ("480p", "480p", "bestvideo[height<=480]+bestaudio/best[height<=480]"),
    ("720p", "720p", "bestvideo[height<=720]+bestaudio/best[height<=720]"),
    ("1080p", "1080p", "bestvideo[height<=1080]+bestaudio/best[height<=1080]"),
]


def read_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # ملف متكسر أو بيتكتب فيه دلوقتي من البروسيس التاني - نرجع
        # القيمة الافتراضية ونحاول تاني في الدورة الجاية
        return default


def write_json(path, data):
    try:
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp_path, path)
    except Exception:
        pass


def read_settings():
    settings = dict(DEFAULT_SETTINGS)
    settings.update(read_json(SETTINGS_FILE, {}))
    return settings


def write_settings(settings):
    write_json(SETTINGS_FILE, settings)


def load_storage_uri():
    try:
        if os.path.exists(STORAGE_PREF_FILE):
            with open(STORAGE_PREF_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


def save_storage_uri(uri_str):
    try:
        with open(STORAGE_PREF_FILE, "w", encoding="utf-8") as f:
            f.write(uri_str)
    except Exception:
        pass


def append_log(path, line):
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")
    except Exception:
        pass


def append_download_log(text):
    append_log(DOWNLOAD_LOG_FILE, text)


def append_error_log(text):
    append_log(ERROR_LOG_FILE, text)


def read_log(path, max_chars=20000):
    try:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if len(content) > max_chars:
            content = content[-max_chars:]
        return content
    except Exception:
        return ""


def clear_log(path):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("")
    except Exception:
        pass


# ------------------------------------------------------------
# نسخ ملف لمجلد SAF (المجلد اللي المستخدم اختاره يدويًا) - بتتنادى من
# السيرفس بعد ما التحميل (والدمج لو حصل) يخلص بنجاح بالكامل
# ------------------------------------------------------------
def copy_to_saf(android_context, local_path, storage_uri_str, filename):
    from jnius import autoclass

    Uri = autoclass("android.net.Uri")
    DocumentsContract = autoclass("android.provider.DocumentsContract")

    resolver = android_context.getContentResolver()
    tree_uri = Uri.parse(storage_uri_str)
    tree_doc_id = DocumentsContract.getTreeDocumentId(tree_uri)
    parent_uri = DocumentsContract.buildDocumentUriUsingTree(tree_uri, tree_doc_id)

    lower = filename.lower()
    if lower.endswith((".mp3", ".m4a", ".opus", ".aac", ".wav")):
        mime_type = "audio/*"
    else:
        mime_type = "video/*"

    new_file_uri = DocumentsContract.createDocument(resolver, parent_uri, mime_type, filename)
    if new_file_uri is None:
        raise Exception("Could not create file in the chosen folder")

    out_stream = resolver.openOutputStream(new_file_uri)
    try:
        chunk_size = 1024 * 1024
        with open(local_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                out_stream.write(bytearray(chunk))
        out_stream.flush()
    finally:
        out_stream.close()

    return new_file_uri.toString()


def find_ffmpeg():
    """
    بيدور على ملف ffmpeg التنفيذي جوه بيئة أندرويد عشان yt-dlp يستخدمه
    لدمج الصوت مع الفيديو. python-for-android مفيهوش ffmpeg CLI جاهز
    بشكل افتراضي، فالدالة دي بتجرب أكتر من مكان محتمل. لو معرفتش تلاقيه
    بترجع None (وقتها yt-dlp هيحاول يحمل من غير دمج، وده ممكن يفشل في
    الجودات اللي محتاجة فيديو وصوت منفصلين زي 720p/1080p).
    """
    from shutil import which

    found = which("ffmpeg")
    if found:
        return found

    candidates = []
    app_root = os.environ.get("ANDROID_APP_PATH", "")
    if app_root:
        candidates.append(os.path.join(app_root, "ffmpeg"))
    private_parent = os.path.dirname(PRIVATE_DIR)
    candidates.append(os.path.join(private_parent, "lib", "libffmpeg.so"))
    candidates.append(os.path.join(private_parent, "lib", "ffmpeg"))
    candidates.append(os.path.join(private_parent, "cache", "ffmpeg"))

    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None
