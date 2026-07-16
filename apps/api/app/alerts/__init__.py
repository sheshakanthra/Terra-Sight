"""Deterministic trend detection and alert generation.

Rules decide, the LLM only phrases (Appendix B.5): every alert here is produced
by numeric rules and carries its own evidence. Nothing in engine.py does I/O, so
the alert logic is exhaustively unit-testable.
"""
