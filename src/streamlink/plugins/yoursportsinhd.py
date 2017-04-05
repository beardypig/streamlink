import base64
import pickle
import re

from Crypto.Cipher import AES

from streamlink import StreamError
from streamlink.plugin import Plugin
from streamlink.plugin.api import http
from streamlink.stream import HLSStream
from streamlink.stream.hls import HLSStreamWriter, HLSStreamReader, num_to_iv

_url_re = re.compile(r"https?://(\w+\.)?yoursportsinhd.com")
_m3u8_re = re.compile(r"""sources:[\s\S]+src:\s["'](?:\s)?(?P<url>(?!http://nasatv)[^"'\s]+)(?:\s)?["']""")


class YourSportsInHDHLSStreamWriter(HLSStreamWriter):
    replace_pairs = pickle.loads(base64.b64decode(
        b'gANdcQAoWBYAAABodHRwczovL21mLnN2Yy5uaGwuY29tcQFYJQAAAGh0dHA6Ly95b3Vyc3'
        b'BvcnRzaW5oZC5jb20vbmhsL2dldF9rZXlxAoZxA1hKAAAAaHR0cHM6Ly9icm9hZGJhbmQu'
        b'ZXNwbi5nby5jb20vZXNwbjMvYXV0aC9lc3BubmV0d29ya3MvbTN1OC92MS9nZW5lcmF0ZU'
        b'tleT9xBFgnAAAAaHR0cDovL3lvdXJzcG9ydHNpbmhkLmNvbS9uY2FhL2dldF9rZXkvcQWG'
        b'cQZYVwAAAGh0dHBzOi8vbWxiLXdzLW1mLm1lZGlhLm1sYi5jb20vcHViYWpheHdzL2JhbX'
        b'Jlc3QvTWVkaWFTZXJ2aWNlMl8wL29wLWdlbmVyYXRlS2V5L3YtMi4zP3EHWCYAAABodHRw'
        b'Oi8veW91cnNwb3J0c2luaGQuY29tL21sYi9nZXRfa2V5L3EIhnEJWDMAAABodHRwczovL2'
        b'tleS1zZXJ2aWNlLnRvdHN1a28udHYva2V5LXNlcnZpY2Uva2V5L2tleT9xClgmAAAAaHR0'
        b'cDovL3lvdXJzcG9ydHNpbmhkLmNvbS92dWUvZ2V0X2tleS9xC4ZxDGUu'))

    def create_decryptor(self, key, sequence):
        if key.method != "AES-128":
            raise StreamError("Unable to decrypt cipher {0}", key.method)

        if not key.uri:
            raise StreamError("Missing URI to decryption key")

        key_uri = key.uri
        for args in self.replace_pairs:
            key_uri = key_uri.replace(*args)

        if self.key_uri != key_uri:
            res = self.session.http.get(key_uri, exception=StreamError,
                                        retries=self.retries,
                                        **self.reader.request_params)
            self.key_data = res.content
            self.key_uri = key_uri

        iv = key.iv or num_to_iv(sequence)

        # Pad IV if needed
        iv = b"\x00" * (16 - len(iv)) + iv

        return AES.new(self.key_data, AES.MODE_CBC, iv)


class YourSportsInHDHLSStreamReader(HLSStreamReader):
    __writer__ = YourSportsInHDHLSStreamWriter


class YourSportsInHDHLSStream(HLSStream):
    def open(self):
        reader = YourSportsInHDHLSStreamReader(self)
        reader.open()

        return reader


class YourSportsInHD(Plugin):
    @classmethod
    def can_handle_url(cls, url):
        return _url_re.match(url)

    def _get_streams(self):
        res = http.get(self.url)
        m3u8_link = _m3u8_re.search(res.text)

        hls_url = m3u8_link.group("url")

        if hls_url:
            for q, s in HLSStream.parse_variant_playlist(self.session, hls_url).items():
                yield q, YourSportsInHDHLSStream(self.session, s.url)


__plugin__ = YourSportsInHD
