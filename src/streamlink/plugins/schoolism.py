from __future__ import print_function

import logging
import re
from functools import partial

from streamlink.plugin import Plugin, PluginArguments, PluginArgument
from streamlink.plugin.api import useragents
from streamlink.plugin.api import validate
from streamlink.stream import HLSStream, HTTPStream
from streamlink.stream.ffmpegmux import MuxedStream
from streamlink.utils import parse_json

log = logging.getLogger(__name__)


class Schoolism(Plugin):
    url_re = re.compile(r"https?://(?:www\.)?schoolism\.com/(viewAssignment|watchLesson).php")
    login_url = "https://www.schoolism.com/index.php"
    key_time_url = "https://www.schoolism.com/video-html/key-time.php"
    playlist_re = re.compile(r"var allVideos\s*=\s*(\[.*\]);", re.DOTALL)
    js_to_json = partial(re.compile(r'(?!<")(\w+):(?!/)').sub, r'"\1":')
    fix_brackets = partial(re.compile(r',\s*\}').sub, r'}')
    playlist_schema = validate.Schema(
        validate.transform(playlist_re.search),
        validate.any(
            None,
            validate.all(
                validate.get(1),
                validate.transform(js_to_json),
                validate.transform(fix_brackets),  # remove invalid ,
                validate.transform(parse_json),
                [{
                    "sources": validate.all([{
                        validate.optional("playlistTitle"): validate.text,
                        "title": validate.text,
                        "src": validate.text,
                        "type": validate.text,
                    }]),
                    validate.optional("subtitles"): validate.all([{
                        "default": bool,
                        "kind": validate.text,
                        "srclang": validate.text,
                        "src": validate.url()
                    }])
                }]
            )
        )
    )

    arguments = PluginArguments(
        PluginArgument(
            "email",
            required=True,
            requires=["password"],
            metavar="EMAIL",
            help="""
        The email associated with your Schoolism account,
        required to access any Schoolism stream.
        """
        ),
        PluginArgument(
            "password",
            sensitive=True,
            metavar="PASSWORD",
            help="A Schoolism account password to use with --schoolism-email."
        ),
        PluginArgument(
            "part",
            type=int,
            default=1,
            metavar="PART",
            help="""
        Play part number PART of the lesson, or assignment feedback video.

        Defaults is 1.
        """),
        PluginArgument(
            "mux-subtitles",
            type="store_true",
            default=False,
            help="""
        If there are subtitles available, then mux them in to output stream.

        Defaults is disabled.
        """
        )
    )

    @classmethod
    def can_handle_url(cls, url):
        return cls.url_re.match(url) is not None

    def login(self, email, password):
        """
        Login to the schoolism account and return the users account
        :param email: (str) email for account
        :param password: (str) password for account
        :return: (str) users email
        """
        if self.options.get("email") and self.options.get("password"):
            res = self.session.http.post(self.login_url, data={"email": email,
                                                               "password": password,
                                                               "redirect": None,
                                                               "submit": "Login"})

            if res.cookies.get("password") and res.cookies.get("email"):
                return res.cookies.get("email")
            else:
                log.error("Failed to login to Schoolism, incorrect email/password combination")
        else:
            log.error("An email and password are required to access Schoolism streams")

    def _extract_streams(self, sources):
        for source in sources:
            if source['type'] == "video/mp4":
                yield "live", HTTPStream(self.session, source["src"],
                                    headers={"User-Agent": useragents.SAFARI_8,
                                             "Referer": self.url})


            elif source['type'] == "application/x-mpegurl":
                for q, s in HLSStream.parse_variant_playlist(self.session,
                                                             source["src"],
                                                             headers={"User-Agent": useragents.SAFARI_8,
                                                                      "Referer": self.url}).items():
                    yield q, s

    def _get_streams(self):
        user = self.login(self.options.get("email"), self.options.get("password"))
        if user:
            log.debug("Logged in to Schoolism as {0}", user)
            res = self.session.http.get(self.url, headers={"User-Agent": useragents.SAFARI_8})
            lesson_playlist = self.playlist_schema.validate(res.text)

            part = self.options.get("part")
            video_type = "Lesson" if "lesson" in self.url_re.match(self.url).group(1).lower() else "Assignment Feedback"

            log.info("Attempting to play {0} Part {1}", video_type, part)

            # make request to key-time api, to get key specific headers
            _ = self.session.http.get(self.key_time_url, headers={"User-Agent": useragents.SAFARI_8})

            try:
                video = lesson_playlist[part+1]
            except IndexError:
                log.error("Could not find {0} Part {1} (there are only {2} parts)", video_type, part, len(lesson_playlist))
            else:
                if "sources" not in video:
                    log.error("Could not find {0} Part {1}", video_type, part)
                else:
                    subtitles = None
                    stream_metadata = None
                    disposition = None
                    if self.options.get("mux_subtitles"):
                        if "subtitles" in video:
                            # extract subtitles
                            pass
                        else:
                            log.warning("Subtitles requested, but none are available")

                    for quality, stream in self._extract_streams(video["sources"]):
                        if subtitles:
                            yield quality, MuxedStream(self.session, stream, subtitles, metadata=stream_metadata, disposition=disposition)
                        else:
                            yield quality, stream



__plugin__ = Schoolism
