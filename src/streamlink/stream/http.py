import copy
import itertools
import logging
import math

import requests

from streamlink.buffers import RingBuffer
from streamlink.compat import getargspec
from streamlink.stream.segmented import SegmentGenerator, HTTPSegment, RangedHTTPSegment, \
    HTTPSegmentProcessor
from .stream import Stream

log = logging.getLogger(__name__)


def normalize_key(keyval):
    key, val = keyval
    key = hasattr(key, "decode") and key.decode("utf8", "ignore") or key

    return key, val


def valid_args(args):
    argspec = getargspec(requests.Request.__init__)

    return dict(filter(lambda kv: kv[0] in argspec.args, args.items()))


class RangeHTTPSegmentGenerator(SegmentGenerator):
    """
    Splits a single HTTP stream in to multiple chunks using Range requests
    """
    def __init__(self, http, url, **request_args):
        SegmentGenerator.__init__(self)
        self.http = http
        self.url = url
        self.request_args = request_args
        self.part_size = 3 * 1024 * 1024

    def supports_range(self):
        request_args = copy.deepcopy(self.request_args)
        _ = request_args.pop("method", None)
        _ = request_args.pop("stream", None)
        req = self.http.request(method="HEAD", url=self.url, **request_args)
        return ("bytes" in req.headers.get("Accept-Ranges", ""),
                int(req.headers.get("Content-length", 0)))

    def next_segments(self):
        supports_range, length = self.supports_range()

        if supports_range:
            parts = math.ceil(length / self.part_size)
            log.debug("Split segment in to {} parts".format(parts))

            if parts > 1:
                ranges = [(offset, self.part_size) if offset + self.part_size - 1 < length else (offset, None) for offset in range(0, length, self.part_size)]
                if length - ranges[-1][0] < 10*1024 < length:
                    ranges.pop()
                    ranges[-1] = (ranges[-1][0], None)
                for offset, part_length in ranges:
                    yield RangedHTTPSegment(self.url, offset=offset, length=part_length, **self.request_args)
            else:
                yield HTTPSegment(self.url, **self.request_args)
        else:
            yield HTTPSegment(self.url, **self.request_args)

        raise StopIteration


class HTTPStream(Stream):
    """A HTTP stream using the requests library.

    *Attributes:*

    - :attr:`url`  The URL to the stream, prepared by requests.
    - :attr:`args` A :class:`dict` containing keyword arguments passed
      to :meth:`requests.request`, such as headers and cookies.

    """

    __shortname__ = "http"

    def __init__(self, session_, url, buffered=True, **args):
        Stream.__init__(self, session_)

        self.args = dict(url=url, **args)
        self.buffered = buffered

    def __repr__(self):
        return "<HTTPStream({0!r})>".format(self.url)

    def __json__(self):
        method = self.args.get("method", "GET")
        req = requests.Request(method=method, **valid_args(self.args))

        # prepare_request is only available in requests 2.0+
        if hasattr(self.session.http, "prepare_request"):
            req = self.session.http.prepare_request(req)
        else:
            req = req.prepare()

        headers = dict(map(normalize_key, req.headers.items()))

        return dict(type=type(self).shortname(), url=req.url,
                    method=req.method, headers=headers,
                    body=req.body)

    @property
    def url(self):
        method = self.args.get("method", "GET")
        return requests.Request(method=method,
                                **valid_args(self.args)).prepare().url

    def open(self):
        generator = self.create_segment_generator(self.session.http, **self.args)
        buffer = RingBuffer(self.session.get_option("ringbuffer-size"))
        proc = HTTPSegmentProcessor(self.session.http, generator, buffer)
        return proc.open()

    def to_url(self):
        return self.url

    def create_segment_generator(self, *args, **kwargs):
        return RangeHTTPSegmentGenerator(self, *args, **kwargs)
