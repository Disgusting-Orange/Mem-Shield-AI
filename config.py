"""
config.py
---------
Tunable constants for the Execution Runtime Guardian.
Keep these here (not hardcoded in guardian.py) so thresholds can be
adjusted without touching detection logic.
"""

# Known substrings that indicate a "silent" failure even when status=="success"
FAILURE_SIGNATURES = ["error", "exception", "traceback", "timeout", "null", "failed"]

# Window (seconds) within which an identical call is considered redundant
REDUNDANCY_WINDOW_SECONDS = 30
