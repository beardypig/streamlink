import logging
import re
import struct
from collections import namedtuple

from streamlink.buffers import RingBuffer
from streamlink.exceptions import StreamError
from streamlink.stream import hls_playlist
from streamlink.stream.ffmpegmux import FFMPEGMuxer, MuxedStream
from streamlink.stream.http import HTTPStream
from streamlink.stream.segmented import (SegmentGenerator,
                                         HTTPSegmentProcessor,
                                         HTTPSegment,
                                         RangedHTTPSegment,
                                         AESEncryptedHTTPSegment,
                                         ManifestBasedSegmentGenerator)

log = logging.getLogger(__name__)
Sequence = namedtuple("Sequence", "num segment")


def num_to_iv(n):
    return struct.pack(">8xq", n)


class HLSSegmentGenerator(ManifestBasedSegmentGenerator):
    def __init__(self, http, url, live_edge=3, start_offset=0, duration=None, reload_attempts=1, live_restart=False,
                 ignore_names=None, **request_params):
        SegmentGenerator.__init__(self)

        self.http = http
        self.url = url

        self.playlist = None
        self.playlist_changed = False
        self.playlist_end = None
        self.playlist_sequence = -1
        self.playlist_sequences = []
        self.playlist_reload_time = self.DEFAULT_RELOAD_TIME

        self.live_edge = live_edge
        self.playlist_reload_retries = reload_attempts
        self.duration_offset_start = start_offset
        self.duration_limit = duration
        self.live_restart = live_restart
        self.ignore_names = ignore_names
        self.request_params = request_params
        self.key_uri = None
        self.key_data = b""

        if self.ignore_names:
            # creates a regex from a list of segment names,
            # this will be used to ignore segments.
            self.ignore_names = list(set(self.ignore_names))
            self.ignore_names = "|".join(list(map(re.escape, self.ignore_names)))
            self.ignore_names_re = re.compile(r"(?:{blacklist})\.ts".format(blacklist=self.ignore_names), re.IGNORECASE)

        if self.playlist_end is None:
            if self.duration_offset_start > 0:
                log.debug(
                    "Time offsets negative for live streams, skipping back {0} seconds",
                    self.duration_offset_start)
            # live playlist, force offset durations back to None
            self.duration_offset_start = -self.duration_offset_start

        if self.duration_offset_start != 0:
            self.playlist_sequence = self.duration_to_sequence(
                self.duration_offset_start, self.playlist_sequences)

        if self.playlist_sequences:
            log.debug("First Sequence: {0}; Last Sequence: {1}",
                      self.playlist_sequences[0].num,
                      self.playlist_sequences[-1].num)
            log.debug(
                "Start offset: {0}; Duration: {1}; Start Sequence: {2}; End Sequence: {3}",
                self.duration_offset_start, self.duration_limit,
                self.playlist_sequence, self.playlist_end)

    def update_reload_time(self, changed):
        last_sequence = self.playlist_sequences and self.playlist_sequences[-1]

        segment_duration = (self.playlist.target_duration or last_sequence.segment.duration)

        if not changed:
            # half the reload wait time if the playlist doesn't change
            self.playlist_reload_time /= 2.0
        elif segment_duration:  # this should be the case after the first reload
            """
            According to the HLS spec the playlist shouldn't be reloaded more frequently than once per TARGET DURATION.
            If we are on a very low live edge, we want to reload it slightly more frequently, to make sure we see playlist changes.
            If we are on a regular live edge (for example, 3), we can reload a bit slower - 80% of 2 x TARGET DURATION should
            ensure we see changes to the playlist in time.
            """
            self.playlist_reload_time = max(segment_duration * (self.live_edge - 1), segment_duration) * 0.8
        else:
            # if there are no segments, and the playlist has not changed fall back to the default
            self.playlist_reload_time = self.DEFAULT_RELOAD_TIME

        log.debug("Updated playlist refresh time to {0:.2f}s".format(self.playlist_reload_time))

    def parse_manifest(self, content, url, **kwargs):
        return hls_playlist.load(content, url, **kwargs)

    def reload_manifest(self):
        if not self.closed:
            log.debug("Reloading playlist")
            res = self.http.get(self.url,
                                exception=StreamError,
                                retries=self.playlist_reload_retries,
                                # set the timeout to half the playlist reload time, but not less than 1 second
                                timeout=max(1.0, self.playlist_reload_time / 2.0),
                                **self.request_params)
            try:
                self.playlist = self.parse_manifest(res.text, res.url)
            except ValueError as err:
                raise StreamError(err)

            if self.playlist.is_master:
                raise StreamError("Attempted to play a variant playlist, use "
                                  "'hls://{0}' instead".format(self.url))

            if self.playlist.iframes_only:
                raise StreamError("Streams containing I-frames only is not playable")

            media_sequence = self.playlist.media_sequence or 0
            sequences = [Sequence(media_sequence + i, s)
                         for i, s in enumerate(self.playlist.segments)]

            changed = False
            if sequences:
                changed = self.process_sequences(self.playlist, sequences)

            self.update_reload_time(changed)

    def process_sequences(self, playlist, sequences):
        first_sequence, last_sequence = sequences[0], sequences[-1]

        if first_sequence.segment.key and first_sequence.segment.key.method != "NONE":
            log.debug("Segments in this playlist are encrypted")

        self.playlist_changed = ([s.num for s in self.playlist_sequences] !=
                                 [s.num for s in sequences])
        self.playlist_sequences = sequences

        if playlist.is_endlist:
            self.playlist_end = last_sequence.num

        if self.playlist_sequence < 0:
            if self.playlist_end is None and not self.live_restart:
                edge_index = -(min(len(sequences), max(int(self.live_edge), 1)))
                edge_sequence = sequences[edge_index]
                self.playlist_sequence = edge_sequence.num
            else:
                self.playlist_sequence = first_sequence.num

        return self.playlist_changed

    def valid_sequence(self, sequence):
        return self.ignore_names and self.ignore_names_re.search(sequence.segment.uri)

    def duration_to_sequence(self, duration, sequences):
        d = 0
        default = -1

        sequences_order = sequences if duration >= 0 else reversed(sequences)

        for sequence in sequences_order:
            if d >= abs(duration):
                return sequence.num
            d += sequence.segment.duration
            default = sequence.num

        # could not skip far enough, so return the default
        return default

    def _future_sequence(self, sequence):
        return sequence.num >= self.playlist_sequence

    def __iter__(self):
        total_duration = 0

        self.reload_manifest()

        while not self.closed:
            for sequence in filter(self._future_sequence, self.playlist_sequences):
                # skip ignored segment names
                if self.valid_sequence(sequence):
                    log.debug("Skipping segment {0}".format(sequence.num))
                    continue

                log.debug("Adding segment {0} to queue", sequence.num)
                key = sequence.segment.key

                if key and key.method != "NONE":
                    if key.method != "AES-128":
                        raise StreamError("Unable to decrypt cipher {0}", key.method)

                    if not key.uri:
                        raise StreamError("Missing URI to decryption key")

                    if self.key_uri != key.uri:
                        res = self.http.get(key.uri, exception=StreamError,
                                            retries=self.playlist_reload_retries,
                                            **self.request_params)
                        self.key_data = res.content
                        self.key_uri = key.uri

                    iv = key.iv or num_to_iv(sequence.num)

                    # Pad IV if needed
                    iv = b"\x00" * (16 - len(iv)) + iv

                    yield AESEncryptedHTTPSegment(sequence.segment.uri,
                                                  self.key_data, iv,
                                                  **self.request_params)

                elif sequence.segment.byterange:
                    yield RangedHTTPSegment(sequence.segment.uri,
                                            offset=sequence.segment.byterange.offset,
                                            length=sequence.segment.byterange.range,
                                            **self.request_params)
                else:
                    yield HTTPSegment(sequence.segment.uri, **self.request_params)

                total_duration += sequence.segment.duration
                if self.duration_limit and total_duration >= self.duration_limit:
                    log.info("Stopping stream early after {0}".format(self.duration_limit))
                    return

                # End of stream
                stream_end = self.playlist_end and sequence.num >= self.playlist_end
                if self.closed or stream_end:
                    return

                self.playlist_sequence = sequence.num + 1

            if self.wait(self.playlist_reload_time):
                try:
                    self.reload_manifest()
                except StreamError as err:
                    log.warning("Failed to reload playlist: {0}", err)


class HLSStream(HTTPStream):
    """Implementation of the Apple HTTP Live Streaming protocol

    *Attributes:*

    - :attr:`url` The URL to the HLS playlist.
    - :attr:`args` A :class:`dict` containing keyword arguments passed
      to :meth:`requests.request`, such as headers and cookies.

    """

    __shortname__ = "hls"

    def __init__(self, session_, url, force_restart=False, start_offset=0,
                 duration=None, **args):
        HTTPStream.__init__(self, session_, url, **args)
        self.force_restart = force_restart
        self.start_offset = start_offset
        self.duration = duration

    def __repr__(self):
        return "<HLSStream({0!r})>".format(self.url)

    def __json__(self):
        json = HTTPStream.__json__(self)

        # Pretty sure HLS is GET only.
        del json["method"]
        del json["body"]

        return json

    def open(self):
        live_edge = self.session.get_option("hls-live-edge")
        reload_retries = self.session.get_option("hls-playlist-reload-attempts")
        duration_offset_start = int(self.start_offset + (self.session.get_option("hls-start-offset") or 0))
        duration_limit = self.duration or (int(self.session.get_option("hls-duration") or 0) or None)
        live_restart = self.force_restart or self.session.get_option("hls-live-restart")
        ignore_names = self.session.get_option("hls-segment-ignore-names")

        generator = HLSSegmentGenerator(self.session.http,
                                        live_edge=live_edge,
                                        start_offset=duration_offset_start,
                                        duration=duration_limit,
                                        reload_attempts=reload_retries,
                                        live_restart=live_restart,
                                        ignore_names=ignore_names,
                                        **self.args)
        buffer = RingBuffer(self.session.get_option("ringbuffer-size"))
        proc = HTTPSegmentProcessor(self.session.http, generator, buffer)
        return proc.open()

    @classmethod
    def _get_variant_playlist(cls, res):
        return hls_playlist.load(res.text, base_uri=res.url)

    @classmethod
    def parse_variant_playlist(cls, session_, url, name_key="name",
                               name_prefix="", check_streams=False,
                               force_restart=False, name_fmt=None,
                               start_offset=0, duration=None,
                               **request_params):
        """Attempts to parse a variant playlist and return its streams.

        :param url: The URL of the variant playlist.
        :param name_key: Prefer to use this key as stream name, valid keys are:
                         name, pixels, bitrate.
        :param name_prefix: Add this prefix to the stream names.
        :param check_streams: Only allow streams that are accessible.
        :param force_restart: Start at the first segment even for a live stream
        :param name_fmt: A format string for the name, allowed format keys are
                         name, pixels, bitrate.
        """
        locale = session_.localization
        # Backwards compatibility with "namekey" and "nameprefix" params.
        name_key = request_params.pop("namekey", name_key)
        name_prefix = request_params.pop("nameprefix", name_prefix)
        audio_select = session_.options.get("hls-audio-select") or []

        res = session_.http.get(url, exception=IOError, **request_params)

        try:
            parser = cls._get_variant_playlist(res)
        except ValueError as err:
            raise IOError("Failed to parse playlist: {0}".format(err))

        streams = {}
        for playlist in filter(lambda p: not p.is_iframe, parser.playlists):
            names = dict(name=None, pixels=None, bitrate=None)
            audio_streams = []
            fallback_audio = []
            default_audio = []
            preferred_audio = []
            for media in playlist.media:
                if media.type == "VIDEO" and media.name:
                    names["name"] = media.name
                elif media.type == "AUDIO":
                    audio_streams.append(media)
            for media in audio_streams:
                # Media without a uri is not relevant as external audio
                if not media.uri:
                    continue

                if not fallback_audio and media.default:
                    fallback_audio = [media]

                # if the media is "audoselect" and it better matches the users preferences, use that
                # instead of default
                if not default_audio and (media.autoselect and locale.equivalent(
                        language=media.language)):
                    default_audio = [media]

                # select the first audio stream that matches the users explict language selection
                if (('*' in audio_select or media.language in audio_select or media.name in audio_select)
                        or ((not preferred_audio or media.default) and locale.explicit and locale.equivalent(
                            language=media.language))):
                    preferred_audio.append(media)

            # final fallback on the first audio stream listed
            fallback_audio = fallback_audio or (len(audio_streams) and
                                                audio_streams[0].uri and [
                                                    audio_streams[0]])

            if playlist.stream_info.resolution:
                width, height = playlist.stream_info.resolution
                names["pixels"] = "{0}p".format(height)

            if playlist.stream_info.bandwidth:
                bw = playlist.stream_info.bandwidth

                if bw >= 1000:
                    names["bitrate"] = "{0}k".format(int(bw / 1000.0))
                else:
                    names["bitrate"] = "{0}k".format(bw / 1000.0)

            if name_fmt:
                stream_name = name_fmt.format(**names)
            else:
                stream_name = (
                    names.get(name_key)
                    or names.get("name")
                    or names.get("pixels")
                    or names.get("bitrate")
                )

            if not stream_name:
                continue
            if name_prefix:
                stream_name = "{0}{1}".format(name_prefix, stream_name)

            if stream_name in streams:  # rename duplicate streams
                stream_name = "{0}_alt".format(stream_name)
                num_alts = len(list(
                    filter(lambda n: n.startswith(stream_name), streams.keys())))

                # We shouldn't need more than 2 alt streams
                if num_alts >= 2:
                    continue
                elif num_alts > 0:
                    stream_name = "{0}{1}".format(stream_name, num_alts + 1)

            if check_streams:
                try:
                    session_.http.get(playlist.uri, **request_params)
                except KeyboardInterrupt:
                    raise
                except Exception:
                    continue

            external_audio = preferred_audio or default_audio or fallback_audio

            if external_audio and FFMPEGMuxer.is_usable(session_):
                external_audio_msg = u", ".join([
                    u"(language={0}, name={1})".format(x.language,
                                                      (x.name or "N/A"))
                    for x in external_audio
                ])
                log.debug(u"Using external audio tracks for stream {0} {1}".format(
                          stream_name, external_audio_msg))

                stream = MuxedHLSStream(session_,
                                        video=playlist.uri,
                                        audio=[x.uri for x in external_audio if x.uri],
                                        force_restart=force_restart,
                                        start_offset=start_offset,
                                        duration=duration,
                                        hls_stream_class=cls,
                                        **request_params)
            else:
                stream = cls(session_,
                             playlist.uri,
                             force_restart=force_restart,
                             start_offset=start_offset,
                             duration=duration,
                             **request_params)
            streams[stream_name] = stream

        return streams


class MuxedHLSStream(MuxedStream):
    __shortname__ = "hls-multi"

    def __init__(self, session, video, audio, force_restart=False,
                 ffmpeg_options=None, hls_stream_class=HLSStream, **args):
        tracks = [video]
        maps = ["0:v?", "0:a?"]
        if audio:
            if isinstance(audio, list):
                tracks.extend(audio)
            else:
                tracks.append(audio)
        for i in range(1, len(tracks)):
            maps.append("{0}:a".format(i))
        substreams = map(lambda url: hls_stream_class(session, url, force_restart=force_restart, **args), tracks)
        ffmpeg_options = ffmpeg_options or {}

        super(MuxedHLSStream, self).__init__(session, *substreams, format="mpegts", maps=maps, **ffmpeg_options)
