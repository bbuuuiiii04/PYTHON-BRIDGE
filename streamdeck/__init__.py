"""Stream Deck controller package.

Marker so ``streamdeck_midi`` is importable as
``rb_ss_bridge_v2.streamdeck.streamdeck_midi`` (the USB bundle's
``--run-streamdeck`` entrypoint needs a real import, not a script exec). The dev
watcher still runs ``streamdeck/streamdeck_midi.py`` as a plain script, which an
``__init__.py`` does not affect.
"""
