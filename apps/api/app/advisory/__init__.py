"""Advisory generation.

Turns structured alerts + weather into a short, plain-language action list. The
LLM only phrases; a deterministic template is the source of truth and the
guaranteed fallback, so the product works with no LLM at all. Both paths obey
the same hard rules: reference only supplied alerts, hedge causes, cite the
numbers, and never name a chemical or a dose.
"""
