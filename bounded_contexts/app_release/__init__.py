"""app_release — tell users about the latest release of the mobile apps we distribute (ADR-0081 §4).

The apps (built from flutterbase) do not go through the Play Store; signed APKs are
distributed via the distribution store (Garage's ``artifacts`` bucket; people get them from
share.nolumia.com). Devices have no way to learn that a new release is out, so the server
reads the ``latest.json`` written to the distribution store and returns it to signed-in apps.

Moved over from photonest's ADR-0079.
"""
