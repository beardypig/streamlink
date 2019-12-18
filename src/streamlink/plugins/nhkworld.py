"""Plugin for NHK World, NHK Japan's english TV channel."""

import re

from streamlink.plugin import Plugin
from streamlink.plugin.api import validate
from streamlink.stream import HLSStream

API_URL = "https://{}.nhk.or.jp/nhkworld/app/tv/hlslive_web.json"

_url_re = re.compile(r"http(?:s)?://(?:(\w+)\.)?nhk.or.jp/nhkworld")
_schema = validate.Schema({
    "main": {
        "jstrm": validate.url(),
        "wstrm": validate.url(),
    }
}, validate.get("main"))


class NHKWorld(Plugin):
    @classmethod
    def can_handle_url(cls, url):
        return _url_re.match(url) is not None

    def get_title(self):
        return "NHK World"

    def _get_streams(self):
        # get the HLS xml from the same sub domain as the main url, defaulting to www
        sdomain = _url_re.match(self.url).group(1) or "www"
        res = self.session.http.get(API_URL.format(sdomain))

        stream_urls = self.session.http.json(res, schema=_schema)
        return HLSStream.parse_variant_playlist(self.session, stream_urls['wstrm'])


__plugin__ = NHKWorld
