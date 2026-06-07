"""macOS ``.app`` identity shell — pure pieces (#61 / ADR-0014).

The locally-generated, unsigned ``Dictatem.app`` exists to give TCC a stable
permission identity (the user grants "Dictatem", not "Python", and grants
survive ``uv tool upgrade``). This package holds the *pure*, CI-verifiable
parts: the Info.plist renderer (``plist.py``) and the bundle generator —
layout, exec shim, launch command (``bundle.py``) — both running against
injected paths on any OS. Only "the generated ``.app`` launches and binds TCC
grants on a real Mac" is manual QA; the thin ``--install-macos-app`` glue
lives in ``daemon``.
"""
