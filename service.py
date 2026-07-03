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
    from android import AndroidService  # p4a helper for foreground notification

    android_service = AndroidService("YT Downloader", "Downloading in background...")
    android_service.start("Download started")

    wake_lock = None
    try:
        wake_lock = acquire_wakelock()

        url = os.environ.get("PY_SERVICE_ARGUMENT", "")
        # الطريقة الأساسية لتمرير المعاملات لخدمة p4a هي عبر Intent extras.
        # نقرأها هنا من خلال الـ Intent المرفق بالخدمة (service.getIntent()).
        intent = service.getIntent()
        url = intent.getStringExtra("url") or url
        format_id = intent.getStringExtra("format_id") or ""
        title = intent.getStringExtra("title") or "video"

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
        android_service.stop("Download finished")

    except Exception as e:
        write_status(f"Error: {e}", 0.0)
        traceback.print_exc()
        try:
            android_service.stop("Download failed")
        except Exception:
            pass
    finally:
        if wake_lock is not None:
            try:
                wake_lock.release()
            except Exception:
                pass


run()
