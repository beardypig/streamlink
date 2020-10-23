"""
    New plugins should use streamlink.plugin.Plugin instead
    of this module, but this is kept here for backwards
    compatibility.
"""

from ..exceptions import NoPluginError, NoStreamsError, PluginError
from ..plugin import Plugin
