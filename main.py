# -*- coding: utf-8 -*-
"""
YT Downloader - تطبيق أندرويد حقيقي (Kivy)
تبويبين: "Download" للشاشة الرئيسية، و"Settings" لمجلد التخزين وعدد
التحميلات المتزامنة وسجل التحميلات/الأخطاء.
"""
import os
import json
import uuid
import threading

from kivy.config import Config
# مبنخليش التطبيق ياخد الشاشة كلها - نسيب شريط الحالة (الساعة/البطارية)
# وأزرار التنقل السفلية ظاهرة زي أي تطبيق عادي
Config.set("graphics", "fullscreen", "0")

from kivy.app import App
from kivy.lang import Builder
from kivy.factory import Factory
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.image import AsyncImage
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.core.clipboard import Clipboard
from kivy.clock import Clock
from kivy.utils import platform
from kivy.properties import ListProperty

from yt_dlp import YoutubeDL

import arabic_reshaper
from bidi.algorithm import get_display

import dl_common as C

# مسار الخط اللي بيدعم العربي - لازم يكون موجود جوه مجلد assets بجانب main.py
FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "NotoNaskhArabic-Regular.ttf")


def to_display_text(text):
    """
    Kivy بيرسم كل حرف عربي لوحده من غير ما يوصل الحروف ببعضها، فالنص
    بيبان متقطّع. الدالة دي بتعمل reshape + bidi قبل الحط في أي Label.
    """
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


# ------------------------------------------------------------
# ستايل الواجهة: أزرار وبطاقات بشكل ثلاثي الأبعاد (skeuomorphic) عن
# طريق طبقات RoundedRectangle متزاحزحة شوية فوق بعض بدل الأشكال الفلات
# ------------------------------------------------------------
KV = """
<Card>:
    padding: dp(12)
    spacing: dp(10)
    canvas.before:
        Color:
            rgba: 0, 0, 0, 0.45
        RoundedRectangle:
            pos: self.x, self.y - dp(3)
            size: self.size
            radius: [dp(16)]
        Color:
            rgba: 0.15, 0.15, 0.19, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(16)]
        Color:
            rgba: 1, 1, 1, 0.035
        RoundedRectangle:
            pos: self.x, self.y + self.height * 0.5
            size: self.width, self.height * 0.5
            radius: [dp(16), dp(16), 0, 0]

<Button3D>:
    background_normal: ""
    background_down: ""
    background_color: 0, 0, 0, 0
    bg_color: 0.20, 0.45, 0.85, 1
    color: 1, 1, 1, 1
    bold: True
    canvas.before:
        Color:
            rgba: 0, 0, 0, 0.55
        RoundedRectangle:
            pos: self.x, (self.y - dp(4)) if self.state == "normal" else (self.y - dp(1))
            size: self.size
            radius: [dp(12)]
        Color:
            rgba: self.bg_color
        RoundedRectangle:
            pos: self.x, (self.y + dp(3)) if self.state == "normal" else self.y
            size: self.size
            radius: [dp(12)]
        Color:
            rgba: 1, 1, 1, 0.16
        RoundedRectangle:
            pos: self.x, ((self.y + dp(3)) if self.state == "normal" else self.y) + self.height * 0.5
            size: self.width, self.height * 0.5
            radius: [dp(12), dp(12), 0, 0]

<QualityToggle>:
    background_normal: ""
    background_down: ""
    background_color: 0, 0, 0, 0
    color: 1, 1, 1, 1
    bold: True
    bg_color: (0.22, 0.62, 0.36, 1) if self.state == "down" else (0.26, 0.26, 0.30, 1)
    canvas.before:
        Color:
            rgba: 0, 0, 0, 0.55
        RoundedRectangle:
            pos: self.x, (self.y - dp(4)) if self.state == "normal" else (self.y - dp(1))
            size: self.size
            radius: [dp(12)]
        Color:
            rgba: self.bg_color
        RoundedRectangle:
            pos: self.x, (self.y + dp(3)) if self.state == "normal" else self.y
            size: self.size
            radius: [dp(12)]
        Color:
            rgba: 1, 1, 1, 0.16
        RoundedRectangle:
            pos: self.x, ((self.y + dp(3)) if self.state == "normal" else self.y) + self.height * 0.5
            size: self.width, self.height * 0.5
            radius: [dp(12), dp(12), 0, 0]

<SmallButton3D@Button3D>:
    font_size: "13sp"

<DownloadCard>:
    orientation: "vertical"
    size_hint_y: None
    height: dp(112)
    padding: dp(10)
    spacing: dp(6)
    canvas.before:
        Color:
            rgba: 0, 0, 0, 0.4
        RoundedRectangle:
            pos: self.x, self.y - dp(2)
            size: self.size
            radius: [dp(14)]
        Color:
            rgba: 0.17, 0.17, 0.21, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]
"""


class Card(BoxLayout):
    pass


class Button3D(Button):
    bg_color = ListProperty([0.20, 0.45, 0.85, 1])


class QualityToggle(ToggleButton):
    bg_color = ListProperty([0.26, 0.26, 0.30, 1])


class DownloadCard(BoxLayout):
    pass


Builder.load_string(KV)
SmallButton3D = Factory.SmallButton3D


class YTDownloaderApp(App):
    def build(self):
        self.title = "YT Downloader"
        self.picked_url = ""
        self.video_title = ""
        self.video_thumb = ""
        self.selected_quality_index = 6  # 720p افتراضيًا
        self.storage_uri = C.load_storage_uri()
        self.quality_buttons = []
        self.download_widgets = {}  # job_id -> dict of widgets

        root = TabbedPanel(do_default_tab=False, tab_width=dp(140))

        download_tab = TabbedPanelItem(text="Download")
        download_tab.content = self.build_download_tab()
        root.add_widget(download_tab)

        settings_tab = TabbedPanelItem(text="Settings")
        settings_tab.content = self.build_settings_tab()
        root.add_widget(settings_tab)

        Clock.schedule_interval(self.poll_downloads, 0.5)
        Clock.schedule_interval(self.refresh_logs, 2.0)

        return root

    # ==============================================================
    # تبويب التحميل الرئيسي
    # ==============================================================
    def build_download_tab(self):
        layout = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12))

        self.btn_analyze = Button3D(
            text="Pick up link & Analyze",
            font_size="20sp",
            size_hint=(1, None),
            height=dp(56),
        )
        self.btn_analyze.bind(on_release=self.on_analyze_pressed)
        layout.add_widget(self.btn_analyze)

        # ---------------- بطاقة نتيجة التحليل + اختيار الجودة ----------------
        self.analyze_card = Card(orientation="vertical", size_hint=(1, None), height=dp(300))

        header_row = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(64), spacing=dp(10))
        self.thumb = AsyncImage(size_hint=(None, None), size=(dp(64), dp(64)))
        header_row.add_widget(self.thumb)
        self.title_label = Label(
            text="",
            font_size="15sp",
            font_name=FONT_PATH,
            halign="left",
            valign="middle",
        )
        self.title_label.bind(size=lambda inst, s: setattr(inst, "text_size", s))
        header_row.add_widget(self.title_label)
        self.analyze_card.add_widget(header_row)

        # صف الصوت (2 زرار)
        row_audio = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(52), spacing=dp(8))
        # صفين فيديو (3 أزرار لكل صف)
        row_video_1 = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(52), spacing=dp(8))
        row_video_2 = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(52), spacing=dp(8))

        rows_map = [row_audio, row_audio, row_video_1, row_video_1, row_video_1, row_video_2, row_video_2, row_video_2]
        self.quality_buttons = []
        for idx, (key, label, _fmt) in enumerate(C.QUALITY_OPTIONS):
            btn = QualityToggle(text=label, group="quality_select", font_size="14sp")
            btn.quality_index = idx
            if idx == self.selected_quality_index:
                btn.state = "down"
            btn.bind(on_release=self.on_quality_selected)
            self.quality_buttons.append(btn)
            rows_map[idx].add_widget(btn)

        self.analyze_card.add_widget(row_audio)
        self.analyze_card.add_widget(row_video_1)
        self.analyze_card.add_widget(row_video_2)

        self.btn_add_queue = Button3D(text="Add to downloads", size_hint=(1, None), height=dp(48))
        self.btn_add_queue.bg_color = [0.22, 0.62, 0.36, 1]
        self.btn_add_queue.bind(on_release=self.on_add_to_queue)
        self.analyze_card.add_widget(self.btn_add_queue)

        layout.add_widget(self.analyze_card)

        # ---------------- بطاقة قائمة التحميلات (Scrollable) ----------------
        downloads_label = Label(text="Downloads", size_hint=(1, None), height=dp(24), bold=True)
        layout.add_widget(downloads_label)

        scroll = ScrollView(size_hint=(1, 1))
        self.downloads_list = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.downloads_list.bind(minimum_height=self.downloads_list.setter("height"))
        scroll.add_widget(self.downloads_list)
        layout.add_widget(scroll)

        self.status_label = Label(text="", font_size="13sp", size_hint=(1, None), height=dp(22))
        layout.add_widget(self.status_label)

        return layout

    # ==============================================================
    # تبويب الإعدادات
    # ==============================================================
    def build_settings_tab(self):
        scroll = ScrollView(size_hint=(1, 1))
        layout = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(14), size_hint_y=None)
        layout.bind(minimum_height=layout.setter("height"))

        # ---------------- مجلد التخزين ----------------
        storage_card = Card(orientation="vertical", size_hint=(1, None), height=dp(110))
        storage_card.add_widget(Label(text="Storage folder", bold=True, size_hint=(1, None), height=dp(24)))
        self.btn_choose_folder = Button3D(
            text="Folder selected" if self.storage_uri else "Choose storage folder",
            size_hint=(1, None),
            height=dp(48),
        )
        self.btn_choose_folder.bind(on_release=self.on_choose_folder_pressed)
        storage_card.add_widget(self.btn_choose_folder)
        layout.add_widget(storage_card)

        # ---------------- عدد التحميلات المتزامنة ----------------
        concurrency_card = Card(orientation="vertical", size_hint=(1, None), height=dp(110))
        concurrency_card.add_widget(Label(text="Simultaneous downloads", bold=True, size_hint=(1, None), height=dp(24)))
        settings = C.read_settings()
        self.spinner_concurrency = Spinner(
            text=str(settings.get("max_concurrent", 2)),
            values=("1", "2", "3", "4"),
            size_hint=(1, None),
            height=dp(48),
        )
        self.spinner_concurrency.bind(text=self.on_concurrency_changed)
        concurrency_card.add_widget(self.spinner_concurrency)
        layout.add_widget(concurrency_card)

        # ---------------- سجل التحميلات ----------------
        dl_log_card = Card(orientation="vertical", size_hint=(1, None), height=dp(240))
        dl_log_card.add_widget(Label(text="Download log", bold=True, size_hint=(1, None), height=dp(24)))
        dl_log_scroll = ScrollView(size_hint=(1, 1))
        self.download_log_label = Label(
            text="", font_size="12sp", size_hint_y=None, halign="left", valign="top", markup=False
        )
        self.download_log_label.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None)),
            texture_size=lambda inst, s: setattr(inst, "height", s[1]),
        )
        dl_log_scroll.add_widget(self.download_log_label)
        dl_log_card.add_widget(dl_log_scroll)
        btn_copy_dl_log = SmallButton3D(text="Copy download log", size_hint=(1, None), height=dp(40))
        btn_copy_dl_log.bind(on_release=lambda *_: self.copy_log_to_clipboard(C.DOWNLOAD_LOG_FILE))
        dl_log_card.add_widget(btn_copy_dl_log)
        layout.add_widget(dl_log_card)

        # ---------------- سجل الأخطاء ----------------
        err_log_card = Card(orientation="vertical", size_hint=(1, None), height=dp(240))
        err_log_card.add_widget(Label(text="Error log", bold=True, size_hint=(1, None), height=dp(24)))
        err_log_scroll = ScrollView(size_hint=(1, 1))
        self.error_log_label = Label(
            text="", font_size="12sp", size_hint_y=None, halign="left", valign="top", markup=False
        )
        self.error_log_label.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None)),
            texture_size=lambda inst, s: setattr(inst, "height", s[1]),
        )
        err_log_scroll.add_widget(self.error_log_label)
        err_log_card.add_widget(err_log_scroll)
        btn_copy_err_log = SmallButton3D(text="Copy error log", size_hint=(1, None), height=dp(40))
        btn_copy_err_log.bind(on_release=lambda *_: self.copy_log_to_clipboard(C.ERROR_LOG_FILE))
        err_log_card.add_widget(btn_copy_err_log)
        layout.add_widget(err_log_card)

        scroll.add_widget(layout)
        return scroll

    def on_concurrency_changed(self, spinner, value):
        settings = C.read_settings()
        try:
            settings["max_concurrent"] = int(value)
        except ValueError:
            settings["max_concurrent"] = 2
        C.write_settings(settings)

    def copy_log_to_clipboard(self, path):
        content = C.read_log(path)
        Clipboard.copy(content)
        self.set_status("Log copied to clipboard")

    def refresh_logs(self, dt):
        if hasattr(self, "download_log_label"):
            self.download_log_label.text = C.read_log(C.DOWNLOAD_LOG_FILE) or "(empty)"
        if hasattr(self, "error_log_label"):
            self.error_log_label.text = C.read_log(C.ERROR_LOG_FILE) or "(empty)"

    # ==============================================================
    # التحليل
    # ==============================================================
    def on_quality_selected(self, btn):
        self.selected_quality_index = btn.quality_index

    def on_analyze_pressed(self, *_):
        threading.Thread(target=self.analyze, daemon=True).start()

    def analyze(self):
        Clock.schedule_once(lambda dt: self.set_widget_text(self.btn_analyze, "Analysing"))
        try:
            url = Clipboard.paste()
            self.picked_url = url
            ydl_opts = {
                "cachedir": False,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            self.video_title = info.get("title", "")
            self.video_thumb = info.get("thumbnail", "")
            Clock.schedule_once(lambda dt: self.on_analyze_done())
        except Exception as e:
            error_msg = str(e)
            Clock.schedule_once(lambda dt: self.set_status(f"Error: {error_msg}"))
            Clock.schedule_once(lambda dt: self.set_widget_text(self.btn_analyze, "Pick up link & Analyze"))

    def on_analyze_done(self):
        self.title_label.text = to_display_text(self.video_title)
        if self.video_thumb:
            self.thumb.source = self.video_thumb
        self.set_widget_text(self.btn_analyze, "Pick up link & Analyze")

    # ==============================================================
    # إضافة للتحميل (queue)
    # ==============================================================
    def on_add_to_queue(self, *_):
        if not self.picked_url or not self.video_title:
            self.set_status("Please analyze a link first")
            return
        if platform == "android" and not self.has_storage_permission():
            self.set_status("Please allow file access, then press again")
            self.request_storage_permission()
            return

        key, label, format_selector = C.QUALITY_OPTIONS[self.selected_quality_index]
        job = {
            "id": uuid.uuid4().hex,
            "url": self.picked_url,
            "title": self.video_title,
            "thumbnail": self.video_thumb,
            "quality_label": label,
            "format_selector": format_selector,
            "storage_uri": self.storage_uri,
            "status": "queued",
        }
        queue = C.read_json(C.QUEUE_FILE, [])
        queue.append(job)
        C.write_json(C.QUEUE_FILE, queue)
        C.append_download_log(f"{job['title']} ({label}) - queued")

        self.start_download_service()
        self.set_status(f"Added to downloads: {label}")

    # ==============================================================
    # صلاحية "الوصول لكل الملفات" - كـ fallback لو مفيش مجلد SAF مختار
    # ==============================================================
    def has_storage_permission(self):
        if self.storage_uri:
            return True
        try:
            from jnius import autoclass
            Environment = autoclass("android.os.Environment")
            return bool(Environment.isExternalStorageManager())
        except Exception:
            return True

    def request_storage_permission(self):
        try:
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            Settings = autoclass("android.provider.Settings")
            Uri = autoclass("android.net.Uri")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
            uri = Uri.parse("package:" + activity.getPackageName())
            intent.setData(uri)
            activity.startActivity(intent)
        except Exception as e:
            self.set_status(f"Error opening settings: {e}")

    # ==============================================================
    # اختيار مجلد التخزين يدويًا (Storage Access Framework)
    # ==============================================================
    def on_choose_folder_pressed(self, *_):
        if platform != "android":
            self.set_status("Folder picker only works on Android device")
            return
        try:
            from jnius import autoclass
            from android import activity

            Intent = autoclass("android.content.Intent")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity_instance = PythonActivity.mActivity

            intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            intent.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            intent.addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)

            activity.bind(on_activity_result=self.on_folder_picked)
            activity_instance.startActivityForResult(intent, 4321)
        except Exception as e:
            self.set_status(f"Error opening folder picker: {e}")

    def on_folder_picked(self, request_code, result_code, intent):
        if request_code != 4321:
            return
        try:
            from jnius import autoclass

            Activity = autoclass("android.app.Activity")
            if result_code != Activity.RESULT_OK or intent is None:
                Clock.schedule_once(lambda dt: self.set_status("Folder selection cancelled"))
                return

            Intent = autoclass("android.content.Intent")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity_instance = PythonActivity.mActivity

            uri = intent.getData()
            take_flags = intent.getFlags() & (
                Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            )
            activity_instance.getContentResolver().takePersistableUriPermission(uri, take_flags)

            uri_str = uri.toString()
            self.storage_uri = uri_str
            C.save_storage_uri(uri_str)
            Clock.schedule_once(lambda dt: self.set_widget_text(self.btn_choose_folder, "Folder selected"))
            Clock.schedule_once(lambda dt: self.set_status("Storage folder saved"))
        except Exception as e:
            error_msg = str(e)
            Clock.schedule_once(lambda dt: self.set_status(f"Error saving folder: {error_msg}"))

    # ==============================================================
    # تشغيل خدمة التحميل (idempotent - آمن نناديها كذا مرة)
    # ==============================================================
    def start_download_service(self):
        if platform != "android":
            self.set_status("Service only runs on Android device")
            return
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        ServiceClass = autoclass("{}.ServiceYtservice".format(activity.getPackageName()))
        ServiceClass.start(activity, "{}")

    # ==============================================================
    # مراقبة التحميلات وتحديث الكروت
    # ==============================================================
    def poll_downloads(self, dt):
        queue = C.read_json(C.QUEUE_FILE, [])
        status_data = C.read_json(C.STATUS_FILE, {})

        current_ids = set()
        for job in queue:
            job_id = job["id"]
            current_ids.add(job_id)
            info = status_data.get(job_id, {})
            status = info.get("status", job.get("status", "queued"))
            percent = info.get("percent", 0.0)

            if job_id not in self.download_widgets:
                self.create_download_card(job, status, percent, info)
            else:
                self.update_download_card(job_id, job, status, percent, info)

        # نشيل الكروت اللي مش موجودة في القائمة (اتنضّفت) من الواجهة
        for job_id in list(self.download_widgets.keys()):
            if job_id not in current_ids:
                widgets = self.download_widgets.pop(job_id)
                self.downloads_list.remove_widget(widgets["card"])

    def create_download_card(self, job, status, percent, info):
        job_id = job["id"]
        card = DownloadCard()

        top_row = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(46), spacing=dp(8))
        thumb = AsyncImage(source=job.get("thumbnail", ""), size_hint=(None, None), size=(dp(40), dp(40)))
        top_row.add_widget(thumb)

        title_lbl = Label(
            text=to_display_text(job.get("title", "")),
            font_name=FONT_PATH,
            font_size="13sp",
            halign="left",
            valign="middle",
        )
        title_lbl.bind(size=lambda inst, s: setattr(inst, "text_size", s))
        top_row.add_widget(title_lbl)
        card.add_widget(top_row)

        progress = ProgressBar(max=100, value=percent, size_hint=(1, None), height=dp(14))
        card.add_widget(progress)

        status_lbl = Label(text=f"{status} - {percent:.1f}%", font_size="11sp", size_hint=(1, None), height=dp(18))
        card.add_widget(status_lbl)

        buttons_row = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(34), spacing=dp(6))
        btn_pause = SmallButton3D(text="Pause", size_hint=(1, 1))
        btn_pause.bind(on_release=lambda *_: self.on_pause_resume(job_id))
        btn_cancel = SmallButton3D(text="Cancel", size_hint=(1, 1))
        btn_cancel.bg_color = [0.65, 0.20, 0.20, 1]
        btn_cancel.bind(on_release=lambda *_: self.on_cancel(job_id))
        btn_open = SmallButton3D(text="Open", size_hint=(1, 1), disabled=True)
        btn_open.bind(on_release=lambda *_: self.on_open(job_id))
        buttons_row.add_widget(btn_pause)
        buttons_row.add_widget(btn_cancel)
        buttons_row.add_widget(btn_open)
        card.add_widget(buttons_row)

        self.downloads_list.add_widget(card)
        self.download_widgets[job_id] = {
            "card": card,
            "progress": progress,
            "status_lbl": status_lbl,
            "btn_pause": btn_pause,
            "btn_cancel": btn_cancel,
            "btn_open": btn_open,
        }
        self.apply_card_state(job_id, status, info)

    def update_download_card(self, job_id, job, status, percent, info):
        widgets = self.download_widgets[job_id]
        widgets["progress"].value = percent
        widgets["status_lbl"].text = f"{status} - {percent:.1f}%"
        if status == "error" and info.get("error"):
            widgets["status_lbl"].text = f"error: {info.get('error')[:60]}"
        self.apply_card_state(job_id, status, info)

    def apply_card_state(self, job_id, status, info):
        widgets = self.download_widgets[job_id]
        btn_pause = widgets["btn_pause"]
        btn_cancel = widgets["btn_cancel"]
        btn_open = widgets["btn_open"]

        if status == "downloading":
            btn_pause.text = "Pause"
            btn_pause.disabled = False
        elif status == "paused":
            btn_pause.text = "Resume"
            btn_pause.disabled = False
        else:
            btn_pause.disabled = True

        btn_cancel.disabled = status in ("finished", "cancelled")
        btn_open.disabled = status != "finished"

    # ==============================================================
    # التحكم في التحميلات (إيقاف مؤقت / استكمال / إلغاء / فتح)
    # ==============================================================
    def send_control(self, job_id, action):
        controls = C.read_json(C.CONTROL_FILE, {})
        controls[job_id] = action
        C.write_json(C.CONTROL_FILE, controls)

    def on_pause_resume(self, job_id):
        status_data = C.read_json(C.STATUS_FILE, {})
        current_status = status_data.get(job_id, {}).get("status", "")
        if current_status == "paused":
            queue = C.read_json(C.QUEUE_FILE, [])
            for j in queue:
                if j["id"] == job_id:
                    j["status"] = "queued"
            C.write_json(C.QUEUE_FILE, queue)
            self.start_download_service()
        else:
            self.send_control(job_id, "pause")

    def on_cancel(self, job_id):
        self.send_control(job_id, "cancel")

    def on_open(self, job_id):
        status_data = C.read_json(C.STATUS_FILE, {})
        info = status_data.get(job_id, {})
        saved_uri = info.get("saved_uri", "")
        saved_path = info.get("saved_path", "")
        if saved_uri:
            self.open_saf_uri(saved_uri)
        elif saved_path:
            self.set_status(f"Saved at: {saved_path}")
        else:
            self.set_status("File not ready yet")

    def open_saf_uri(self, uri_str):
        try:
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity

            mime_type = "video/*"
            if uri_str.lower().endswith((".mp3", ".m4a", ".opus", ".aac", ".wav")):
                mime_type = "audio/*"

            intent = Intent(Intent.ACTION_VIEW)
            intent.setDataAndType(Uri.parse(uri_str), mime_type)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            activity.startActivity(intent)
        except Exception as e:
            self.set_status(f"Could not open file: {e}")

    # ==============================================================
    def set_status(self, text):
        self.status_label.text = text

    def set_widget_text(self, widget, text):
        widget.text = text


if __name__ == "__main__":
    YTDownloaderApp().run()
