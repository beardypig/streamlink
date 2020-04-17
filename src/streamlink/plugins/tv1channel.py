import logging
import re

from streamlink.plugin import Plugin
from streamlink.plugin.api import useragents
from streamlink.plugin.api.utils import itertags
from streamlink.stream import HLSStream

log = logging.getLogger(__name__)


class TV1Channel(Plugin):
    _url_re = re.compile(r'https?://(?:www\.)?tv1channel\.org/(?!play/)(?:index\.php/livetv)?')
    _hls_load = re.compile(r'''hls.loadSource\((?P<quote>["']?)(?P<url>http.*?)(?P=quote)\)''')

    @classmethod
    def can_handle_url(cls, url):
        return cls._url_re.match(url) is not None

    def _get_streams(self):
        self.session.http.headers.update({'User-Agent': useragents.FIREFOX})
        res = self.session.http.get(self.url)
        for iframe in itertags(res.text, 'iframe'):
            if 'cdn.netbadgers.com' not in iframe.attributes.get('src'):
                continue

            iframe_url = iframe.attributes.get('src')
            log.debug("Found iframe: {0}".format(iframe_url))
            res = self.session.http.get(iframe_url)

            m = self._hls_load.search(res.text)
            if m:
                return HLSStream.parse_variant_playlist(self.session, m.group("url"))
            else:
                log.debug("Could not find hls.loadSource call")

        log.debug("Could not find expected iframe src")


__plugin__ = TV1Channel
