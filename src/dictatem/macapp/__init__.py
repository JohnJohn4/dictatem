"""macOS ``.app`` identity shell — pure pieces (#61 / ADR-0014).

The locally-generated, unsigned ``Dictatem.app`` exists to give TCC a stable
permission identity (the user grants "Dictatem", not "Python", and grants
survive ``uv tool upgrade``). This package holds the *pure*, CI-verifiable
parts: the Info.plist renderer (``plist.py``). The ``.app`` directory layout,
exec shim, and ``--install-macos-app`` subcommand are native/manual-QA work
that lands separately.
"""
