import re

from streamlink.plugin import Plugin
from streamlink.plugin.api import http
from streamlink.plugin.api import useragents
from streamlink.plugin.api import validate
from streamlink.stream import HLSStream


class AllSporting(Plugin):
    url_re = re.compile(r"""
        https?://(?:www\.)?(sportgol1\.org|(1|2)streamking\.co)/(?P<channel>\w+)
    """, re.VERBOSE)
    iframe_re = re.compile(r"iframe .*?src=\"(?P<url>https?://.*?/player[^\"]+)\"", re.DOTALL)
    hls_file_re = re.compile(r"file: (?P<q>[\"'])(?P<url>http.+?m3u8.*?)(?P=q)")

    _get_url_schame = validate.any(
            None,
            validate.all(
                validate.get("url"),
                validate.url()
            )
        )
    iframe_schema = validate.Schema(validate.transform(iframe_re.search), _get_url_schame)
    hls_stream_schema = validate.Schema(validate.transform(hls_file_re.search), _get_url_schame)

    @classmethod
    def can_handle_url(cls, url):
        return cls.url_re.match(url) is not None

    def _get_streams(self):
        http.headers = {"User-Agent": useragents.CHROME, "Referer": self.url}

        iframe_url = http.get(self.url, schema=self.iframe_schema)
        if iframe_url:
            stream_url = http.get(iframe_url, schema=self.hls_stream_schema)
            if stream_url:
                yield "live", HLSStream(self.session, stream_url)
            else:
                self.logger.error("Could not find the stream URL")
        else:
            self.logger.error("Could not find the stream player")


__plugin__ = AllSporting
