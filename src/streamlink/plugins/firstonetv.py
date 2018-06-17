import logging
import re

from streamlink.plugin import Plugin
from streamlink.plugin.api import http
from streamlink.stream import HLSStream
from streamlink.utils import parse_json

log = logging.getLogger(__name__)


class FirstOneTV(Plugin):
    url_re = re.compile(r"https?://(?:www\.)firstonetv\.net/Live/", re.IGNORECASE)
    _favourite_re = re.compile(r'''addFavorite\(['"](\w+)['"], ['"](\d+)['"]\)''')
    api_url = "https://www.firstonetv.net/api/"

    @classmethod
    def can_handle_url(cls, url):
        return cls.url_re.match(url) is not None

    def _get_stream_urls(self, country_code, channel_id):
        res = http.get(self.api_url, params={
            "action": "channel",
            "ctoken": "apptest",
            "c": country_code,
            "id": channel_id
        })
        data = http.json(res)

        if data['state']:
            log.info("Found channel: {0}".format(data['title']))
            surl = data['surl']
            log.debug("surl: {0}".format(data['surl']))
            if surl.startswith("{"):
                for _, ssurl in parse_json(surl).items():
                    yield ssurl
            else:
                yield surl
        else:
            log.warning("{0} (errorCode:{1})".format(data["msg"] or "An error occurred",
                                                     data['errorCode']))

    def _get_streams(self):
        res = http.get(self.url)
        match = self._favourite_re.search(res.text)
        if match:
            country_code, channel_id = match.group(1), match.group(2)
            log.debug("Channel ID: {0}; Country Code: {1}".format(channel_id, country_code))

            for stream_url in self._get_stream_urls(country_code, channel_id):
                log.debug("stream_url: {0}".format(stream_url))
                if stream_url.startswith("iframe"):
                    iframe = stream_url.split("|")[1]
                    for s in self.session.streams(iframe).items():
                        yield s
                else:
                    streams = HLSStream.parse_variant_playlist(self.session, stream_url)
                    if not streams:
                        yield "live", HLSStream(self.session, stream_url)
                    else:
                        for s in streams:
                            yield s


__plugin__ = FirstOneTV
