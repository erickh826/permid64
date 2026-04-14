"""
exceptions.py — Custom exception types for permid64.
"""
from __future__ import annotations


class PermId64ConfigError(Exception):
    """
    Raised when a configuration error is detected at startup that would
    make ID generation unsafe.

    Examples
    --------
    - State file is on a network filesystem (NFS/CIFS) where POSIX
      advisory locks are unreliable.  In v0.3 this is downgraded to a
      UserWarning; future versions may raise this exception.
    """
