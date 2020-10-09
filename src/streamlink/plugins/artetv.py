"""Plugin for Arte.tv, bi-lingual art and culture channel."""

import logging
import re
from operator import itemgetter

from streamlink.plugin import Plugin, PluginArguments, PluginArgument
from streamlink.plugin.api import validate
from streamlink.stream import HLSStream

log = logging.getLogger(__name__)


class ArteTV(Plugin):
    arguments = PluginArguments(
        PluginArgument(
            "available-variants",
            action="store_true",
            help="List the available stream variants"
        ),
        PluginArgument(
            "variant",
            metavar="VARIANT",
            default=1,
            type=int,
            help="Request a specific stream variant, use the number returned by --artetv-available-variants"
        )
    )

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
                        "versionLibelle": validate.text,
                        "versionProg": int
                    },
                },
            )
        }
    })

    JSON_VOD_URL = "https://api.arte.tv/api/player/v1/config/{0}/{1}?platform=ARTE_NEXT"
    JSON_LIVE_URL = "https://api.arte.tv/api/player/v1/livestream/{0}"

    @classmethod
    def can_handle_url(cls, url):
        return self._url_re.match(url)

    def get_variants(self, video_id, language):
        videos = self.api_call(video_id, language)
        if videos:
            return dict([(stream["versionProg"], stream["versionLibelle"]) for stream in videos])
        else:
            return {}

    def list_variants(self, video_id, language, program_version=1):
        versions = self.get_variants(video_id, language)
        if versions:
            log.info("This stream is available in the following variants")
            for pver, label in sorted(versions.items(), key=itemgetter(0)):
                log.info("{0: 4d}: {1}{2}".format(pver, label, " [DEFAULT]" if program_version == pver else ""))

    def api_call(self, video_id, language):
        if video_id is None:
            json_url = self.JSON_LIVE_URL.format(language)
        else:
            json_url = self.JSON_VOD_URL.format(language, video_id)

        res = self.session.http.get(json_url)
        video = self.session.http.json(res, schema=self._video_schema)

        if not video["videoJsonPlayer"]["VSR"]:
            return

        return video["videoJsonPlayer"]["VSR"].values()

    def _create_stream(self, video_id, language, program_version=1):
        videos = self.api_call(video_id, language)
        variants = self.get_variants(video_id, language)
        if program_version in variants:
            log.debug("Selecting `{0}` variant".format(variants.get(program_version)))
        else:
            log.error("Unknown program variant: {0}".format(program_version))
            return
        for video in videos:
            if video["mediaType"] == "hls":
                if video["versionProg"] == program_version:
                    try:
                        streams = HLSStream.parse_variant_playlist(self.session, video["url"])
                        for s in streams.items():
                            yield s
                    except IOError as err:
                        log.error("Failed to extract HLS streams: {0}", err)

    def _get_streams(self):
        match = self._url_re.match(self.url)
        language = match.group('language')
        video_id = match.group('video_id')

        if self.get_option("available-variants"):
            self.list_variants(video_id, language, self.get_option("variant"))
        else:
            return self._create_stream(video_id, language, self.get_option("variant"))


__plugin__ = ArteTV
