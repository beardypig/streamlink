import re

from streamlink.plugin import Plugin
from streamlink.plugin.api import http
from streamlink.stream import HDSStream
from streamlink.stream import HLSStream
from streamlink.compat import urlparse, parse_qsl, urljoin, urlunparse


class WiizTV(Plugin):
    url_re = re.compile(r"https?://(?:www\.)?wiiz\.tv/(.*)")
    hls_src_re = re.compile(r'''source\s+src="(.*?)"\s+type="application/x-mpegurl"''')
    embed_re = re.compile(r'''iframe[^>]+src\s*=\s*"([^"]*?embed\.html[^"]*?)"''', re.DOTALL)

    @classmethod
    def can_handle_url(cls, url):
        return cls.url_re.match(url) is not None

    def _get_hls_streams(self, page):
        m = self.hls_src_re.search(page)
        if m:
            for s in HLSStream.parse_variant_playlist(self.session, m.group(1).strip()).items():
                yield s

    def _get_embed_url(self, page):
        m = self.embed_re.search(page)
        if m:
            return m.group(1).strip()

    def _get_embed_hls_streams(self, page):
        self.logger.debug("Looking for embedded HLS streams")
        embed_url = self._get_embed_url(page)
        if embed_url:
            parsed_url = urlparse(embed_url)
            params = dict(parse_qsl(parsed_url.query))

            if "from" in params and "duration" in params:
                path = "/index-{0}-{1}.m3u8".format(params["from"], params["duration"])
            elif "from" in params:
                path = "timeshift_abs-{0}.m3u8".format(params["from"])
            elif "tracks" in params:
                path = "tracks-{0}/index.m3u8".format(params["tracks"])
            else:
                path = "index.m3u8"

            hls_url = urlunparse(parsed_url._replace(path=urljoin(parsed_url.path, path)))

            for s in HLSStream.parse_variant_playlist(self.session, hls_url).items():
                yield s

    def _get_embed_hds_streams(self, page):
        self.logger.debug("Looking for embedded HDS streams")
        embed_url = self._get_embed_url(page)
        if embed_url:
            parsed_url = urlparse(embed_url)
            params = dict(parse_qsl(parsed_url.query))

            if "from" in params:
                path = "/archive/{0}/{1}/manifest.f4m".format(params["from"], params.get("duration", "now"))
            else:
                path = "manifest.f4m"

            hds_url = urlunparse(parsed_url._replace(path=urljoin(parsed_url.path, path)))

            for s in HDSStream.parse_manifest(self.session, hds_url).items():
                yield s

    def _get_streams(self):
        res = http.get(self.url)
        page = res.text

        for s in self._get_hls_streams(page):
            yield s
        for s in self._get_embed_hds_streams(page):
            yield s
        for s in self._get_embed_hls_streams(page):
            yield s


__plugin__ = WiizTV
