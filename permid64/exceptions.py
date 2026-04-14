"""
exceptions.py — Custom exception types for permid64.
"""
from __future__ import annotations


class PermId64ConfigError(Exception):
    """
    Raised when a configuration error is detected at startup that would
    make ID generation unsafe.

    .. note::
        **Reserved for v0.5 — not yet raised by any production code.**

        The planned ``ReservedBlockSource`` (central-coordinator model for
        NFS/CIFS deployments) will raise this exception when the coordinator
        is unreachable or misconfigured at startup.

        In v0.3, the NFS/CIFS detection path was intentionally downgraded to
        a ``UserWarning`` (see ``ProcessSafeCounterSource`` and
        ``_warn_network_fs``).  This class exists in the public API surface
        so that callers can write ``except PermId64ConfigError`` today and
        be ready for v0.5 without a breaking import change.

    Examples
    --------
    - (v0.5+) State file is on a network filesystem (NFS/CIFS) and the
      coordinator endpoint is not reachable.
    - (v0.5+) Block-reservation lease has expired without renewal.
    """
