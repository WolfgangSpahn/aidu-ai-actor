# Copyright (C) 2026 Dr. Wolfgang Spahn, PHBern
#
# MIT License — see LICENSE file for details.
# If you use this software in academic work, citation of the original author is requested.

"""Hold the process-wide runtime limits and diagnostic switches used by actors."""


class Config:
    max_step = 10
    show_trace = False
    debug = False


config = Config()
