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
import time
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
SAVE_DIR = "/sdcard/Download"


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

        write_status("starting", 0.0)

        os.makedirs(SAVE_DIR, exist_ok=True)

        download_opts = {
            "format": format_id if format_id else "best",
            "progress_hooks": [progress_hook],
            "outtmpl": os.path.join(SAVE_DIR, "%(title)s.mp3"),
        }

        with YoutubeDL(download_opts) as ydl:
            ydl.download([url])

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
