from __future__ import annotations

import os
import unittest


requires_authorized_catalog = unittest.skipIf(
    os.environ.get("SHANDONG_SKIP_AUTHORIZED_CATALOG_TESTS") == "1",
    "requires the locally authorized production catalog",
)
