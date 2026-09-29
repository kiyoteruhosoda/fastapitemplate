from enum import StrEnum


class NotificationChannel(StrEnum):
    """お知らせを出す場所。値が DB と API に出る安定キーなので変えない。"""

    #: ヘッダーのベル。一覧に残り、既読にするまで数に出る。
    BELL = "bell"
    #: 画面の上部。閉じるか押すまで出続ける。
    BANNER = "banner"
    #: 端末への通知（Web Push）。購読している端末にだけ届く。
    PUSH = "push"
