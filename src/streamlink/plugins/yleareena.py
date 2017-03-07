from __future__ import print_function
import re

from streamlink.plugin import Plugin
from streamlink.plugin.api import http
from streamlink.plugin.api import validate
from streamlink.stream import HLSStream
from streamlink.utils import parse_json


class YLEAreena(Plugin):
    url_re = re.compile(r"https?://(?:www\.)?areena.yle.fi/tv/suorat")
    UI_CONFIG_ID = 37558971
    WID = "_1955031"
    id_re = re.compile(r'"yle:channel" content="(.*?)"')
    api_url = "https://player.yle.fi/api/v1/services.jsonp"
    services_schema = validate.Schema({
        "data": {
            "service": {
                "outlet": [
                    {"region": validate.text,
                     "type": validate.text,
                     "media": {
                         "id": validate.text,
                         "type": validate.text
                     }
                     }
                ]
            }
        }
    }, validate.get("data"))
    player_config_schema = validate.Schema({
        "entryResult": {
            "meta": {
                "hlsStreamUrl": validate.url()
            }
        }
    }, validate.get("entryResult"), validate.get("meta"), validate.get("hlsStreamUrl"))
    frame_url = "http://cdnapi.kaltura.com/html5/html5lib/v2.52/mwEmbedFrame.php"
    entry_ids = {
        "10-1": "0_5b5tgtxb",
        "10-38": "0_xxdtnjgg",
        "10-2": "0_gpx3lpzo",
        "10-39": "0_an3qei0l",
        "10-3": "0_urulwpuk",
        "10-40": "0_fuyregh7",
        "10-4": "0_mhi0k2hy",
        "10-41": "0_efu3tmnn",
        "10-5": "0_3ovgfsep",
        "10-42": "0_efu3tmnn"
    }
    package_data_re = re.compile(r"window.kalturaIframePackageData = (\{.*?});")

    @classmethod
    def can_handle_url(cls, url):
        return cls.url_re.match(url) is not None

    def _get_channel_id(self):
        res = http.get(self.url)
        m = self.id_re.search(res.text)
        return m and m.group(1)

    def _get_entry_ids(self):
        res = http.get(self.api_url, params=dict(
            id=self._get_channel_id(),
            region="world"
        ))
        data = http.json(res, schema=self.services_schema)
        for outlet in data["service"]["outlet"]:
            media_id = outlet["media"]["id"]
            entry_id = self.entry_ids.get(media_id)
            self.logger.debug("Output: {0}: {1} => {2}", outlet["region"], media_id, entry_id)
            yield entry_id

    def _get_streams(self):
        for entry_id in self._get_entry_ids():
            res = http.get(self.frame_url, params=dict(
                wid=self.WID,
                uiconf_id=self.UI_CONFIG_ID,
                entry_id=entry_id
            ))

            m = self.package_data_re.search(res.text)
            if m:
                stream_url = parse_json(m.group(1), schema=self.player_config_schema)
                try:
                    return HLSStream.parse_variant_playlist(self.session, stream_url)
                except:
                    pass


__plugin__ = YLEAreena
