[app]
title = Судоку
package.name = sudokumobile
package.domain = org.sudoku

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.0.0

requirements = python3,kivy==2.3.1

orientation = portrait
fullscreen = 0

android.accept_sdk_license = True
android.permissions = INTERNET
android.api = 31
android.minapi = 21
#android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
