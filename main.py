# -*- coding: utf-8 -*-
"""
YT Downloader - تطبيق أندرويد حقيقي (Kivy) - واجهة عربية بالكامل
تبويبين: "تحميل" للشاشة الرئيسية، و"الإعدادات" لمجلد التخزين وعدد
التحميلات المتزامنة وسجل التحميلات/الأخطاء.
"""
import os
import uuid
import threading

from kivy.config import Config
# مبنخليش التطبيق ياخد الشاشة كلها - نسيب شريط الحالة (الساعة/البطارية)
# وأزرار التنقل السفلية ظاهرة زي أي تطبيق عادي
Config.set("graphics", "fullscreen", "0")

from kivy.core.window import Window

from kivy.app import App
from kivy.lang import Builder
from kivy.factory import Factory
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.behaviors import ToggleButtonBehavior
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.image import AsyncImage
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.switch import Switch
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.core.clipboard import Clipboard
from kivy.clock import Clock
from kivy.utils import platform
from kivy.properties import ListProperty, StringProperty

from yt_dlp import YoutubeDL

import arabic_reshaper
from bidi.algorithm import get_display

import dl_common as C

# مسار الخط اللي بيدعم العربي - لازم يكون موجود جوه مجلد assets بجانب main.py
FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "AppFont.ttf")


def ar(text):
    """
    Kivy بيرسم كل حرف عربي لوحده من غير ما يوصل الحروف ببعضها، فالنص
    بيبان متقطّع. الدالة دي بتعمل reshape + bidi قبل الحط في أي نص عربي
    (سواء عنوان فيديو أو أي نص ثابت في الواجهة).
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

<Button3D>:
    background_normal: ""
    background_down: ""
    background_color: 0, 0, 0, 0
    bg_color: 0.20, 0.45, 0.85, 1
    color: 1, 1, 1, 1
    bold: True
    font_name: app.font_path
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
    Label:
        text: root.quality_name
        font_size: "10sp"
        font_name: app.font_path
        color: (1, 1, 1, 0.85) if not root.disabled else (0.6, 0.6, 0.6, 0.85)
        size_hint: None, None
        size: self.texture_size
        pos: root.x + dp(6), root.top - self.height - dp(4)
    Label:
        text: root.size_text
        font_size: "14sp"
        font_name: app.font_path
        bold: True
        color: (1, 1, 1, 1) if not root.disabled else (0.6, 0.6, 0.6, 1)
        center: root.center_x, root.center_y - dp(4)

<SmallButton3D@Button3D>:
    font_size: "13sp"

<DownloadCard>:
    orientation: "vertical"
    size_hint_y: None
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


class QualityToggle(ToggleButtonBehavior, FloatLayout):
    bg_color = ListProperty([0.26, 0.26, 0.30, 1])
    quality_name = StringProperty("")
    size_text = StringProperty("")


class DownloadCard(BoxLayout):
    pass


Builder.load_string(KV)
SmallButton3D = Factory.SmallButton3D


class YTDownloaderApp(App):
    font_path = FONT_PATH

    def build(self):
        self.title = "منزّل يوتيوب"
        self.picked_url = ""
        self.video_title = ""
        self.video_thumb = ""
        self.selected_quality_index = 6  # 720p افتراضيًا
        self.storage_uri = C.load_storage_uri()
        self.quality_buttons = []
        self.download_widgets = {}  # job_id -> dict of widgets
        self.quality_data = {}
        self.is_playlist = False
        self.playlist_entries = []
        self.playlist_title = ""

        root = TabbedPanel(do_default_tab=False)
        # التابين لازم ياخدوا نص عرض الشاشة بالتساوي، مش عرض ثابت بيسيب
        # فراغ جنبهم. بنربط tab_width بنص عرض اللوحة، ونحدثه لو الشاشة
        # اتدارت (landscape/portrait) أو تغيّر حجمها.
        root.tab_width = Window.width / 2
        root.bind(width=lambda inst, w: setattr(inst, "tab_width", w / 2))

        download_tab = TabbedPanelItem(text=ar("تحميل"))
        download_tab.font_name = FONT_PATH
        download_tab.content = self.build_download_tab()
        root.add_widget(download_tab)

        settings_tab = TabbedPanelItem(text=ar("الإعدادات"))
        settings_tab.font_name = FONT_PATH
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
            text=ar("التقط الرابط وحلّل"),
            font_size="19sp",
            size_hint=(1, None),
            height=dp(56),
        )
        self.btn_analyze.bind(on_release=self.on_analyze_pressed)
        layout.add_widget(self.btn_analyze)

        # ---------------- بطاقة نتيجة التحليل + اختيار الجودة ----------------
        # الارتفاع بيُحسب أوتوماتيك من محتواها (minimum_height) بدل قيمة
        # ثابتة، لأن القيمة الثابتة القديمة كانت أصغر من المحتوى الفعلي
        # وده كان بيخلي المحتوى يفيض ويتراكب مع زر التحليل اللي فوقها
        self.analyze_card = Card(orientation="vertical", size_hint=(1, None))
        self.analyze_card.bind(minimum_height=self.analyze_card.setter("height"))

        header_row = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(64), spacing=dp(10))
        # الصورة المصغرة بتفضل مخفية تمامًا لحد ما يبقى عندنا صورة فعلية
        # (كانت قبل كده بتبان كمربع أبيض فاضي قبل التحليل)
        self.thumb = AsyncImage(size_hint=(None, None), size=(0, 0), opacity=0)
        header_row.add_widget(self.thumb)
        self.title_label = Label(
            text="",
            font_size="15sp",
            font_name=FONT_PATH,
            halign="right",
            valign="middle",
        )
        self.title_label.bind(size=lambda inst, s: setattr(inst, "text_size", s))
        header_row.add_widget(self.title_label)
        self.analyze_card.add_widget(header_row)

        # ---------------- صف اختيار نطاق قائمة تشغيل (يظهر بس لو الرابط قائمة) ----------------
        self.playlist_row = BoxLayout(orientation="horizontal", size_hint=(1, None), height=0, spacing=dp(8), opacity=0)
        self.playlist_row.add_widget(Label(text=ar("من فيديو رقم"), font_name=FONT_PATH, font_size="13sp", size_hint=(0.4, 1)))
        self.input_from = TextInput(text="1", multiline=False, input_filter="int", font_size="14sp", size_hint=(0.25, 1))
        self.playlist_row.add_widget(self.input_from)
        self.playlist_row.add_widget(Label(text=ar("إلى رقم"), font_name=FONT_PATH, font_size="13sp", size_hint=(0.15, 1)))
        self.input_to = TextInput(text="1", multiline=False, input_filter="int", font_size="14sp", size_hint=(0.25, 1))
        self.playlist_row.add_widget(self.input_to)
        self.analyze_card.add_widget(self.playlist_row)

        # صف الصوت (2 زرار)
        row_audio = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(44), spacing=dp(8))
        # صفين فيديو (3 أزرار لكل صف)
        row_video_1 = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(44), spacing=dp(8))
        row_video_2 = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(44), spacing=dp(8))

        rows_map = [row_audio, row_audio, row_video_1, row_video_1, row_video_1, row_video_2, row_video_2, row_video_2]
        self.quality_buttons = []
        for idx, (key, label) in enumerate(C.QUALITY_LABELS):
            display_name = label if key.isdigit() else ar(label)
            btn = QualityToggle(group="quality_select", quality_name=display_name)
            btn.quality_key = key
            btn.base_label = label
            btn.quality_index = idx
            if idx == self.selected_quality_index:
                btn.state = "down"
            btn.bind(on_release=self.on_quality_selected)
            self.quality_buttons.append(btn)
            rows_map[idx].add_widget(btn)

        self.analyze_card.add_widget(row_audio)
        self.analyze_card.add_widget(row_video_1)
        self.analyze_card.add_widget(row_video_2)

        self.btn_add_queue = Button3D(text=ar("أضف للتحميل"), size_hint=(1, None), height=dp(48))
        self.btn_add_queue.bg_color = [0.22, 0.62, 0.36, 1]
        self.btn_add_queue.bind(on_release=self.on_add_to_queue)
        self.analyze_card.add_widget(self.btn_add_queue)

        layout.add_widget(self.analyze_card)

        # ---------------- عنوان قائمة التحميلات + زر تصفير السجل ----------------
        downloads_header = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(36), spacing=dp(8))
        downloads_header.add_widget(Label(text=ar("التحميلات"), font_name=FONT_PATH, bold=True, size_hint=(0.6, 1)))
        btn_reset = SmallButton3D(text=ar("تصفير السجل"), size_hint=(0.4, 1))
        btn_reset.bg_color = [0.55, 0.30, 0.15, 1]
        btn_reset.bind(on_release=self.on_reset_downloads)
        downloads_header.add_widget(btn_reset)
        layout.add_widget(downloads_header)

        # ---------------- بطاقة قائمة التحميلات (Scrollable) ----------------
        scroll = ScrollView(size_hint=(1, 1))
        self.downloads_list = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.downloads_list.bind(minimum_height=self.downloads_list.setter("height"))
        scroll.add_widget(self.downloads_list)
        layout.add_widget(scroll)

        self.status_label = Label(text="", font_size="13sp", font_name=FONT_PATH, size_hint=(1, None), height=dp(22))
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
        storage_card.add_widget(Label(text=ar("مجلد التخزين"), font_name=FONT_PATH, bold=True, size_hint=(1, None), height=dp(24)))
        self.btn_choose_folder = Button3D(
            text=ar("تم اختيار المجلد") if self.storage_uri else ar("اختر مجلد التخزين"),
            size_hint=(1, None),
            height=dp(48),
        )
        self.btn_choose_folder.bind(on_release=self.on_choose_folder_pressed)
        storage_card.add_widget(self.btn_choose_folder)
        layout.add_widget(storage_card)

        # ---------------- جودة الصوت المقرون بالفيديو ----------------
        audio_pair_card = Card(orientation="horizontal", size_hint=(1, None), height=dp(70))
        audio_pair_label = Label(
            text=ar("دمج الفيديو مع أقل جودة صوت (لتوفير البيانات)"),
            font_name=FONT_PATH,
            font_size="14sp",
            halign="right",
            valign="middle",
            size_hint=(0.8, 1),
        )
        audio_pair_label.bind(size=lambda inst, s: setattr(inst, "text_size", s))
        audio_pair_card.add_widget(audio_pair_label)
        settings_for_switch = C.read_settings()
        self.switch_low_audio = Switch(
            active=bool(settings_for_switch.get("pair_low_audio", True)),
            size_hint=(0.2, 1),
        )
        self.switch_low_audio.bind(active=self.on_pair_audio_changed)
        audio_pair_card.add_widget(self.switch_low_audio)
        layout.add_widget(audio_pair_card)

        # ---------------- عدد التحميلات المتزامنة ----------------
        concurrency_card = Card(orientation="vertical", size_hint=(1, None), height=dp(110))
        concurrency_card.add_widget(Label(text=ar("عدد التحميلات في نفس الوقت"), font_name=FONT_PATH, bold=True, size_hint=(1, None), height=dp(24)))
        settings = C.read_settings()
        self.spinner_concurrency = Spinner(
            text=str(settings.get("max_concurrent", 2)),
            values=("1", "2", "3", "4"),
            font_name=FONT_PATH,
            size_hint=(1, None),
            height=dp(48),
        )
        self.spinner_concurrency.bind(text=self.on_concurrency_changed)
        concurrency_card.add_widget(self.spinner_concurrency)
        layout.add_widget(concurrency_card)

        # ---------------- سجل التحميلات ----------------
        dl_log_card = Card(orientation="vertical", size_hint=(1, None), height=dp(240))
        dl_log_card.add_widget(Label(text=ar("سجل التحميلات"), font_name=FONT_PATH, bold=True, size_hint=(1, None), height=dp(24)))
        dl_log_scroll = ScrollView(size_hint=(1, 1))
        self.download_log_label = Label(
            text="", font_size="12sp", font_name=FONT_PATH, size_hint_y=None, halign="right", valign="top"
        )
        self.download_log_label.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None)),
            texture_size=lambda inst, s: setattr(inst, "height", s[1]),
        )
        dl_log_scroll.add_widget(self.download_log_label)
        dl_log_card.add_widget(dl_log_scroll)
        btn_copy_dl_log = SmallButton3D(text=ar("نسخ سجل التحميلات"), size_hint=(1, None), height=dp(40))
        btn_copy_dl_log.bind(on_release=lambda *_: self.copy_log_to_clipboard(C.DOWNLOAD_LOG_FILE))
        dl_log_card.add_widget(btn_copy_dl_log)
        layout.add_widget(dl_log_card)

        # ---------------- سجل الأخطاء ----------------
        err_log_card = Card(orientation="vertical", size_hint=(1, None), height=dp(240))
        err_log_card.add_widget(Label(text=ar("سجل الأخطاء"), font_name=FONT_PATH, bold=True, size_hint=(1, None), height=dp(24)))
        err_log_scroll = ScrollView(size_hint=(1, 1))
        self.error_log_label = Label(
            text="", font_size="12sp", font_name=FONT_PATH, size_hint_y=None, halign="right", valign="top"
        )
        self.error_log_label.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None)),
            texture_size=lambda inst, s: setattr(inst, "height", s[1]),
        )
        err_log_scroll.add_widget(self.error_log_label)
        err_log_card.add_widget(err_log_scroll)
        btn_copy_err_log = SmallButton3D(text=ar("نسخ سجل الأخطاء"), size_hint=(1, None), height=dp(40))
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

    def on_pair_audio_changed(self, switch, value):
        settings = C.read_settings()
        settings["pair_low_audio"] = bool(value)
        C.write_settings(settings)

    def copy_log_to_clipboard(self, path):
        content = C.read_log(path)
        Clipboard.copy(content)
        self.set_status(ar("تم نسخ السجل"))

    def refresh_logs(self, dt):
        if hasattr(self, "download_log_label"):
            self.download_log_label.text = C.read_log(C.DOWNLOAD_LOG_FILE) or ar("(فارغ)")
        if hasattr(self, "error_log_label"):
            self.error_log_label.text = C.read_log(C.ERROR_LOG_FILE) or ar("(فارغ)")

    # ==============================================================
    # زر تصفير سجل التحميلات
    # ==============================================================
    def on_reset_downloads(self, *_):
        queue = C.read_json(C.QUEUE_FILE, [])
        remaining = [j for j in queue if j.get("status") in ("queued", "downloading", "paused")]
        C.write_json(C.QUEUE_FILE, remaining)

        remaining_ids = {j["id"] for j in remaining}
        status_data = C.read_json(C.STATUS_FILE, {})
        status_data = {k: v for k, v in status_data.items() if k in remaining_ids}
        C.write_json(C.STATUS_FILE, status_data)

        C.clear_log(C.DOWNLOAD_LOG_FILE)
        C.clear_log(C.ERROR_LOG_FILE)
        self.set_status(ar("تم تنظيف السجل"))

    # ==============================================================
    # التحليل
    # ==============================================================
    def on_quality_selected(self, btn):
        self.selected_quality_index = btn.quality_index

    def on_analyze_pressed(self, *_):
        threading.Thread(target=self.analyze, daemon=True).start()

    def analyze(self):
        Clock.schedule_once(lambda dt: self.set_widget_text(self.btn_analyze, ar("جاري التحليل...")))
        try:
            url = Clipboard.paste()
            self.picked_url = url

            # أول خطوة: فحص سريع (extract_flat) لمعرفة لو الرابط ده قائمة
            # تشغيل كاملة قبل ما نعمل تحليل كامل مكلف لكل فيديو فيها
            probe_opts = {
                "quiet": True,
                "no_warnings": True,
                "cachedir": False,
                "extract_flat": "in_playlist",
                "noplaylist": False,
            }
            with YoutubeDL(probe_opts) as ydl:
                probe_info = ydl.extract_info(url, download=False)

            if probe_info.get("_type") == "playlist" or "entries" in probe_info:
                self.is_playlist = True
                self.playlist_entries = [e for e in (probe_info.get("entries") or []) if e]
                self.playlist_title = probe_info.get("title") or "Playlist"
                self.video_title = self.playlist_title
                thumbs = probe_info.get("thumbnails") or []
                self.video_thumb = thumbs[-1].get("url", "") if thumbs else ""
                self.quality_data = {}
            else:
                self.is_playlist = False
                full_opts = {"quiet": True, "no_warnings": True, "cachedir": False, "noplaylist": True}
                with YoutubeDL(full_opts) as ydl2:
                    info = ydl2.extract_info(url, download=False)
                self.video_title = info.get("title", "")
                self.video_thumb = info.get("thumbnail", "")
                sorted_audio, video_qualities = C.analyze_formats(info)
                settings = C.read_settings()
                use_low_audio = bool(settings.get("pair_low_audio", True))
                self.quality_data = C.pick_best_options(sorted_audio, video_qualities, use_low_audio=use_low_audio)

            Clock.schedule_once(lambda dt: self.on_analyze_done())
        except Exception as e:
            error_msg = str(e)
            Clock.schedule_once(lambda dt: self.set_status(f"خطأ: {error_msg}"))
            Clock.schedule_once(lambda dt: self.set_widget_text(self.btn_analyze, ar("التقط الرابط وحلّل")))

    def on_analyze_done(self):
        self.title_label.text = ar(self.video_title)
        if self.video_thumb:
            self.thumb.source = self.video_thumb
            self.thumb.size = (dp(64), dp(64))
            self.thumb.opacity = 1
        else:
            self.thumb.size = (0, 0)
            self.thumb.opacity = 0

        # تحديث لابل الحجم في كل زرار جودة (لو فيديو مفرد) أو من غيره
        # (لو قائمة تشغيل، مش هنعرف حجم كل فيديو مقدمًا)
        for btn in self.quality_buttons:
            key = btn.quality_key
            if not self.is_playlist:
                option = self.quality_data.get(key)
                if option:
                    btn.size_text = f"{option[1]} MB"
                    btn.disabled = False
                else:
                    btn.size_text = ar("غير متاح")
                    btn.disabled = True
            else:
                btn.size_text = ""
                btn.disabled = False

        # إظهار/إخفاء صف اختيار نطاق قائمة التشغيل
        if self.is_playlist:
            count = len(self.playlist_entries)
            self.playlist_row.height = dp(46)
            self.playlist_row.opacity = 1
            self.input_from.text = "1"
            self.input_to.text = str(count) if count else "1"
            self.btn_add_queue.text = ar("حمّل النطاق المحدد")
            self.set_status(ar(f"قائمة تشغيل بها {count} فيديو"))
        else:
            self.playlist_row.height = 0
            self.playlist_row.opacity = 0
            self.btn_add_queue.text = ar("أضف للتحميل")

        self.set_widget_text(self.btn_analyze, ar("التقط الرابط وحلّل"))

    # ==============================================================
    # إضافة للتحميل (queue)
    # ==============================================================
    def on_add_to_queue(self, *_):
        if not self.picked_url or not self.video_title:
            self.set_status(ar("حلّل رابط أولًا"))
            return
        if platform == "android" and not self.has_storage_permission():
            self.set_status(ar("من فضلك اسمح بالوصول للملفات ثم اضغط تاني"))
            self.request_storage_permission()
            return

        if self.is_playlist:
            self.enqueue_playlist_range()
        else:
            self.enqueue_single_video()

    def enqueue_single_video(self):
        key, label = C.QUALITY_LABELS[self.selected_quality_index]
        option = self.quality_data.get(key)
        if not option:
            self.set_status(ar("الجودة دي مش متاحة لهذا الفيديو"))
            return
        format_selector, size_mb = option

        job = {
            "id": uuid.uuid4().hex,
            "url": self.picked_url,
            "title": self.video_title,
            "thumbnail": self.video_thumb,
            "quality_key": key,
            "format_selector": format_selector,
            "storage_uri": self.storage_uri,
            "playlist_name": "",
            "status": "queued",
        }
        queue = C.read_json(C.QUEUE_FILE, [])
        queue.append(job)
        C.write_json(C.QUEUE_FILE, queue)
        C.append_download_log(f"{job['title']} ({label}, {size_mb} MB) - queued")

        self.start_download_service()
        self.set_status(ar("تمت الإضافة للتحميل"))

    def enqueue_playlist_range(self):
        count = len(self.playlist_entries)
        if count == 0:
            self.set_status(ar("مفيش فيديوهات في القائمة دي"))
            return
        try:
            from_idx = int(self.input_from.text or "1")
            to_idx = int(self.input_to.text or str(count))
        except ValueError:
            self.set_status(ar("اكتب أرقام صحيحة للنطاق"))
            return

        from_idx = max(1, min(from_idx, count))
        to_idx = max(1, min(to_idx, count))
        if from_idx > to_idx:
            from_idx, to_idx = to_idx, from_idx

        key, label = C.QUALITY_LABELS[self.selected_quality_index]
        playlist_folder = C.sanitize_name(self.playlist_title)

        queue = C.read_json(C.QUEUE_FILE, [])
        added = 0
        for i in range(from_idx - 1, to_idx):
            entry = self.playlist_entries[i]
            video_id = entry.get("id")
            video_url = entry.get("url") or (f"https://www.youtube.com/watch?v={video_id}" if video_id else "")
            if not video_url:
                continue
            title = entry.get("title") or f"video {i + 1}"
            thumbs = entry.get("thumbnails") or []
            thumb_url = thumbs[-1].get("url", "") if thumbs else ""

            job = {
                "id": uuid.uuid4().hex,
                "url": video_url,
                "title": title,
                "thumbnail": thumb_url,
                "quality_key": key,
                "format_selector": "",  # هيتحدد وقت التحميل نفسه في السيرفس
                "storage_uri": self.storage_uri,
                "playlist_name": playlist_folder,
                "status": "queued",
            }
            queue.append(job)
            added += 1

        C.write_json(C.QUEUE_FILE, queue)
        C.append_download_log(f"{self.playlist_title}: {added} videos ({label}) - queued")
        self.start_download_service()
        self.set_status(ar(f"تمت إضافة {added} فيديو من القائمة"))

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
            self.set_status(f"خطأ في فتح الإعدادات: {e}")

    # ==============================================================
    # اختيار مجلد التخزين يدويًا (Storage Access Framework)
    # ==============================================================
    def on_choose_folder_pressed(self, *_):
        if platform != "android":
            self.set_status(ar("اختيار المجلد شغال بس على أندرويد"))
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
            self.set_status(f"خطأ في فتح اختيار المجلد: {e}")

    def on_folder_picked(self, request_code, result_code, intent):
        if request_code != 4321:
            return
        try:
            from jnius import autoclass

            Activity = autoclass("android.app.Activity")
            if result_code != Activity.RESULT_OK or intent is None:
                Clock.schedule_once(lambda dt: self.set_status(ar("تم إلغاء اختيار المجلد")))
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
            Clock.schedule_once(lambda dt: self.set_widget_text(self.btn_choose_folder, ar("تم اختيار المجلد")))
            Clock.schedule_once(lambda dt: self.set_status(ar("تم حفظ مجلد التخزين")))
        except Exception as e:
            error_msg = str(e)
            Clock.schedule_once(lambda dt: self.set_status(f"خطأ في حفظ المجلد: {error_msg}"))

    # ==============================================================
    # تشغيل خدمة التحميل (idempotent - آمن نناديها كذا مرة)
    # ==============================================================
    def start_download_service(self):
        if platform != "android":
            self.set_status(ar("الخدمة شغالة بس على أندرويد"))
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

        for job_id in list(self.download_widgets.keys()):
            if job_id not in current_ids:
                widgets = self.download_widgets.pop(job_id)
                self.downloads_list.remove_widget(widgets["card"])

    def status_text_ar(self, status):
        mapping = {
            "queued": "في الانتظار",
            "downloading": "جاري التحميل",
            "merging": "جاري الدمج",
            "saving": "جاري الحفظ",
            "finished": "تم بنجاح",
            "paused": "متوقف مؤقتًا",
            "cancelled": "ملغي",
            "error": "خطأ",
        }
        return ar(mapping.get(status, status))

    def create_download_card(self, job, status, percent, info):
        job_id = job["id"]
        card = DownloadCard()
        card.bind(minimum_height=card.setter("height"))

        top_row = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(46), spacing=dp(8))
        thumb = AsyncImage(source=job.get("thumbnail", ""), size_hint=(None, None), size=(dp(40), dp(40)))
        top_row.add_widget(thumb)

        title_lbl = Label(
            text=ar(job.get("title", "")),
            font_name=FONT_PATH,
            font_size="13sp",
            halign="right",
            valign="middle",
        )
        title_lbl.bind(size=lambda inst, s: setattr(inst, "text_size", s))
        top_row.add_widget(title_lbl)
        card.add_widget(top_row)

        progress = ProgressBar(max=100, value=percent, size_hint=(1, None), height=dp(24))
        card.add_widget(progress)

        status_lbl = Label(
            text=f"{self.status_text_ar(status)} - {percent:.1f}%",
            font_size="11sp",
            font_name=FONT_PATH,
            size_hint=(1, None),
            height=dp(18),
        )
        card.add_widget(status_lbl)

        buttons_row = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(34), spacing=dp(6))
        btn_pause = SmallButton3D(text=ar("إيقاف مؤقت"), size_hint=(1, 1))
        btn_pause.bind(on_release=lambda *_: self.on_pause_resume(job_id))
        btn_cancel = SmallButton3D(text=ar("إلغاء"), size_hint=(1, 1))
        btn_cancel.bg_color = [0.65, 0.20, 0.20, 1]
        btn_cancel.bind(on_release=lambda *_: self.on_cancel(job_id))
        btn_open = SmallButton3D(text=ar("فتح"), size_hint=(1, 1), disabled=True)
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
        widgets["status_lbl"].text = f"{self.status_text_ar(status)} - {percent:.1f}%"
        if status == "error" and info.get("error"):
            widgets["status_lbl"].text = ar("خطأ") + f": {info.get('error')[:50]}"
        self.apply_card_state(job_id, status, info)

    def apply_card_state(self, job_id, status, info):
        widgets = self.download_widgets[job_id]
        btn_pause = widgets["btn_pause"]
        btn_cancel = widgets["btn_cancel"]
        btn_open = widgets["btn_open"]

        if status == "downloading":
            btn_pause.text = ar("إيقاف مؤقت")
            btn_pause.disabled = False
        elif status == "paused":
            btn_pause.text = ar("استكمال")
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
            self.set_status(ar("محفوظ في") + f": {saved_path}")
        else:
            self.set_status(ar("الملف لسه مش جاهز"))

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
            self.set_status(f"تعذر فتح الملف: {e}")

    # ==============================================================
    def set_status(self, text):
        self.status_label.text = text

    def set_widget_text(self, widget, text):
        widget.text = text


if __name__ == "__main__":
    YTDownloaderApp().run()
