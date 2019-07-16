import datetime
import itertools
import logging
import os.path

import requests

from streamlink import StreamError, PluginError
from streamlink.buffers import RingBuffer
from streamlink.compat import urlparse, urlunparse
from streamlink.stream.dash_manifest import MPD, sleep_until, utc, freeze_timeline
from streamlink.stream.ffmpegmux import FFMPEGMuxer
from streamlink.stream.http import valid_args, normalize_key
from streamlink.stream.segmented import SegmentGenerator, HTTPSegmentProcessor, ManifestBasedSegmentGenerator, RangedHTTPSegment, HTTPSegment
from streamlink.stream.stream import Stream
from streamlink.utils import parse_xml
from streamlink.utils.l10n import Language

log = logging.getLogger(__name__)


class DASHSegmentGenerator(ManifestBasedSegmentGenerator):
    def __init__(self, http, mpd, representation_id, mime_type, live_edge=3, period_index=0, **request_params):
        SegmentGenerator.__init__(self)

        self.http = http
        self.mpd = mpd
        self.representation_id = representation_id
        self.mime_type = mime_type
        self.live_edge = live_edge
        self.period_index = period_index
        self.request_params = request_params

    def parse_manifest(self, content, url, base_url=None, timelines=None, **kwargs):
        return MPD(parse_xml(content, ignore_ns=True),
                   base_url=base_url,
                   url=url,
                   timelines=timelines)

    def reload_manifest(self):
        if not self.closed and self.mpd.type == "dynamic":
            log.debug("Reloading manifest ({0}:{1})".format(self.representation_id, self.mime_type))
            res = self.http.get(self.mpd.url, exception=StreamError)

            new_mpd = self.parse_manifest(res.text, self.mpd.url, base_url=self.mpd.base_url, timelines=self.mpd.timelines)

            new_rep = new_mpd.find_representation(self.representation_id, self.mime_type, period=self.period_index)
            with freeze_timeline(new_mpd):
                changed = len(list(itertools.islice(new_rep.segments(), 1))) > 0

            if changed:
                self.mpd = new_mpd

            return changed
        return False

    def update_reload_time(self, changed):
        reload_wait = max(self.mpd.minimumUpdatePeriod.total_seconds(),
                          self.mpd.periods[self.period_index].duration.total_seconds()) or self.DEFAULT_RELOAD_TIME
        if not changed:
            self.manifest_reload_time /= 2.0
        else:
            self.manifest_reload_time = max(reload_wait * (self.live_edge - 1), reload_wait) * 0.8

    def __iter__(self):
        init = True
        while not self.closed:
            representation = self.mpd.find_representation(self.representation_id, self.mime_type, self.period_index)
            if representation:
                for segment in representation.segments(init=init):
                    init = False

                    if self.closed:
                        break

                    now = datetime.datetime.now(tz=utc)
                    if segment.available_at > now:
                        time_to_wait = (segment.available_at - now).total_seconds()
                        fname = os.path.basename(urlparse(segment.url).path)
                        log.debug("Waiting for segment: {fname} ({wait:.01f}s)".format(fname=fname, wait=time_to_wait))
                        sleep_until(segment.available_at)
                    if segment.range:
                        yield RangedHTTPSegment(segment.url,
                                                offset=segment.range.offset,
                                                length=segment.range.length,
                                                **self.request_params)
                    else:
                        yield HTTPSegment(segment.url, **self.request_params)
            if self.mpd.type == "dynamic":
                changed = self.reload_manifest()
                self.update_reload_time(changed)
            else:
                break


class DASHStream(Stream):
    __shortname__ = "dash"

    def __init__(self,
                 session,
                 mpd,
                 video_representation=None,
                 audio_representation=None,
                 period=0,
                 **args):
        super(DASHStream, self).__init__(session)
        self.mpd = mpd
        self.video_representation = video_representation
        self.audio_representation = audio_representation
        self.period = period
        self.args = args

    def __json__(self):
        req = requests.Request(method="GET", url=self.mpd.url, **valid_args(self.args))
        req = req.prepare()

        headers = dict(map(normalize_key, req.headers.items()))
        return dict(type=type(self).shortname(), url=req.url, headers=headers)

    @classmethod
    def parse_manifest(cls, session, url_or_manifest, **args):
        """
        Attempt to parse a DASH manifest file and return its streams

        :param session: Streamlink session instance
        :param url_or_manifest: URL of the manifest file or an XML manifest string
        :return: a dict of name -> DASHStream instances
        """
        ret = {}

        if url_or_manifest.startswith('<?xml'):
            mpd = MPD(parse_xml(url_or_manifest, ignore_ns=True))
        else:
            res = session.http.get(url_or_manifest, **args)
            url = res.url

            urlp = list(urlparse(url))
            urlp[2], _ = urlp[2].rsplit("/", 1)

            mpd = MPD(session.http.xml(res, ignore_ns=True), base_url=urlunparse(urlp), url=url)

        video, audio = [], []

        # Search for suitable video and audio representations
        for aset in mpd.periods[0].adaptationSets:
            if aset.contentProtection:
                raise PluginError("{} is protected by DRM".format(url))
            for rep in aset.representations:
                if rep.mimeType.startswith("video"):
                    video.append(rep)
                elif rep.mimeType.startswith("audio"):
                    audio.append(rep)

        if not video:
            video = [None]

        if not audio:
            audio = [None]

        locale = session.localization
        locale_lang = locale.language
        lang = None
        available_languages = set()

        # if the locale is explicitly set, prefer that language over others
        for aud in audio:
            if aud and aud.lang:
                available_languages.add(aud.lang)
                try:
                    if locale.explicit and aud.lang and Language.get(aud.lang) == locale_lang:
                        lang = aud.lang
                except LookupError:
                    continue

        if not lang:
            # filter by the first language that appears
            lang = audio[0] and audio[0].lang

        log.debug("Available languages for DASH audio streams: {0} (using: {1})".format(
            ", ".join(available_languages) or "NONE",
            lang or "n/a"
        ))

        # if the language is given by the stream, filter out other languages that do not match
        if len(available_languages) > 1:
            audio = list(filter(lambda a: a.lang is None or a.lang == lang, audio))

        for vid, aud in itertools.product(video, audio):
            stream = DASHStream(session, mpd, vid, aud, **args)
            stream_name = []

            if vid:
                stream_name.append("{:0.0f}{}".format(vid.height or vid.bandwidth_rounded, "p" if vid.height else "k"))
            if audio and len(audio) > 1:
                stream_name.append("a{:0.0f}k".format(aud.bandwidth))
            ret['+'.join(stream_name)] = stream
        return ret

    def open(self):
        live_edge = self.session.get_option("dash-live-edge")
        reload_retries = self.session.get_option("dash-playlist-reload-attempts")

        video = None
        audio = None

        if self.video_representation:
            video_segment_generator = DASHSegmentGenerator(self.session.http,
                                                           self.mpd,
                                                           self.video_representation.id,
                                                           self.video_representation.mimeType,
                                                           live_edge=live_edge,
                                                           reload_attempts=reload_retries,
                                                           **self.args)
            video_buffer = RingBuffer(self.session.get_option("ringbuffer-size"))
            video = HTTPSegmentProcessor(self.session.http, video_segment_generator, video_buffer)

        if self.audio_representation:
            audio_segment_generator = DASHSegmentGenerator(self.session.http,
                                                           self.mpd,
                                                           self.audio_representation.id,
                                                           self.audio_representation.mimeType,
                                                           live_edge=live_edge,
                                                           reload_attempts=reload_retries,
                                                           **self.args)
            audio_buffer = RingBuffer(self.session.get_option("ringbuffer-size"))
            audio = HTTPSegmentProcessor(self.session.http, audio_segment_generator, audio_buffer)

        if self.video_representation and self.audio_representation:
            return FFMPEGMuxer(self.session, video.open(), audio.open(), copyts=True).open()
        elif self.video_representation:
            return video.open()
        elif self.audio_representation:
            return audio.open()

    def to_url(self):
        return self.mpd.url
