"""Autostart: pure reconcile decision + per-OS AutostartRegistrar adapters.

The daemon owns autostart and reconciles the OS entry to
``config.startup.autostart`` on launch (see ADR-0012). The reconcile *decision*
lives here as pure logic (``reconcile.py``); the native registry adapter
(``win32_registrar.py``) is manual-QA only and excluded from pyright/tests.
"""
