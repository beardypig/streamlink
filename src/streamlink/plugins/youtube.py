from __future__ import unicode_literals

import argparse
import logging
import re

from streamlink.compat import parse_qsl
from streamlink.plugin import Plugin, PluginError, PluginArguments, PluginArgument
from streamlink.plugin.api import http, validate, useragents
from streamlink.plugin.api.utils import parse_query, itertags
from streamlink.stream import HTTPStream, HLSStream
from streamlink.stream.ffmpegmux import MuxedStream
from streamlink.utils import parse_json, search_dict

log = logging.getLogger(__name__)


def parse_stream_map(stream_map):
    if not stream_map:
        return []

    return [parse_query(s) for s in stream_map.split(",")]


def parse_fmt_list(formatsmap):
    formats = {}
    if not formatsmap:
        return formats

    for format in formatsmap.split(","):
        s = format.split("/")
        (w, h) = s[1].split("x")
        formats[int(s[0])] = "{0}p".format(h)

    return formats


_config_schema = validate.Schema(
    {
        validate.optional("fmt_list"): validate.all(
            validate.text,
            validate.transform(parse_fmt_list)
        ),
        validate.optional("url_encoded_fmt_stream_map"): validate.all(
            validate.text,
            validate.transform(parse_stream_map),
            [{
                "itag": validate.all(
                    validate.text,
                    validate.transform(int)
                ),
                "quality": validate.text,
                "url": validate.url(scheme="http"),
                validate.optional("s"): validate.text,
                validate.optional("stereo3d"): validate.all(
                    validate.text,
                    validate.transform(int),
                    validate.transform(bool)
                ),
            }]
        ),
        validate.optional("adaptive_fmts"): validate.all(
            validate.text,
            validate.transform(parse_stream_map),
            [{
                validate.optional("s"): validate.text,
                "type": validate.all(
                    validate.text,
                    validate.transform(lambda t: t.split(";")[0].split("/")),
                    [validate.text, validate.text]
                ),
                "url": validate.all(
                    validate.url(scheme="http")
                )
            }]
        ),
        validate.optional("hlsvp"): validate.text,
        validate.optional("live_playback"): validate.transform(bool),
        validate.optional("reason"): validate.all(validate.text, validate.transform(lambda x: x.decode("utf8"))),
        validate.optional("livestream"): validate.text,
        validate.optional("live_playback"): validate.text,
        "status": validate.text
    }
)
_search_schema = validate.Schema(
    {
        "items": [{
            "id": {
                "videoId": validate.text
            }
        }]
    },
    validate.get("items")
)

_ytdata_re = re.compile(r'window\["ytInitialData"\]\s*=\s*({.*?});', re.DOTALL)
_url_re = re.compile(r"""
    http(s)?://(\w+\.)?youtube.com
    (?:
        (?:
            /(watch.+v=|embed/|v/)
            (?P<video_id>[0-9A-z_-]{11})
        )
        |
        (?:
            /(user|channel)/(?P<user>[^/?]+)
        )
        |
        (?:
            /(c/)?(?P<liveChannel>[^/?]+)/live
        )
    )
""", re.VERBOSE)


class YouTube(Plugin):
    _video_info_url = "https://youtube.com/get_video_info"
    adp_video = {
        137: "1080p",
        303: "1080p60",  # HFR
        299: "1080p60",  # HFR
        264: "1440p",
        308: "1440p60",  # HFR
        266: "2160p",
        315: "2160p60",  # HFR
        138: "2160p",
        302: "720p60",  # HFR
    }
    adp_audio = {
        140: 128,
        141: 256,
        171: 128,
        249: 48,
        250: 64,
        251: 160,
        256: 256,
        258: 258,
    }

    arguments = PluginArguments(
        PluginArgument(
            "api-key",
            sensitive=True,
            help=argparse.SUPPRESS  # no longer used
        )
    )

    @classmethod
    def can_handle_url(cls, url):
        return _url_re.match(url)

    @classmethod
    def stream_weight(cls, stream):
        match_3d = re.match(r"(\w+)_3d", stream)
        match_hfr = re.match(r"(\d+p)(\d+)", stream)
        if match_3d:
            weight, group = Plugin.stream_weight(match_3d.group(1))
            weight -= 1
            group = "youtube_3d"
        elif match_hfr:
            weight, group = Plugin.stream_weight(match_hfr.group(1))
            weight += 1
            group = "high_frame_rate"
        else:
            weight, group = Plugin.stream_weight(stream)

        return weight, group

    def _create_adaptive_streams(self, info, streams, protected):
        adaptive_streams = {}
        best_audio_itag = None

        # Extract audio streams from the DASH format list
        for stream_info in info.get("adaptive_fmts", []):
            if stream_info.get("s"):
                protected = True
                continue

            stream_params = dict(parse_qsl(stream_info["url"]))
            if "itag" not in stream_params:
                continue
            itag = int(stream_params["itag"])
            # extract any high quality streams only available in adaptive formats
            adaptive_streams[itag] = stream_info["url"]

            stream_type, stream_format = stream_info["type"]
            if stream_type == "audio":
                stream = HTTPStream(self.session, stream_info["url"])
                name = "audio_{0}".format(stream_format)
                streams[name] = stream

                # find the best quality audio stream m4a, opus or vorbis
                if best_audio_itag is None or self.adp_audio[itag] > self.adp_audio[best_audio_itag]:
                    best_audio_itag = itag

        if best_audio_itag and adaptive_streams and MuxedStream.is_usable(self.session):
            aurl = adaptive_streams[best_audio_itag]
            for itag, name in self.adp_video.items():
                if itag in adaptive_streams:
                    vurl = adaptive_streams[itag]
                    log.debug("MuxedStream: v {video} a {audio} = {name}".format(
                        audio=best_audio_itag,
                        name=name,
                        video=itag,
                    ))
                    streams[name] = MuxedStream(self.session,
                                                HTTPStream(self.session, vurl),
                                                HTTPStream(self.session, aurl))

        return streams, protected

    def _find_video_id(self, url):
        res = http.get(url)

        for link in itertags(res.text, 'link'):
            if link.attributes.get("rel") == "canonical":
                canon_link = link.attributes.get("href")
                if canon_link != url:
                    log.debug("Re-directing to canonical URL: {0}".format(canon_link))
                    return self._find_video_id(canon_link)

        datam = _ytdata_re.search(res.text)
        if datam:
            data = parse_json(datam.group(1))
            # find the videoRenderer object, where there is a LVE NOW badge
            for vid_ep in search_dict(data, 'currentVideoEndpoint'):
                video_id = vid_ep.get("watchEndpoint", {}).get("videoId")
                if video_id:
                    return video_id


    def _get_stream_info(self, video_id):
        # normal
        _params_1 = {"el": "detailpage"}
        # age restricted
        _params_2 = {"el": "embedded"}
        # embedded restricted
        _params_3 = {"eurl": "https://youtube.googleapis.com/v/{0}".format(video_id)}

        count = 0
        info_parsed = None
        for _params in (_params_1, _params_2, _params_3):
            count += 1
            params = {"video_id": video_id}
            params.update(_params)

            res = http.get(self._video_info_url, params=params)
            info_parsed = parse_query(res.content, name="config", schema=_config_schema)
            if info_parsed.get("status") == "fail":
                log.debug("get_video_info - {0}: {1}".format(
                    count, info_parsed.get("reason"))
                )
                continue
            log.debug("get_video_info - {0}: Found data".format(count))
            break

        return info_parsed

    def _get_streams(self):
        http.headers.update({'User-Agent': useragents.CHROME})
        is_live = False

        video_id = self._find_video_id(self.url)
        if not video_id:
            log.error("Cloud not find a video on this page")
            return

        info = self._get_stream_info(video_id)
        if info and info.get("status") == "fail":
            log.error("Could not get video info: {0}".format(info.get("reason")))
        elif not info:
            log.error("Could not get video info")

        if info.get("livestream") == '1' or info.get("live_playback") == '1':
            log.debug("This video is live.")
            is_live = True

        formats = info.get("fmt_list")
        streams = {}
        protected = False
        for stream_info in info.get("url_encoded_fmt_stream_map", []):
            if stream_info.get("s"):
                protected = True
                continue

            stream = HTTPStream(self.session, stream_info["url"])
            name = formats.get(stream_info["itag"]) or stream_info["quality"]

            if stream_info.get("stereo3d"):
                name += "_3d"

            streams[name] = stream

        if not is_live:
            streams, protected = self._create_adaptive_streams(info, streams, protected)

        hls_playlist = info.get("hlsvp")
        if hls_playlist:
            try:
                hls_streams = HLSStream.parse_variant_playlist(
                    self.session, hls_playlist, namekey="pixels"
                )
                streams.update(hls_streams)
            except IOError as err:
                log.warning("Failed to extract HLS streams: {0}", err)

        if not streams and protected:
            raise PluginError("This plugin does not support protected videos, "
                              "try youtube-dl instead")

        return streams


__plugin__ = YouTube
