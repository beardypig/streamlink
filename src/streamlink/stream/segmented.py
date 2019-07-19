import concurrent.futures
import logging
import time
from concurrent import futures
from concurrent.futures import CancelledError
from threading import Thread, Lock, Event
from math import log2
from contextlib import contextmanager

from streamlink import StreamError

try:
    import queue
except ImportError:
    import Queue as queue

from Crypto.Cipher import AES

from streamlink.buffers import RingBuffer

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def shorten(text, width):
    text = text.strip()
    if len(text) > width:
        width_h = max((width - 2) // 2, 1)
        x = text[:width_h]
        y = text[-width_h:]
        return "{0}..{1}".format(x.strip(), y.strip())
    else:
        return text


def sizeof_fmt(size):
    units = ['', 'Ki', 'Mi', 'Gi']
    order = int(log2(size) // 10) if size > 0 else 0
    unit = units[order] if order < len(units) else units[-1]

    return "{0:.4g}{1}B".format(size / 1024**order, unit)


class AutoIncrementSegment(object):
    __sequence_lock = Lock()
    __sequence_counter = None

    def __init__(self):
        self.sequence_number = self.next_sequence()

    @classmethod
    def next_sequence(cls):
        with cls.__sequence_lock:
            if cls.__sequence_counter is not None:
                cls.__sequence_counter += 1
            else:
                cls.__sequence_counter = 0
            return cls.__sequence_counter


class Segment(object):
    @property
    def encrypted(self):
        """
        If the segment is encrypted or not
        :return: True|False
        """
        return False

    def decrypt(self, block):
        """
        Decrypts a block of data
        :param block:
        :return:
        """
        return block

    def finalise(self):
        """
        Finalise any decrpytion for block ciphers.
        :return:
        """
        pass


class HTTPSegment(Segment, AutoIncrementSegment):
    def __init__(self, uri, **request_params):
        """
        The definition of a segment

        These segments only support block cipher encryption

        :param uri: the URI of the resource to download
        :param request_params: additional request parameters that should be passed to the Request
        """
        super(HTTPSegment, self).__init__()
        self._uri = uri
        self._request_parameters = request_params

    @property
    def uri(self):
        """
        Read-only URI property
        :return:
        """
        return self._uri

    def request_parameters(self):
        """
        Generate an additional request parameters that might be required to make
        the request, eg. specific headers

        Note: this MUST exclude the Range header
        :return:
        """
        return self._request_parameters

    @property
    def range(self):
        """
        Return the required byte offset and length for any chunking in the
        segments (directly corresponds to the Range HTTP header).
        A length of None means all remaining data

        :return: (offset, length|None)
        """
        return 0, None


class RangedHTTPSegment(HTTPSegment):
    """
    Range of bytes in a URL, typically for parallel access to the same URL
    """

    def __init__(self, uri, offset, length=None, **request_params):
        super(RangedHTTPSegment, self).__init__(uri,
                                                **request_params)
        self.offset = offset
        self.length = length

    @property
    def range(self):
        return self.offset, self.length


class SegmentDecryptionError(Exception):
    """
    Error occurred while decrypting
    """
    pass


class AESEncryptedHTTPSegment(HTTPSegment):
    """
    An encrypted HTTP Segment, range requests will not be possible
    """

    def __init__(self, uri, key, iv, **request_params):
        super(AESEncryptedHTTPSegment, self).__init__(uri,
                                                      **request_params)
        # TODO: test correctness of key + IV
        self.key = key
        self.iv = iv
        self._decrptor = self.create_decryptor()
        self._buffer = b""

    @property
    def key_size(self):
        return len(self.key)

    def decrypt(self, block):
        """
        Decrypts a block of data
        :param block:
        :return:
        """
        aligned_size = (len(block) // self.key_size) * self.key_size
        eblock = self._buffer + block
        cipher_text, self._buffer = eblock[aligned_size:], eblock[aligned_size:]
        return self._decrptor.decrypt(cipher_text)

    def finalise(self):
        """
        Finalise any decrpytion for block ciphers.
        :return:
        """
        if len(self._buffer) % self.key_size:
            raise SegmentDecryptionError("block size misaligned")
        elif len(self._buffer) > 0:
            return self._decrptor.decrypt(self._buffer)
        else:
            return b""

    def create_decryptor(self):
        """
        If the segment is encrypted then create a decrpytor to decrypt it
        :return:
        """
        return AES.new(self.key, AES.MODE_CBC, self.iv)

    @property
    def encrypted(self):
        return True


class SegmentGenerator(object):
    """
    Generate segments including sequence information
    """

    def __init__(self):
        self._closed = Event()

    def next_segments(self):
        raise NotImplementedError

    def __iter__(self):
        while not self.closed:
            for segment in self.next_segments():
                yield segment

    def wait(self, seconds):
        """
        Pauses the thread for a specified time.

        Returns False if interrupted by another thread and True if the
        time runs out normally.
        """
        return not self._closed.wait(seconds)

    @contextmanager
    def waiter(self, duration):
        """
        This code block will take at least duration seconds to run, if
        needed a wait will be inserted at the end to ensure the run time.

        The wait can be interrupted by another thread.

        :param duration: the amount of time to wait
        """
        s = time.time()
        yield
        time_to_sleep = duration - (time.time() - s)
        if time_to_sleep > 0:
            self.wait(time_to_sleep)

    def close(self):
        self._closed.set()

    @property
    def closed(self):
        return self._closed.is_set()


class ManifestBasedSegmentGenerator(SegmentGenerator):
    # sensible defaults
    MIN_RELOAD_TIME = 1.0
    DEFAULT_RELOAD_TIME = 3.0

    def __init__(self):
        super(ManifestBasedSegmentGenerator, self).__init__()
        self._manifest_reload_time = self.DEFAULT_RELOAD_TIME

    @property
    def manifest_reload_time(self):
        return self._manifest_reload_time

    @manifest_reload_time.setter
    def manifest_reload_time(self, value):
        # ensure that the reload time is never less than the minimum
        self._manifest_reload_time = max(self.MIN_RELOAD_TIME, value or self.DEFAULT_RELOAD_TIME)

    def reload_manifest(self):
        raise NotImplementedError

    def parse_manifest(self, content, url, **kwargs):
        raise NotImplementedError

    def update_reload_time(self, current, manifest_changed):
        raise NotImplementedError

    def next_segments(self):
        raise NotImplementedError

    def __iter__(self):
        last_reload = None

        while not self.closed:
            with self.waiter(self.manifest_reload_time):
                try:
                    time_since_reload = time.time() - last_reload if last_reload else 0
                    log.debug("Reloading playlist... (time since last reload {:.3g}s)".format(time_since_reload))
                    changed = self.reload_manifest()
                    last_reload = time.time()
                    self.manifest_reload_time = self.update_reload_time(self.manifest_reload_time, changed)
                    log.debug("Updated playlist refresh time to {0:.2f}s".format(self.manifest_reload_time))

                except StreamError as err:
                    log.warning("Failed to reload manifest: {0}", err)

                for segment in self.next_segments():
                    yield segment


class SegmentError(Exception):
    pass


class SegmentProcessor(Thread):
    def __init__(self, segment_generator, buffer, **kwargs):
        super(SegmentProcessor, self).__init__(**kwargs)
        assert isinstance(buffer, RingBuffer)
        self._closed = Event()
        self.segment_generator = segment_generator
        self.buffer = buffer

        self.threads = 5  # (os.cpu_count() or 1) * 5
        self.timeout = 5.0
        self.fetch_executor = futures.ThreadPoolExecutor(max_workers=self.threads)
        self._filler = None
        self._data_queue = queue.Queue(maxsize=100)
        self._queue_lock = Lock()
        self._started = Event()

    @property
    def closed(self):
        return self._closed.is_set()

    def wait(self, timeout):
        return not self._closed.wait(timeout)

    def run(self):
        # start thread to fill the executor pool
        self._filler = Thread(target=self.filler)
        self._filler.start()
        self._started.set()

        while not self.closed:
            try:
                segment, buffer, future = self._data_queue.get(block=False)
            except queue.Empty:
                self.wait(0.1)
                continue

            if segment is None:
                # completed all items in the queue
                self.buffer.close()
                return

            log.debug("Writing {0} to output buffer".format(segment.sequence_number))
            while not self.closed:
                # copy from the segment buffer to the output buffer
                try:
                    for chunk in buffer.read_iter(16 * 1024):
                        self.write(chunk)
                    log.debug("Segment {0} written to output buffer".format(segment.sequence_number))
                    break
                except IOError:
                    try:
                        exception = future.exception(0)
                        if exception:
                            log.error("Segment {0} failed with error: {1}".format(segment.sequence_number, exception))
                            break
                    except TimeoutError:
                        continue
                    except CancelledError:
                        log.error("Download if {0} cancelled".format(segment.sequence_number))
                        break

    def filler(self):
        """
        Takes segments and puts them in the executor queue, and then adds the
        future to the data queue with the associated segment descriptor
        """
        log.debug("Started filler thread...")
        # fill thread queue
        # TODO: segments should be added to a queue in the a separate thread so that HLS reloads, etc are not blocked.
        for segment in self.segment_generator:
            if self.closed:
                return
            if segment is not None:
                buffer = RingBuffer(size=2 * 1024 * 1024)
                try:
                    future = self.fetch_executor.submit(self.fetcher, segment, buffer)
                    self.put((segment, buffer, future))
                    log.debug("Queued segment #{}...".format(segment.sequence_number))
                except RuntimeError:
                    return

        self.put((None, None, None))
        log.debug("All segmented queued")

    def fetcher(self, segment, buffer):
        """
        Manage the fetching of the segment, stores the data in a per-segment buffer

        :param segment: the segment descriptor
        :param buffer: output buffer for this segment
        """
        for chunk in self.fetch(segment, chunk_size=min(buffer.buffer_size, 16 * 1024)):
            buffer.write(chunk)
        buffer.close()

    def fetch(self, segment, chunk_size=16 * 1024):
        raise NotImplementedError

    def put(self, item):
        # Add the item to the queue, with a timeout and retry  - the timeout
        # is required to avoid a deadlock with the lock in run() as put
        # is a blocking call.
        while not self.closed:
            try:
                self._data_queue.put(item, block=False)
                return  # successfully added the item to the queue
            except queue.Full:
                self.wait(0.1)
                continue

    def open(self):
        """
        Open the stream for reading.

        Start filling the buffer
        :return:
        """
        self.start()
        self._started.wait()
        return self

    def read(self, size=8 * 1024):
        if not self.buffer or self._filler is None:
            return b""

        return self.buffer.read(size, timeout=self.timeout)

    def write(self, data):
        return self.buffer.write(data)

    def close(self):
        self._closed.set()
        self.segment_generator.close()
        self.buffer.close()

        self.fetch_executor.shutdown(wait=False)
        if concurrent.futures.thread._threads_queues:
            concurrent.futures.thread._threads_queues.clear()


class HTTPSegmentProcessor(SegmentProcessor):
    """
    Downloads HTTPSegments and writes the data to an output buffer.

    The segments are streamed and decrypted on the fly, if required, and streamed
    out to a queue, where they are written to an output buffer.
    """

    def __init__(self, http, segment_generator, buffer, **kwargs):
        super(HTTPSegmentProcessor, self).__init__(segment_generator, buffer, **kwargs)
        self.http = http

        self.retries = 3
        self.timeout = 5 * self.retries
        self.request_params = {}
        self.byterange_offsets = {}

    @staticmethod
    def _get_range_header(segment, offset=0):
        """
        If the segment has a range attribute then return a Range header
        :param segment: Segment to generate range for
        :param offset: additional offset in to the range, for resuming interrupted requests
        :return: dict; with posible Range header set
        """
        headers = {}
        start, length = segment.range
        start += offset
        if length and offset:
            length = max(length - (offset - 1), 0)

        if start > 0 or length is not None:
            headers["Range"] = "bytes={0}-{1}".format(start, (start + length - 1) if length else "")

        return headers

    def fetch(self, segment, chunk_size=128 * 1024):
        """
        Download the sequence and yield data chunks.

        Segments can be downloaded in any order, but these threads should not be
        blocked by earlier segments that have not been downloaded.

        :param segment: the Segment to download
        :param chunk_size: size in bytes to yield
        :yield: data and segment number
        """

        log.debug("Starting fetch of #{} : {} (range: {}-{})".format(segment.sequence_number, shorten(segment.uri, width=70),
                                                                     segment.range[0], segment.range[1] or ""))

        retries = self.retries
        offset = 0
        last_error = None
        headers = {}

        for _ in range(retries):
            # if the download fails mid-stream, and this is a retry, then add the
            # offset to the range header.

            headers.update(self._get_range_header(segment, offset))
            try:
                # TODO: ignore names needs to be handled before this, in the segment generator)
                streamer = self.http.get(segment.uri,
                                         raise_for_status=False,
                                         stream=True,
                                         headers=headers)
                # check that the request support range, and skip over the bytes
                # that are outside the required range. this should always be in
                # whole chunks as it is not possible to have differently sized
                # chunks
                # TODO:
                # if "Range" in headers:
                #     if streamer.status_code == 200:  # none-partial reply
                #         log.debug("Non-partial reply in Range query")
                #         skipped = 0
                #         for chunk in content:
                #             skipped += len(chunk)
                #             if skipped >= offset:
                #                 break
                if streamer.headers.get("Content-Length"):
                    size = sizeof_fmt(int(streamer.headers.get("Content-Length")))
                else:
                    size = "unknown size"
                log.debug("Starting download of segment {0} ({1})".format(segment.sequence_number, size))
                t = time.time()
                for chunk in streamer.iter_content(chunk_size=chunk_size):
                    if self.closed:  # stop downloading the segment if interrupted
                        break
                    if segment.encrypted:
                        yield segment.decrypt(chunk)
                    else:
                        yield chunk
                    offset += len(chunk)  # update the offset
                    # TODO: for non-partial stop at the right place
                log.debug("Completed download of segment {0} in {1:.1f}s".format(segment.sequence_number, time.time() - t))
                return  # completed successfully
            except Exception as err:
                # failed, need to retry build maintain the current offset
                last_error = err
                log.debug(err)

        log.error("Failed to open segment {0}: {1}", segment.sequence_nuber,
                  last_error)
        raise SegmentError("Failed to read segment", segment, last_error)
