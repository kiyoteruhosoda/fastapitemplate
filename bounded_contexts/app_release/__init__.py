"""app_release — 配布しているスマホアプリの最新版を知らせる（ADR-0048）。

アプリ（flutterbase から作ったもの）は Play ストアを通らず、署名済みの APK を
配布面（Garage の ``artifacts`` バケット。人は share.nolumia.com から取る）に
置いて配っている。端末は新しい版が出たことを知る手段を持たないので、
配布面が書く ``latest.json`` をサーバーが読み、ログイン済みのアプリへ返す。

photonest の ADR-0079 から移したもの。
"""
