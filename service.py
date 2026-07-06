# -*- coding: utf-8 -*-
"""
service.py -> خدمة تحميل خلفية (Foreground Service).
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


def resolve_format(job):
    """
    لو الفورمات محدد مسبقًا (فيديو مفرد اتحلل كامل في main.py)، نستخدمه
    زي ما هو. لو الوظيفة دي جاية من قائمة تشغيل (عندها quality_key بس
    من غير format_selector)، نحلل الفيديو ده دلوقتي ونطبق نفس آلية
    "أخف حجم في نطاق الجودة" بتاعة back_end.py على الفيديو ده تحديدًا.
    """
    if job.get("format_selector"):
        return job["format_selector"]

    quality_key = job.get("quality_key", "best_audio")
    if quality_key in ("worst_audio", "best_audio"):
        return "worstaudio" if quality_key == "worst_audio" else "bestaudio"

    try:
        probe_opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "cachedir": False}
        with YoutubeDL(probe_opts) as ydl:
            info = ydl.extract_info(job["url"], download=False)
        sorted_audio, video_qualities = C.analyze_formats(info)
        settings = C.read_settings()
        use_low_audio = bool(settings.get("pair_low_audio", True))
        options = C.pick_best_options(sorted_audio, video_qualities, use_low_audio=use_low_audio)
        chosen = options.get(quality_key)
        if chosen:
            return chosen[0]
    except Exception:
        pass

    # فولباك عام لو التحليل فشل أو الجودة دي مش متاحة بالظبط لهذا الفيديو
    return f"bestvideo[height<={quality_key}]+bestaudio/best[height<={quality_key}]"


def download_worker(job):
    job_id = job["id"]
    temp_dir = os.path.join(C.TEMP_ROOT, job_id)
    os.makedirs(temp_dir, exist_ok=True)
    last_percent = [0.0]

    def hook(d):
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

        format_selector = resolve_format(job)
        ffmpeg_path = C.find_ffmpeg()
        ydl_opts = {
            "format": format_selector,
            "outtmpl": os.path.join(temp_dir, "%(title).150s.%(ext)s"),
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

        result_files = [
            f for f in glob.glob(os.path.join(temp_dir, "*"))
            if not f.endswith(".part") and not f.endswith(".ytdl")
        ]
        if not result_files:
            raise Exception("Download finished but output file not found")
        local_path = max(result_files, key=os.path.getmtime)

        # لو التحميل ده صوت فقط (أقل/أعلى جودة صوت)، بنغيّر امتداد الملف
        # لـ .mp3 مباشرة من غير أي إعادة ترميز (re-encode) - يعني الملف
        # لسه بنفس الترميز الأصلي (opus/m4a/webm) بس الامتداد .mp3 فقط،
        # زي ما طلب المستخدم بالظبط.
        quality_key = job.get("quality_key", "")
        if quality_key in ("worst_audio", "best_audio"):
            base_path, _old_ext = os.path.splitext(local_path)
            mp3_path = base_path + ".mp3"
            if mp3_path != local_path:
                os.replace(local_path, mp3_path)
                local_path = mp3_path

        update_status(job_id, status="saving", percent=100.0)
        storage_uri = job.get("storage_uri", "")
        playlist_name = job.get("playlist_name") or None

        if storage_uri:
            saved_uri = C.copy_to_saf(
                service, local_path, storage_uri, os.path.basename(local_path), subfolder_name=playlist_name
            )
            update_status(job_id, status="finished", percent=100.0, saved_uri=saved_uri, saved_path="")
        else:
            final_dir = C.SAVE_DIR
            if playlist_name:
                final_dir = os.path.join(C.SAVE_DIR, playlist_name)
            os.makedirs(final_dir, exist_ok=True)
            final_path = os.path.join(final_dir, os.path.basename(local_path))
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
