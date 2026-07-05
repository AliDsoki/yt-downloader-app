# -*- coding: utf-8 -*-
"""
dl_common.py
كود مشترك بين main.py (الواجهة) و service.py (خدمة التحميل في الخلفية).
الملفين دول بيشتغلوا في بروسيسين منفصلين على أندرويد، فبيتواصلوا مع
بعض عن طريق ملفات JSON بسيطة بدل الاتصال المباشر.
"""
import os
import re
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

DEFAULT_SETTINGS = {"max_concurrent": 2, "pair_low_audio": True}

# قائمة الجودات الـ8 المعروضة في الواجهة: (المفتاح, النص العربي المعروض)
# ترتيبها هو نفسه ترتيب الصفوف المطلوب: صف صوت (2) ثم صفين فيديو (3+3)
QUALITY_LABELS = [
    ("worst_audio", "أقل جودة صوت"),
    ("best_audio", "أعلى جودة صوت"),
    ("144", "144p"),
    ("240", "240p"),
    ("360", "360p"),
    ("480", "480p"),
    ("720", "720p"),
    ("1080", "1080p"),
]
VIDEO_QUALITY_KEYS = ["144", "240", "360", "480", "720", "1080"]


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
            json.dump(data, f, ensure_ascii=False)
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


def sanitize_name(name):
    """تنظيف اسم من الرموز الممنوعة في أسماء الملفات/المجلدات"""
    name = re.sub(r'[\\/:*?"<>|]', "", name or "")
    name = " ".join(name.split())
    return name.strip() or "video"


# ==================================================================
# آلية اختيار الجودات - نفس آلية back_end.py بالضبط:
# لكل جودة (144/240/360/480/720/1080) بنجمع كل الفورمات اللي عندها
# حجم حقيقي (filesize)، بنرتبهم تصاعديًا، وبناخد أخف واحد في كل جودة.
# للصوت: أخف ملف = "أقل جودة صوت"، وأتقل ملف = "أعلى جودة صوت".
# ==================================================================
def analyze_formats(info):
    keys = [144, 240, 360, 480, 720, 1080]
    keys_str = ["144", "240", "360", "480", "720", "1080"]
    audio_qualities = {}
    video_qualities = {}

    for f in info.get("formats", []):
        filesize = f.get("filesize")
        if filesize is None:
            continue
        size_mb = round(filesize / (1024 * 1024), 2)

        if f.get("vcodec") == "none" and f.get("acodec") != "none":
            audio_qualities[f.get("format_id")] = size_mb

        format_note = f.get("format_note") or ""
        note_num = format_note[:-1] if format_note else ""
        height = f.get("height")
        if f.get("acodec") == "none" and (height in keys or note_num in keys_str):
            key = str(height) if height in keys else note_num
            video_qualities.setdefault(key, []).append([f.get("format_id"), size_mb])

    sorted_audio = dict(sorted(audio_qualities.items(), key=lambda item: item[1]))
    for quality in video_qualities:
        video_qualities[quality] = sorted(video_qualities[quality], key=lambda x: x[1])

    return sorted_audio, video_qualities


def pick_best_options(sorted_audio, video_qualities, use_low_audio=True):
    """
    بيرجع dict: المفتاح ("worst_audio","best_audio","144"...) -> إما
    (format_selector, حجم_تقريبي_ميجا) لو الجودة متاحة، أو None لو مش
    متاحة لهذا الفيديو بالذات.
    لجودات الفيديو، الحجم المعروض = حجم الفيديو + حجم الصوت المقرون بيه.
    use_low_audio=True (الافتراضي) يعني الفيديو بيتقرن بأقل جودة صوت
    لتوفير البيانات، ولو False بيتقرن بأعلى جودة صوت.
    """
    result = {}
    audio_items = list(sorted_audio.items())
    if audio_items:
        worst_audio_id, worst_audio_size = audio_items[0]
        best_audio_id, best_audio_size = audio_items[-1]
        result["worst_audio"] = (worst_audio_id, worst_audio_size)
        result["best_audio"] = (best_audio_id, best_audio_size)
    else:
        result["worst_audio"] = None
        result["best_audio"] = None

    pair_audio = result.get("worst_audio") if use_low_audio else result.get("best_audio")
    for quality in VIDEO_QUALITY_KEYS:
        formats_list = video_qualities.get(quality)
        if formats_list and pair_audio:
            video_id, video_size = formats_list[0]  # أخف حجم في نطاق الجودة دي
            total_size = round(video_size + pair_audio[1], 2)
            selector = f"{video_id}+{pair_audio[0]}"
            result[quality] = (selector, total_size)
        else:
            result[quality] = None
    return result


# ------------------------------------------------------------
# نسخ ملف لمجلد SAF (المجلد اللي المستخدم اختاره يدويًا) - بتتنادى من
# السيرفس بعد ما التحميل (والدمج لو حصل) يخلص بنجاح بالكامل.
# لو subfolder_name موجود (تحميل من قائمة تشغيل)، بننشئ/نستخدم مجلد
# فرعي بنفس اسم القائمة جوه المجلد المختار.
# ------------------------------------------------------------
def get_or_create_saf_folder(android_context, storage_uri_str, folder_name):
    from jnius import autoclass

    Uri = autoclass("android.net.Uri")
    DocumentsContract = autoclass("android.provider.DocumentsContract")
    Document = autoclass("android.provider.DocumentsContract$Document")

    resolver = android_context.getContentResolver()
    tree_uri = Uri.parse(storage_uri_str)
    parent_doc_id = DocumentsContract.getTreeDocumentId(tree_uri)
    parent_uri = DocumentsContract.buildDocumentUriUsingTree(tree_uri, parent_doc_id)

    children_uri = DocumentsContract.buildChildDocumentsUriUsingTree(tree_uri, parent_doc_id)
    projection = [Document.COLUMN_DOCUMENT_ID, Document.COLUMN_DISPLAY_NAME, Document.COLUMN_MIME_TYPE]
    cursor = resolver.query(children_uri, projection, None, None, None)
    found_doc_id = None
    try:
        if cursor is not None:
            while cursor.moveToNext():
                name = cursor.getString(1)
                mime = cursor.getString(2)
                if name == folder_name and mime == Document.MIME_TYPE_DIR:
                    found_doc_id = cursor.getString(0)
                    break
    finally:
        if cursor is not None:
            cursor.close()

    if found_doc_id:
        folder_doc_id = found_doc_id
    else:
        new_dir_uri = DocumentsContract.createDocument(
            resolver, parent_uri, Document.MIME_TYPE_DIR, folder_name
        )
        if new_dir_uri is None:
            raise Exception("Could not create playlist folder")
        folder_doc_id = DocumentsContract.getDocumentId(new_dir_uri)

    folder_uri = DocumentsContract.buildDocumentUriUsingTree(tree_uri, folder_doc_id)
    return folder_uri.toString()


def copy_to_saf(android_context, local_path, storage_uri_str, filename, subfolder_name=None):
    from jnius import autoclass

    Uri = autoclass("android.net.Uri")
    DocumentsContract = autoclass("android.provider.DocumentsContract")

    resolver = android_context.getContentResolver()

    if subfolder_name:
        parent_uri_str = get_or_create_saf_folder(android_context, storage_uri_str, subfolder_name)
        parent_uri = Uri.parse(parent_uri_str)
    else:
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
    لدمج الصوت مع الفيديو. لو معرفتش تلاقيه بترجع None (وقتها yt-dlp
    هيحاول من غيره، وده ممكن يفشل في الجودات اللي محتاجة دمج).
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
