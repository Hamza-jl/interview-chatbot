"""Turning an arbitrary document into an interview.

The existing questionnaire is hand-written: `app/pca/blueprint.py` names the
exact table, row and column every answer is written to. That is right for two
templates the team controls, and useless for a document somebody uploads five
minutes before a workshop.

This package derives the same thing at runtime. Structure discovery is
deterministic - a model is never asked where the blanks are, only how to ask
about one it has been handed.
"""
