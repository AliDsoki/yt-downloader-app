[app]

# (str) Title of your application
title = YT Downloader

# (str) Package name
package.name = ytdownloader

# (str) Package domain (needed for android/ios packaging)
package.domain = org.alidsoki

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,jpeg,kv,atlas,json

# (list) List of inclusions using pattern matching
#source.include_patterns = assets/*,images/*.png

# (str) Application versioning
version = 1.0

# (list) Application requirements
# yt-dlp, requests, certifi are pure python and installable via pip during the p4a build
# لازم hostpython3 (بايثون البناء) و python3 (بايثون الهدف) يكونوا نفس النسخة بالظبط
# دي متطلبة أساسية من python-for-android، لو مش متطابقين البناء بيفشل فورًا
requirements = python3==3.11.8,hostpython3==3.11.8,kivy==2.3.0,yt-dlp,requests,certifi,pyjnius,android

# (str) Presplash of the application
#presplash.filename = %(source.dir)s/data/presplash.png

# (str) Icon of the application
#icon.filename = %(source.dir)s/data/icon.png

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (list) Permissions
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,FOREGROUND_SERVICE,WAKE_LOCK,POST_NOTIFICATIONS

# (list) The Android archs to build for
# مبني لمعمار واحد بس (arm64-v8a) - بيغطي كل الموبايلات الحديثة من 2017 لحد دلوقتي
# وده بيقلل وقت البناء وفرصة الأخطاء لأنه بيبني نسخة واحدة بس مش اتنين
android.archs = arm64-v8a

# (int) Target Android API
android.api = 34

# (int) Minimum API your APK / AAB will support
android.minapi = 24

# (str) Android NDK version to use
android.ndk = 25b

# (bool) If True, then skip trying to update the Android sdk
android.skip_update = False

# (bool) If True, then automatically accept SDK license
android.accept_sdk_license = True

# (str) The format used to package the app for release mode (aab or apk)
android.release_artifact = apk

# --------------------------------------------------------------------
# هنا بنسجل خدمة الخلفية (Foreground Service) اللي في service.py
# الصيغة: <اسم الخدمة كما هتتنادى من main.py> : <مسار ملف السيرفس> : foreground
# main.py بيعمل autoclass باسم "ServiceYtservice" لذلك اسم الخدمة هنا لازم يكون "ytservice"
# --------------------------------------------------------------------
services = ytservice:service.py:foreground

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 1
