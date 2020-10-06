"""Plugin for Arte.tv, bi-lingual art and culture channel."""

import re
import logging
from itertools import chain

from streamlink.compat import urlparse
from streamlink.plugin import Plugin
from streamlink.plugin.api import validate
from streamlink.stream import HLSStream

JSON_VOD_URL = "https://api.arte.tv/api/player/v1/config/{0}/{1}?platform=ARTE_NEXT"
JSON_LIVE_URL = "https://api.arte.tv/api/player/v1/livestream/{0}"

_url_re = re.compile(r"""
    https?://(?:\w+\.)?arte\.tv/(?:guide/)?
    (?P<language>[a-z]{2})/
    (?:
        (?:videos/)?(?P<video_id>(?!RC\-|videos)[^/]+?)/.+ | # VOD
        (?:direct|live)        # Live TV
    )
""", re.VERBOSE)

_video_schema = validate.Schema({
    "videoJsonPlayer": {
        "VSR": validate.any(
            [],
            {
                validate.text: {
                    "height": int,
                    "mediaType": validate.text,
                    "url": validate.text,
                    "versionShortLibelle": validate.text
                },
            },
        )
    }
})
log = logging.getLogger(__name__)


class ArteTV(Plugin):
    @classmethod
    def can_handle_url(cls, url):
        return _url_re.match(url)

    def _create_stream(self, stream, language):
        stream_type = stream["mediaType"]
        stream_url = stream["url"]
        stream_language = stream["versionShortLibelle"]

        if language == "de":
            language = ["DE", "VOST-DE", "VA", "VOA", "Dt. Live"]
        elif language == "en":
            language = ["ANG", "VOST-ANG"]
        elif language == "es":
            language = ["ESP", "VOST-ESP"]
        elif language == "fr":
            language = ["FR", "VOST-FR", "VF", "VOF", "Frz. Live"]
        elif language == "pl":
            language = ["POL", "VOST-POL"]

        if stream_language in language:
            if stream_type == "hls" and urlparse(stream_url).path.endswith("m3u8"):
                try:
                    streams = HLSStream.parse_variant_playlist(self.session, stream_url)
                    for name, stream in streams.items():
                        yield name, stream
                except IOError as err:
                    log.error("Failed to extract HLS streams: {0}", err)

    def _get_streams(self):
        match = _url_re.match(self.url)
        language = match.group('language')
        video_id = match.group('video_id')
        if video_id is None:
            json_url = JSON_LIVE_URL.format(language)
        else:
            json_url = JSON_VOD_URL.format(language, video_id)
        res = self.session.http.get(json_url)
        video = self.session.http.json(res, schema=_video_schema)

        if not video["videoJsonPlayer"]["VSR"]:
            return

        vsr = video["videoJsonPlayer"]["VSR"].values()
        streams = (self._create_stream(stream, language) for stream in vsr)

        return chain.from_iterable(streams)


__plugin__ = ArteTV
