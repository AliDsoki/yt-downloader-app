# -*- coding: utf-8 -*-
"""
service.py -> يترجمها python-for-android لخدمة أندرويد حقيقية (Foreground Service).
هذا الملف بيشتغل في بروسس منفصل عن الواجهة، وبيفضل شغال حتى لو:
  - المستخدم قفل شاشة الموبايل
  - المستخدم رجع لسطح المكتب (Home)
وده بفضل:
  1. تشغيله كـ Foreground Service (لازم إشعار Notification دايم ظاهر - متطلب أندرويد)
  2. أخذ PARTIAL_WAKE_LOCK يمنع المعالج من الدخول في وضع Doze/Sleep
"""
import os
import json
import glob
import shutil
import traceback
from jnius import autoclass
from yt_dlp import YoutubeDL

PythonService = autoclass("org.kivy.android.PythonService")
PowerManager = autoclass("android.os.PowerManager")
Context = autoclass("android.content.Context")
service = PythonService.mService

STATUS_FILE = os.path.join(
    os.environ.get("ANDROID_PRIVATE", os.path.expanduser("~")), "download_status.json"
)
DOWNLOAD_DIR = os.environ.get(
    "ANDROID_ARGUMENT",
    "/sdcard/Download",
)
# نفضل نحمل في مجلد التنزيلات العام حتى يظهر للمستخدم بسهولة
# (ده بيتستخدم بس لو المستخدم مختارش مجلد تخزين يدوي عن طريق SAF)
SAVE_DIR = "/sdcard/Download"

# مجلد خاص جوه التطبيق نفسه (مساحة تخزين داخلية) - الكتابة فيه مبتحتاجش
# أي إذن خالص، وبنستخدمه كمحطة وسيطة قبل ما ننقل الملف لمكانه النهائي.
# لازم نحمل هنا أولًا لأن yt-dlp محتاج مسار ملف عادي (File path) مش
# content:// URI، فمنقدرش نخليه يكتب مباشرة جوه مجلد SAF.
TEMP_DOWNLOAD_DIR = os.path.join(
    os.environ.get("ANDROID_PRIVATE", os.path.expanduser("~")), "tmp_downloads"
)


def write_status(status="", percent=0.0):
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump({"status": status, "percent": percent}, f)
    except Exception:
        pass


def progress_hook(d):
    if d.get("status") == "downloading":
        percent_str = d.get("_percent_str", "0.0%").strip().strip("%")
        try:
            write_status("downloading", float(percent_str))
        except ValueError:
            pass
    elif d.get("status") == "finished":
        write_status("processing...", 100.0)


def acquire_wakelock():
    power_manager = service.getSystemService(Context.POWER_SERVICE)
    wake_lock = power_manager.newWakeLock(
        PowerManager.PARTIAL_WAKE_LOCK, "ytdl:download_wakelock"
    )
    wake_lock.acquire()
    return wake_lock


# ------------------------------------------------------------
# نقل الملف اللي اتحمل من المجلد الداخلي المؤقت لمجلد التخزين اللي
# المستخدم اختاره يدويًا عن طريق SAF (Storage Access Framework).
# دي الطريقة الوحيدة للكتابة في مجلد اختاره المستخدم بنفسه من غير
# ما نحتاج صلاحية "الوصول لكل الملفات" (MANAGE_EXTERNAL_STORAGE).
# ------------------------------------------------------------
def copy_to_saf(local_path, storage_uri_str, filename):
    Uri = autoclass("android.net.Uri")
    DocumentsContract = autoclass("android.provider.DocumentsContract")

    resolver = service.getContentResolver()
    tree_uri = Uri.parse(storage_uri_str)
    tree_doc_id = DocumentsContract.getTreeDocumentId(tree_uri)
    parent_uri = DocumentsContract.buildDocumentUriUsingTree(tree_uri, tree_doc_id)

    mime_type = "audio/mpeg" if filename.lower().endswith(".mp3") else "application/octet-stream"
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


def run():
    wake_lock = None
    try:
        wake_lock = acquire_wakelock()
        # الطريقة الرسمية لتمرير البيانات لخدمة p4a: main.py بيبعتها
        # كنص JSON واحد عن طريق service.start(activity, argument)،
        # وبتوصلنا هنا من خلال متغير البيئة PYTHON_SERVICE_ARGUMENT.
        # (الاعتماد على service.getIntent() أو AndroidService هنا كان غلط:
        # الخدمة دلوقتي شغالة كـ foreground عن طريق buildozer.spec مباشرة
        # فمفيش حاجة تانية لازم تشغّلها بنفسها.)
        raw_argument = os.environ.get("PYTHON_SERVICE_ARGUMENT", "{}")
        try:
            data = json.loads(raw_argument)
        except (ValueError, TypeError):
            data = {}
        url = data.get("url", "")
        format_id = data.get("format_id", "")
        title = data.get("title", "video")
        storage_uri = data.get("storage_uri", "")

        write_status("starting", 0.0)

        # دايمًا بنحمل في المجلد الخاص الداخلي الأول (مش محتاج إذن)
        os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)
        download_opts = {
            "format": format_id if format_id else "best",
            "progress_hooks": [progress_hook],
            "outtmpl": os.path.join(TEMP_DOWNLOAD_DIR, "%(title)s.mp3"),
        }
        with YoutubeDL(download_opts) as ydl:
            ydl.download([url])

        # نلاقي الملف اللي اتحمل فعليًا (من غير افتراض اسمه بالظبط، لأن
        # yt-dlp بيعمل sanitize لاسم الفيديو ومنقدرش نتأكد منه 100%)
        downloaded_files = glob.glob(os.path.join(TEMP_DOWNLOAD_DIR, "*"))
        if not downloaded_files:
            raise Exception("Download finished but file not found")
        local_path = max(downloaded_files, key=os.path.getmtime)

        if storage_uri:
            # فيه مجلد تخزين مختار يدويًا (SAF) - ده الوضع المفضل واللي
            # بيتجاوز مشاكل صلاحيات أندرويد 11+ خالص
            write_status("saving to chosen folder...", 100.0)
            copy_to_saf(local_path, storage_uri, os.path.basename(local_path))
            try:
                os.remove(local_path)
            except Exception:
                pass
        else:
            # مفيش مجلد مختار - نرجع للسلوك القديم (محتاج صلاحية
            # "الوصول لكل الملفات" عشان الكتابة تنجح في أندرويد 11+)
            os.makedirs(SAVE_DIR, exist_ok=True)
            shutil.move(local_path, os.path.join(SAVE_DIR, os.path.basename(local_path)))

        write_status("download finished", 100.0)
    except Exception as e:
        write_status(f"Error: {e}", 0.0)
        traceback.print_exc()
    finally:
        if wake_lock is not None:
            try:
                wake_lock.release()
            except Exception:
                pass


run()
