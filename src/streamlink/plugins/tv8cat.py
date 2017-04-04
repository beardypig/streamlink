from __future__ import print_function

import re

from streamlink.plugin import Plugin
from streamlink.plugin.api import http
from streamlink.plugins.brightcove import BrightcovePlayer
from streamlink.utils import update_scheme


class TV8cat(Plugin):
    url_re = re.compile(r"https?://(?:www\.)?8tv\.cat/directe/?")
    live_iframe = "http://www.8tv.cat/wp-content/themes/8tv/_/inc/_live_html.php"
    iframe_re = re.compile(r'iframe .*?src="((?:https?)?//[^"]*?)"')

    @classmethod
    def can_handle_url(cls, url):
        return cls.url_re.match(url) is not None

    def _find_iframe(self, res):
        iframe = self.iframe_re.search(res.text)
        url = iframe and iframe.group(1)

        if url:
            return update_scheme(self.url, url)

    def _get_streams(self):
        res = http.get(self.live_iframe)
        brightcove_url = self._find_iframe(res)

        if brightcove_url:
            self.logger.debug("Found Brightcove embed url: {0}", brightcove_url)
            return BrightcovePlayer.from_url(self.session, brightcove_url)


__plugin__ = TV8cat
