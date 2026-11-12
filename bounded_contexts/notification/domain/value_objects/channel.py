from enum import StrEnum


class NotificationChannel(StrEnum):
    """Where a notification appears. The values are stable keys in the DB and the API; don't change them."""

    #: Bell in the header. Stays in the list and is counted until read.
    BELL = "bell"
    #: Top of the screen. Shown until dismissed or tapped.
    BANNER = "banner"
    #: Device notification (Web Push). Reaches only subscribed devices.
    PUSH = "push"
