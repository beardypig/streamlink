import base64
import pickle
import re

from streamlink.plugin import Plugin
from streamlink.plugin.api import http
from streamlink.stream import HLSStream

from streamlink.stream.hls_playlist import M3U8Parser

_url_re = re.compile(r"https?://(\w+\.)?yoursportsinhd.com")
_m3u8_re = re.compile(r"""#hlsjslive.*?sources:.*?src:\s*["']\s*(?P<url>(?!http://nasatv).*?)\s*["']""", re.DOTALL)


class YSIHDM3U8Parser(M3U8Parser):
    replace_pairs = pickle.loads(base64.b64decode(
        b'gANdcQAoWBYAAABodHRwczovL21mLnN2Yy5uaGwuY29tcQFYJQAAAGh0dHA6Ly95b3Vyc3'
        b'BvcnRzaW5oZC5jb20vbmhsL2dldF9rZXlxAoZxA1hKAAAAaHR0cHM6Ly9icm9hZGJhbmQu'
        b'ZXNwbi5nby5jb20vZXNwbjMvYXV0aC9lc3BubmV0d29ya3MvbTN1OC92MS9nZW5lcmF0ZU'
        b'tleT9xBFgnAAAAaHR0cDovL3lvdXJzcG9ydHNpbmhkLmNvbS9uY2FhL2dldF9rZXkvcQWG'
        b'cQZYVwAAAGh0dHBzOi8vbWxiLXdzLW1mLm1lZGlhLm1sYi5jb20vcHViYWpheHdzL2JhbX'
        b'Jlc3QvTWVkaWFTZXJ2aWNlMl8wL29wLWdlbmVyYXRlS2V5L3YtMi4zP3EHWCYAAABodHRw'
        b'Oi8veW91cnNwb3J0c2luaGQuY29tL21sYi9nZXRfa2V5L3EIhnEJWDMAAABodHRwczovL2'
        b'tleS1zZXJ2aWNlLnRvdHN1a28udHYva2V5LXNlcnZpY2Uva2V5L2tleT9xClgmAAAAaHR0'
        b'cDovL3lvdXJzcG9ydHNpbmhkLmNvbS92dWUvZ2V0X2tleS9xC4ZxDGUu'))

    def uri(self, uri):
        uri = super(YSIHDM3U8Parser, self).uri(uri)
        if uri:
            for args in self.replace_pairs:
                uri = uri.replace(*args)
        return uri


class YourSportsInHD(Plugin):
    @classmethod
    def can_handle_url(cls, url):
        return _url_re.match(url)

    def _get_streams(self):
        res = http.get(self.url)
        m3u8_link = _m3u8_re.search(res.text)

        hls_url = m3u8_link.group("url")

        if hls_url:
            self.logger.debug("HLS URL: {0}", hls_url)
            hls_url = "http://cors2.yoursportsinhd.com/" + hls_url
            for q, s in HLSStream.parse_variant_playlist(self.session, hls_url, parser=YSIHDM3U8Parser,
                                                         headers={"Origin": "http://yoursportsinhd.com"}).items():
                yield q, s

__plugin__ = YourSportsInHD
