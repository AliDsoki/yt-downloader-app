# -*- coding: utf-8 -*-
"""
YT Downloader - تطبيق أندرويد حقيقي (Kivy)
الواجهة الرئيسية: بتلصق الرابط، تحلله، وتبدأ خدمة تحميل تشتغل
في الخلفية حتى لو قفلت شاشة الموبايل (Foreground Service + WakeLock).
"""

import os
import threading
import json

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.image import AsyncImage
from kivy.uix.progressbar import ProgressBar
from kivy.core.clipboard import Clipboard
from kivy.clock import Clock
from kivy.utils import platform

from yt_dlp import YoutubeDL

FORMAT_IDS = ("249-drc", "250-drc", "249", "250", "140-drc", "251-drc", "140", "251")

# ملف مؤقت بيستخدمه السيرفس عشان يبعت تحديثات (تقدم التحميل) للواجهة
STATUS_FILE = os.path.join(
    os.environ.get("ANDROID_PRIVATE", os.path.expanduser("~")), "download_status.json"
) if platform == "android" else "download_status.json"


class Root(BoxLayout):
    pass


class YTDownloaderApp(App):
    def build(self):
        self.title = "YT Downloader"
        self.picked_url = ""
        self.chosen_format_id = ""
        self.video_title = ""

        root = BoxLayout(orientation="vertical", padding=20, spacing=15)

        self.btn_paste = Button(
            text="Pick up link",
            font_size="26sp",
            size_hint=(1, 0.15),
            background_color=(0.18, 0.18, 0.18, 1),
            color=(0.9, 0.9, 0.9, 1),
        )
        self.btn_paste.bind(on_release=self.on_paste_pressed)
        root.add_widget(self.btn_paste)

        self.btn_download = Button(
            text="Download",
            font_size="26sp",
            size_hint=(1, 0.15),
            background_color=(0.18, 0.18, 0.18, 1),
            color=(0.9, 0.9, 0.9, 1),
        )
        self.btn_download.bind(on_release=self.on_download_pressed)
        root.add_widget(self.btn_download)

        self.thumb = AsyncImage(size_hint=(1, 0.3))
        root.add_widget(self.thumb)

        # لابل اسم الفيديو - بيدعم العربي والإنجليزي والنص الطويل عن طريق text_size
        self.title_label = Label(
            text="",
            font_size="18sp",
            size_hint=(1, 0.15),
            halign="center",
            valign="middle",
        )
        self.title_label.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None))
        )
        root.add_widget(self.title_label)

        self.progress = ProgressBar(max=100, size_hint=(1, 0.1))
        root.add_widget(self.progress)

        self.percent_label = Label(text="00.00%", font_size="24sp", size_hint=(1, 0.1))
        root.add_widget(self.percent_label)

        self.status_label = Label(text="", font_size="14sp", size_hint=(1, 0.1))
        root.add_widget(self.status_label)

        # نراقب ملف الحالة كل نص ثانية عشان نحدث البروجرس بار من غير ما
        # نحتاج اتصال مباشر بالسيرفس (اللي شغال في بروسس تاني)
        Clock.schedule_interval(self.poll_status_file, 0.5)

        return root

    # ------------------------------------------------------------
    # تحليل الرابط
    # ------------------------------------------------------------
    def on_paste_pressed(self, *_):
        threading.Thread(target=self.analyze, daemon=True).start()

    def analyze(self):
        # تعديل الواجهة (widget.text) لازم يحصل على الـ Main Thread بس.
        # تعديله مباشرة من الـ background thread ده كان بيسبب crash على أندرويد.
        Clock.schedule_once(lambda dt: self.set_widget_text(self.btn_paste, "Analysing"))
        try:
            url = Clipboard.paste()
            self.picked_url = url
            small_size = 2000
            chosen_id = ""
            # cachedir=False: بيمنع yt-dlp من محاولة الكتابة على ملفات cache
            # ممكن ماتكونش متاحة للكتابة جوه بيئة أندرويد وتسبب مشاكل
            ydl_opts = {
                "cachedir": False,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                for f in info.get("formats", []):
                    if f.get("format_id") in FORMAT_IDS:
                        size = f.get("filesize") or f.get("filesize_approx")
                        if size:
                            mb = round(size / (1024 * 1024), 2)
                            if mb < small_size:
                                small_size = mb
                                chosen_id = f["format_id"]
            self.chosen_format_id = chosen_id
            self.video_title = info.get("title", "")
            Clock.schedule_once(
                lambda dt: self.on_analyze_done(small_size, info.get("thumbnail", ""))
            )
        except Exception as e:
            # لازم نحول الخطأ لنص عادي هنا فورًا، لأن بايثون بيمسح متغير 'e'
            # تلقائيًا أول ما نخرج من كتلة except، وlambda هنا بتتنفذ لاحقًا
            # (بعد ما نخرج من except بكتير)، فكانت بتحصل NameError وتقفل التطبيق
            error_msg = str(e)
            Clock.schedule_once(lambda dt: self.set_status(f"Error: {error_msg}"))
            Clock.schedule_once(lambda dt: self.set_widget_text(self.btn_paste, "Pick up link"))

    def on_analyze_done(self, size_mb, thumb_url):
        self.btn_download.text = f"Size : {size_mb} MB"
        self.title_label.text = self.video_title
        if thumb_url:
            self.thumb.source = thumb_url
        self.set_widget_text(self.btn_paste, "Pick up link")

    # ------------------------------------------------------------
    # التحميل (عن طريق Foreground Service حتى يستمر مع قفل الشاشة)
    # ------------------------------------------------------------
    def on_download_pressed(self, *_):
        if not self.chosen_format_id or not self.picked_url:
            self.set_status("Please analyze link first")
            return
        self.set_status("Starting background download service...")
        self.start_download_service()

    def start_download_service(self):
        if platform != "android":
            self.set_status("Service only runs on Android device")
            return
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        activity = PythonActivity.mActivity
        ServiceClass = autoclass(
            "{}.ServiceYtservice".format(activity.getPackageName())
        )
        intent = Intent(activity, ServiceClass)
        intent.putExtra("url", self.picked_url)
        intent.putExtra("format_id", self.chosen_format_id)
        intent.putExtra("title", self.video_title)
        # في أندرويد 8+ لازم نستخدم startForegroundService
        try:
            activity.startForegroundService(intent)
        except Exception:
            activity.startService(intent)

    # ------------------------------------------------------------
    # قراءة تقدم التحميل من ملف بيكتبه السيرفس (بروسس منفصل)
    # ------------------------------------------------------------
    def poll_status_file(self, dt):
        try:
            if not os.path.exists(STATUS_FILE):
                return
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            percent = float(data.get("percent", 0))
            status = data.get("status", "")
            self.progress.value = percent
            self.percent_label.text = f"{percent:.2f}%"
            self.status_label.text = status
        except Exception:
            pass

    # ------------------------------------------------------------
    def set_status(self, text):
        self.status_label.text = text

    def set_widget_text(self, widget, text):
        widget.text = text


if __name__ == "__main__":
    YTDownloaderApp().run()
