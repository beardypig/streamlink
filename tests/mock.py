from __future__ import absolute_import
import sys


if (sys.version_info.major == 3) and (sys.version_info.minor > 5):
    from unittest.mock import *
    import unittest.mock as mock
    __all__ = mock.__all__
else:
    from mock import *
    import mock
    __all__ = mock.__all__
