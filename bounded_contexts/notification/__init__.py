"""notification context — delivers notifications written by admins to users (ADR-0081 §3).

A notification is defined by three things: "what" (title, body, link), "where it appears"
(channel) and "to whom" (audience).

========== ======================================================================
Channel     Where it appears
========== ======================================================================
``bell``    Bell in the header (stays in the list; counted until read)
``banner``  Top of the screen (shown until dismissed or tapped)
``push``    Device notification (Web Push; shown even when the browser/PWA is closed)
========== ======================================================================

The audience is "everyone", "a group" or "an individual". **It is delivered to the members as of
sending** (one row per person in ``notification_deliveries``). People who join the group later
don't receive it, and it doesn't vanish from those who leave.
"""
