# -*- coding: utf-8 -*-
"""
service.py -> خدمة تحميل خلفية (Foreground Service).
بتدعم دلوقتي:
  - تحميل عدة فيديوهات في نفس الوقت (حد أقصى قابل للضبط من الإعدادات)
  - دمج الصوت مع الفيديو تلقائيًا عن طريق ffmpeg لما يكونوا ملفين منفصلين
  - إيقاف مؤقت/استكمال آمن (بيسيب ملفات .part متعرفوش تتحذف إلا لما
    التحميل يخلص بنجاح بالكامل، فمفيش احتمال ملف نص متحمل يتحط مكان
    النهائي وهو تالف)
  - إلغاء نظيف لأي تحميل (شغال أو لسه في الانتظار)

الخدمة بتفضل شغالة وبتراقب ملف "قائمة الانتظار" (QUEUE_FILE) باستمرار،
فأي فيديو جديد تضيفه الواجهة (main.py) بيتلقط تلقائيًا من غير ما نحتاج
نعيد تشغيل السيرفس من الأول.
"""
import os
import glob
import shutil
import threading
import time
import traceback
from jnius import autoclass
from yt_dlp import YoutubeDL

import dl_common as C

PythonService = autoclass("org.kivy.android.PythonService")
PowerManager = autoclass("android.os.PowerManager")
Context = autoclass("android.content.Context")
service = PythonService.mService

os.makedirs(C.TEMP_ROOT, exist_ok=True)

status_lock = threading.Lock()
active_threads = {}
abort_flags = {}  # job_id -> "pause" | "cancel"


def acquire_wakelock():
    power_manager = service.getSystemService(Context.POWER_SERVICE)
    wake_lock = power_manager.newWakeLock(
        PowerManager.PARTIAL_WAKE_LOCK, "ytdl:download_wakelock"
    )
    wake_lock.acquire()
    return wake_lock


def update_status(job_id, **kwargs):
    with status_lock:
        data = C.read_json(C.STATUS_FILE, {})
        entry = data.get(job_id, {})
        entry.update(kwargs)
        data[job_id] = entry
        C.write_json(C.STATUS_FILE, data)


def update_queue_status(job_id, status):
    queue = C.read_json(C.QUEUE_FILE, [])
    changed = False
    for job in queue:
        if job.get("id") == job_id:
            job["status"] = status
            changed = True
    if changed:
        C.write_json(C.QUEUE_FILE, queue)


def remove_from_queue(job_id):
    queue = C.read_json(C.QUEUE_FILE, [])
    queue = [j for j in queue if j.get("id") != job_id]
    C.write_json(C.QUEUE_FILE, queue)


class AbortDownload(Exception):
    pass


def download_worker(job):
    job_id = job["id"]
    temp_dir = os.path.join(C.TEMP_ROOT, job_id)
    os.makedirs(temp_dir, exist_ok=True)
    last_percent = [0.0]

    def hook(d):
        # بنتشيك على أمر إلغاء/إيقاف مؤقت في كل نبضة تقدم - رفع Exception
        # هنا هو الطريقة اللي yt-dlp بيسمح بيها بمقاطعة تحميل شغال
        reason = abort_flags.get(job_id)
        if reason:
            raise AbortDownload(reason)

        if d.get("status") == "downloading":
            percent_str = d.get("_percent_str", "0.0%")
            cleaned = "".join(ch for ch in percent_str if ch.isdigit() or ch == ".")
            try:
                percent = float(cleaned) if cleaned else last_percent[0]
            except ValueError:
                percent = last_percent[0]
            last_percent[0] = percent
            update_status(job_id, status="downloading", percent=percent)
        elif d.get("status") == "finished":
            update_status(job_id, status="merging", percent=99.0)

    try:
        update_status(
            job_id,
            status="downloading",
            percent=0.0,
            title=job.get("title", ""),
            thumbnail=job.get("thumbnail", ""),
        )
        ffmpeg_path = C.find_ffmpeg()
        ydl_opts = {
            "format": job["format_selector"],
            # اسم الملف ثابت الطول عشان نقدر نلاقيه بسهولة، وبرضه بيحافظ
            # على نفس الاسم بين محاولة التحميل الأولى ومحاولة الاستكمال
            "outtmpl": os.path.join(temp_dir, "%(title).150B.%(ext)s"),
            "merge_output_format": "mp4",
            "progress_hooks": [hook],
            "continuedl": True,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "cachedir": False,
        }
        if ffmpeg_path:
            ydl_opts["ffmpeg_location"] = ffmpeg_path

        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([job["url"]])

        # لو الكود وصل هنا يبقى التحميل (والدمج لو حصل) خلص بنجاح 100%
        # من غير أي مقاطعة، فالملف مضمون سليم ومش هنلمسه إلا دلوقتي.
        # ده بالظبط اللي كان ناقص قبل كده وبيسبب تلف الملف بعد الاستكمال.
        result_files = [
            f for f in glob.glob(os.path.join(temp_dir, "*"))
            if not f.endswith(".part") and not f.endswith(".ytdl")
        ]
        if not result_files:
            raise Exception("Download finished but output file not found")
        local_path = max(result_files, key=os.path.getmtime)

        update_status(job_id, status="saving", percent=100.0)
        storage_uri = job.get("storage_uri", "")
        if storage_uri:
            saved_uri = C.copy_to_saf(service, local_path, storage_uri, os.path.basename(local_path))
            update_status(job_id, status="finished", percent=100.0, saved_uri=saved_uri, saved_path="")
        else:
            os.makedirs(C.SAVE_DIR, exist_ok=True)
            final_path = os.path.join(C.SAVE_DIR, os.path.basename(local_path))
            shutil.move(local_path, final_path)
            update_status(job_id, status="finished", percent=100.0, saved_path=final_path, saved_uri="")

        shutil.rmtree(temp_dir, ignore_errors=True)
        update_queue_status(job_id, "finished")
        C.append_download_log(f"{job.get('title', '')} - finished")

    except AbortDownload as ab:
        reason = str(ab)
        if reason == "cancel":
            update_status(job_id, status="cancelled", percent=0.0)
            update_queue_status(job_id, "cancelled")
            shutil.rmtree(temp_dir, ignore_errors=True)
            C.append_download_log(f"{job.get('title', '')} - cancelled")
        else:
            # إيقاف مؤقت: مبنمسحش temp_dir خالص عشان ملفات .part تفضل
            # موجودة، وبكرة لما نكمّل هيبدأ منها بدل ما يحمل من الصفر
            update_status(job_id, status="paused", percent=last_percent[0])
            update_queue_status(job_id, "paused")
    except Exception as e:
        error_msg = str(e)
        update_status(job_id, status="error", error=error_msg)
        update_queue_status(job_id, "error")
        C.append_error_log(f"{job.get('title', '')} - {error_msg}")
        traceback.print_exc()
    finally:
        abort_flags.pop(job_id, None)
        active_threads.pop(job_id, None)


def handle_controls():
    controls = C.read_json(C.CONTROL_FILE, {})
    if not controls:
        return
    remaining = {}
    for job_id, action in controls.items():
        if job_id in active_threads:
            abort_flags[job_id] = action
        elif action == "cancel":
            # الملف لسه في قائمة الانتظار ومبدأش تحميله، نشيله على طول
            remove_from_queue(job_id)
            update_status(job_id, status="cancelled", percent=0.0)
        else:
            remaining[job_id] = action
    C.write_json(C.CONTROL_FILE, remaining)


def run():
    wake_lock = None
    idle_cycles = 0
    try:
        wake_lock = acquire_wakelock()
        while True:
            handle_controls()

            settings = C.read_settings()
            try:
                max_concurrent = int(settings.get("max_concurrent", 2) or 2)
            except (TypeError, ValueError):
                max_concurrent = 2

            queue = C.read_json(C.QUEUE_FILE, [])
            pending = [
                j for j in queue
                if j.get("status") == "queued" and j.get("id") not in active_threads
            ]

            slots = max_concurrent - len(active_threads)
            for job in pending[: max(0, slots)]:
                job_id = job["id"]
                update_queue_status(job_id, "downloading")
                t = threading.Thread(target=download_worker, args=(job,), daemon=True)
                active_threads[job_id] = t
                t.start()

            if not active_threads and not pending:
                idle_cycles += 1
            else:
                idle_cycles = 0

            # حوالي 5 ثواني من غير أي شغل - نوقف السيرفس نفسه لتوفير
            # البطارية. main.py هيعيد تشغيله تاني أول ما يضاف تحميل جديد
            if idle_cycles > 10:
                break

            time.sleep(0.5)
    except Exception:
        C.append_error_log("Service crashed: " + traceback.format_exc())
    finally:
        if wake_lock is not None:
            try:
                wake_lock.release()
            except Exception:
                pass
        try:
            service.stopSelf()
        except Exception:
            pass


run()
