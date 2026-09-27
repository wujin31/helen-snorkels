"""Pure parsers: raw archived bytes -> normalized observations (SI, UTC).

Each parser raises ValueError on a response it can't make sense of; callers
turn that into a failed SourceResult rather than a crash.
"""
