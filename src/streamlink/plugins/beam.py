import re

from streamlink.plugin import Plugin
from streamlink.plugin.api import http, validate
from streamlink.stream import HLSStream
from streamlink.stream import RTMPStream

_url_re = re.compile(r"http(s)?://(\w+.)?beam.pro/(?P<channel>[^/]+)")

CHANNEL_INFO = "https://beam.pro/api/v1/channels/{0}"
CHANNEL_MANIFEST = "https://beam.pro/api/v1/channels/{0}/manifest.{1}"

_assets_schema = validate.Schema(
    validate.union({
        "base": validate.all(
            validate.xml_find("./head/meta"),
            validate.get("base"),
            validate.url(scheme="rtmp")
        ),
        "videos": validate.all(
            validate.xml_findall(".//video"),
            [
                validate.union({
                    "src": validate.all(
                        validate.get("src"),
                        validate.text
                    ),
                    "height": validate.all(
                        validate.get("height"),
                        validate.text,
                        validate.transform(int)
                    )
                })
            ]
        )
    })
)

_light2_schema = validate.Schema({validate.optional("hlsSrc"): validate.url()})


class Beam(Plugin):
    @classmethod
    def can_handle_url(cls, url):
        return _url_re.match(url)

    def _get_rtmp_streams(self, channel_id):
        res = http.get(CHANNEL_MANIFEST.format(channel_id, "smil"))
        assets = http.xml(res, schema=_assets_schema)
        for video in assets["videos"]:
            name = "{0}p".format(video["height"])
            stream = RTMPStream(self.session, {
                "rtmp": "{0}{1}".format(assets["base"], video["src"])
            })
            yield name, stream

    def _get_hls_streams(self, channel_id):
        # get the HLS manifest
        res = http.get(CHANNEL_MANIFEST.format(channel_id, "light2"))
        light2_data = http.json(res, schema=_light2_schema)

        # Output the HLSStreams
        if "hlsSrc" in light2_data:
            for s in HLSStream.parse_variant_playlist(self.session,
                                                      light2_data["hlsSrc"]).items():
                yield s

    def _get_streams(self):
        match = _url_re.match(self.url)
        channel = match.group("channel")
        res = http.get(CHANNEL_INFO.format(channel))
        channel_info = http.json(res)

        if not channel_info["online"]:
            return

        # Get the legacy RTMPStreams
        for s in self._get_rtmp_streams(channel_info["id"]):
            yield s

        # Get the HLStreams
        for s in self._get_hls_streams(channel_info["id"]):
            yield s

__plugin__ = Beam
