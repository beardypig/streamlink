import re

from streamlink.plugin.api import validate

__all__ = ["parse_playlist"]

from streamlink.utils import jsonutil

_playlist_re = re.compile(r"\(?\{.*playlist: (\[.*\]),.*?\}\)?;", re.DOTALL)

_playlist_schema = validate.Schema(
    validate.transform(_playlist_re.search),
    validate.any(
        None,
        validate.all(
            validate.get(1),
            validate.transform(jsonutil.from_js),
            [{
                "sources": [{
                    "file": validate.text,
                    validate.optional("label"): validate.text
                }]
            }]
        )
    )
)


def parse_playlist(res):
    """Attempts to parse a JWPlayer playlist in a HTTP response body."""
    return _playlist_schema.validate(res.text)
