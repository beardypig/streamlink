import copy

import requests

from streamlink.compat import getargspec
from streamlink.exceptions import StreamError
from streamlink.stream import Stream
from streamlink.stream.wrappers import StreamIOThreadWrapper, StreamIOIterWrapper
from streamlink.buffers import RingBuffer
from streamlink.stream.segmented import SegmentGenerator, HTTPSegment, RangedHTTPSegment, \
    HTTPSegmentProcessor
from .stream import Stream


def normalize_key(keyval):
    key, val = keyval
    key = hasattr(key, "decode") and key.decode("utf8", "ignore") or key

    return key, val


def valid_args(args):
    argspec = getargspec(requests.Request.__init__)

    return dict(filter(lambda kv: kv[0] in argspec.args, args.items()))


class RangeHTTPSegmentGenerator(SegmentGenerator):
    def __init__(self, session, url, **request_args):
        self.session = session
        self.url = url
        self.request_args = request_args

    def supports_range(self):
        request_args = copy.deepcopy(self.request_args)
        _ = request_args.pop("method", None)
        _ = request_args.pop("stream", None)
        req = self.session.request(method="HEAD", url=self.url, **request_args)
        return ("bytes" in req.headers.get("Accept-Ranges", ""),
                int(req.headers.get("Content-length", 0)))

    def __iter__(self):
        supports_range, length = self.supports_range()
        range_size = 3 * 1024 * 1024
        if length:
            range_size = max(length / 10, range_size)  # ~10 parts (no smaller than 3MB)

        if supports_range and length > 2 * range_size:
            parts = int(length / range_size)
            for i in range(0, parts):
                yield RangedHTTPSegment(self.url, offset=i * range_size, length=range_size, **self.request_args)
            if parts * range_size < length-1:
                yield RangedHTTPSegment(self.url, offset=parts * range_size, **self.request_args)
        else:
            yield HTTPSegment(self.url, **self.request_args)


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
        generator = RangeHTTPSegmentGenerator(self.session.http, **self.args)
        buffer = RingBuffer()
        proc = HTTPSegmentProcessor(self.session.http, generator, buffer)
        return proc.open()

    def to_url(self):
        return self.url
