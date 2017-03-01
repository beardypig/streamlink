"""Plugin for NPO: Nederlandse Publieke Omroep

Supports:
   VODs: http://www.npo.nl/het-zandkasteel/POMS_S_NTR_059963
   Live: http://www.npo.nl/live/nederland-1
"""

import re

from streamlink.plugin import Plugin, PluginOptions
from streamlink.plugin.api import http
from streamlink.plugin.api import useragents
from streamlink.plugin.api import validate
from streamlink.stream import HLSStream


class NPO(Plugin):
    api_url = "http://ida.omroep.nl/app.php/{endpoint}"
    url_re = re.compile(r"http(s)?://(\w+\.)?npo.nl/")
    prid_re = re.compile(r'data(-alt)?-prid="(\w+)"')

    auth_schema = validate.Schema({"token": validate.text}, validate.get("token"))
    streams_schema = validate.Schema({
        "items": [
            [{
                "label": validate.text,
                "contentType": validate.text,
                "url": validate.url(),
                "format": validate.text
            }]
        ]
    }, validate.get("items"), validate.get(0))
    stream_info_schema = validate.Schema(validate.any(
        validate.url(),
        validate.all({"errorcode": 0, "url": validate.url()},
                     validate.get("url"))
    ))
    options = PluginOptions({
        "subtitles": False
    })

    @classmethod
    def can_handle_url(cls, url):
        return cls.url_re.match(url) is not None

    def __init__(self, url):
        super(NPO, self).__init__(url)
        self._token = None
        http.headers.update({"User-Agent": useragents.CHROME})

    def api_call(self, endpoint, schema=None, params=None):
        url = self.api_url.format(endpoint=endpoint)
        res = http.get(url, params=params)
        return http.json(res, schema=schema)

    @property
    def token(self):
        if not self._token:
            self._token = self.api_call("auth", schema=self.auth_schema)
        return self._token

    def _get_prid(self, subtitles=False):
        res = http.get(self.url)
        # Locate the asset id for the content on the page
        bprid = None
        for alt, prid in self.prid_re.findall(res.text):
            if alt and subtitles:
                bprid = prid
            elif bprid is None:
                bprid = prid
        return bprid

    def _get_streams(self):
        asset_id = self._get_prid(self.get_option("subtitles"))

        if asset_id:
            self.logger.debug("Found asset id: {0}", asset_id)
            streams = self.api_call(asset_id,
                                    params=dict(adaptive="yes",
                                                token=self.token),
                                    schema=self.streams_schema)

            for stream in streams:
                if stream["format"] == "hls":
                    # using type=json removes the javascript function wrapper
                    info_url = stream["url"].replace("type=jsonp", "type=json")

                    # find the actual stream URL
                    stream_url = http.json(http.get(info_url),
                                           schema=self.stream_info_schema)

                    for s in HLSStream.parse_variant_playlist(self.session, stream_url).items():
                        yield s


__plugin__ = NPO
