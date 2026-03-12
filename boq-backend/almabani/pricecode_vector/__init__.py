"""
Price Code Vector Service – vector-based price code matching.

Uses S3 Vectors (embedding similarity) instead of the SQLite/TF-IDF
lexical search approach in ``almabani.pricecode``.

INDEX mode:  Parse a BOQ with price codes filled → embed → store in S3 Vectors.
ALLOCATE mode: Parse a BOQ needing codes → embed → query S3 Vectors → fill.
"""
