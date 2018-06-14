import json
import logging
import re
from uuid import uuid4

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

from streamlink.compat import urljoin
from streamlink.plugin import Plugin
from streamlink.plugin.api import http, useragents, validate
from streamlink.plugin.api.utils import itertags
from streamlink.stream import HLSStream, RTMPStream, HDSStream
from streamlink.compat import urlparse

log = logging.getLogger(__name__)


class ITVPlayer(Plugin):
    _url_re = re.compile(r"https?://(?:www.)?itv.com/hub/(?P<stream>.+)")
    _live_swf = "http://www.itv.com/mediaplayer/ITVMediaPlayer.swf"
    _vod_swf = "http://www.itv.com/mercury/Mercury_VideoPlayer.swf"
    _channel_map = {'itv': 1, 'itv2': 2, 'itv3': 3, 'itv4': 4, 'itvbe': 8, 'citv': 7}
    _video_info_schema = validate.Schema({
        "StatusCode": 200,
        "AdditionalInfo": {
            "Message": validate.any(None, validate.text)
        },
        "Playlist": {
            "VideoType": validate.text,
            "Video": {
                "Subtitles": validate.any(None, [{
                    "Href": validate.url(),
                }]),
                "Base": validate.url(),
                "MediaFiles": [
                    {"Href": validate.text,
                     "KeyServiceUrl": validate.any(None, validate.url())}
                ]
            }
        }
    })

    @classmethod
    def can_handle_url(cls, url):
        match = cls._url_re.match(url)
        return match is not None

    @property
    def device_info(self):
        return {"user": {},
                "client": {"version": "4.1", "id": "browser"},
                "variantAvailability": {"featureset": {"min": ["hls", "aes"],
                                                       "max": ["hls", "aes"]},
                                        "platformTag": "dotcom"}}

    def video_info(self):
        page = http.get(self.url)
        for div in itertags(page.text, 'div'):
            if div.attributes.get("id") == "video":
                return div.attributes

    def _get_streams(self):
        """
            Find all the streams for the ITV url
            :return: Mapping of quality to stream
        """
        http.headers.update({"User-Agent": useragents.CHROME})
        video_info = self.video_info()
        for s in self._flash_streams(video_info).items():
            yield s
        for s in self._html5_streams(video_info):
            yield s

    def _html5_streams(self, video_info):
        video_info_url = video_info.get("data-html5-playlist") or video_info.get("data-video-id")
        if video_info_url.endswith(".xml"):
            log.debug("Getting HTML5 streams")
            return

        log.debug("Getting HTML5 streams")
        res = http.post(video_info_url,
                        data=json.dumps(self.device_info),
                        headers={"hmac": video_info.get("data-video-hmac")})
        data = http.json(res, schema=self._video_info_schema)

        log.debug("Video ID info response: {0}".format(data))

        stype = data['Playlist']['VideoType']

        for media in data['Playlist']['Video']['MediaFiles']:
            url = urljoin(data['Playlist']['Video']['Base'], media['Href'])
            name_fmt = "{pixels}_{bitrate}" if stype == "CATCHUP" else None
            try:
                for s in HLSStream.parse_variant_playlist(self.session, url, name_fmt=name_fmt).items():
                    yield s
            except OSError:
                log.warning("HTML5 streams available")

    def _flash_streams(self, video_info):
        log.debug("Getting legacy flash streams")
        channel_id = self._channel_map.get(video_info.get("data-video-channel-id"))

        soap_message = self._soap_request(production_id=video_info.get("data-video-production-id"),
                                          channel_id=channel_id)

        headers = {'Content-Length': '{0:d}'.format(len(soap_message)),
                   'Content-Type': 'text/xml; charset=utf-8',
                   'Host': 'secure-mercury.itv.com',
                   'Origin': 'http://www.itv.com',
                   'Referer': self.url,
                   'SOAPAction': "http://tempuri.org/PlaylistService/GetPlaylist",
                   'User-Agent': useragents.CHROME,
                   "X-Requested-With": "ShockwaveFlash/16.0.0.305"}

        res = http.post("https://secure-mercury.itv.com/PlaylistService.svc?wsdl",
                        headers=headers,
                        data=soap_message)

        xmldoc = http.xml(res)

        # Look for <MediaFiles> tag (RTMP streams)
        mediafiles = xmldoc.find('.//VideoEntries//MediaFiles')

        # Look for <ManifestFile> tag (HDS streams)
        manifestfile = xmldoc.find('.//VideoEntries//ManifestFile')

        # No streams
        if not mediafiles and not manifestfile:
            log.warning("No flash streams available")
            return {}

        streams = {}

        # Parse RTMP streams
        if mediafiles:
            rtmp = mediafiles.attrib['base']

            for mediafile in mediafiles.findall("MediaFile"):
                playpath = mediafile.find("URL").text

                rtmp_url = urlparse(rtmp)
                app = (rtmp_url.path[1:] + '?' + rtmp_url.query).rstrip('?')
                live = app == "live"

                params = dict(rtmp="{u.scheme}://{u.netloc}{u.path}".format(u=rtmp_url),
                              app=app.rstrip('?'),
                              playpath=playpath,
                              swfVfy=self._live_swf if live else self._vod_swf,
                              timeout=10)
                if live:
                    params['live'] = True

                bitrate = int(mediafile.attrib['bitrate']) / 1000
                quality = "{0:d}k".format(int(bitrate))
                streams[quality] = RTMPStream(self.session, params)

        # Parse HDS streams
        if manifestfile:
            url = manifestfile.find('URL').text

            if urlparse(url).path.endswith('f4m'):
                streams.update(
                    HDSStream.parse_manifest(self.session, url, pvswf=self._live_swf)
                )

        return streams

    def _soap_request(self, production_id, channel_id):

        def sub_ns(parent, tag, ns):
            return ET.SubElement(parent, "{%s}%s" % (ns, tag))

        def sub_common(parent, tag):
            return sub_ns(parent, tag, "http://schemas.itv.com/2009/05/Common")

        def sub_soap(parent, tag):
            return sub_ns(parent, tag, "http://schemas.xmlsoap.org/soap/envelope/")

        def sub_item(parent, tag):
            return sub_ns(parent, tag, "http://tempuri.org/")

        def sub_itv(parent, tag):
            return sub_ns(parent, tag, "http://schemas.datacontract.org/2004/07/Itv.BB.Mercury.Common.Types")

        ET.register_namespace("com", "http://schemas.itv.com/2009/05/Common")
        ET.register_namespace("soapenv", "http://schemas.xmlsoap.org/soap/envelope/")
        ET.register_namespace("tem", "http://tempuri.org/")
        ET.register_namespace("itv", "http://schemas.datacontract.org/2004/07/Itv.BB.Mercury.Common.Types")

        # Start of XML
        root = ET.Element("{http://schemas.xmlsoap.org/soap/envelope/}Envelope")

        sub_soap(root, "Header")
        body = sub_soap(root, "Body")

        # build request
        get_playlist = sub_item(body, "GetPlaylist")
        request = sub_item(get_playlist, "request")
        prode = sub_itv(request, "ProductionId")

        if production_id:
            # request -> ProductionId
            prode.text = production_id

        # request -> RequestGuid
        sub_itv(request, "RequestGuid").text = str(uuid4()).upper()

        vodcrid = sub_itv(request, "Vodcrid")
        # request -> Vodcrid -> Id
        vod_id = sub_common(vodcrid, "Id")
        # request -> Vodcrid -> Partition
        sub_common(vodcrid, "Partition").text = "itv.com"

        if not production_id and channel_id:
            vod_id.text = "sim{0}".format(channel_id)

        # build userinfo
        userinfo = sub_item(get_playlist, "userInfo")
        sub_itv(userinfo, "Broadcaster").text = "Itv"
        sub_itv(userinfo, "RevenueScienceValue").text = "ITVPLAYER.2.18.14.+build.a778cd30ac"
        sub_itv(userinfo, "SessionId")
        sub_itv(userinfo, "SsoToken")
        sub_itv(userinfo, "UserToken")
        # GeoLocationToken -> Token
        # sub_itv(sub_itv(userinfo, "GeoLocationToken"), "Token")

        # build siteinfo
        siteinfo = sub_item(get_playlist, "siteInfo")
        sub_itv(siteinfo, "AdvertisingRestriction").text = "None"
        sub_itv(siteinfo, "AdvertisingSite").text = "ITV"
        sub_itv(siteinfo, "AdvertisingType").text = "Any"
        sub_itv(siteinfo,
                "Area").text = "ITVPLAYER.VIDEO"  # "channels.itv{0}".format(channel_id) if channel_id else "ITVPLAYER.VIDEO"
        sub_itv(siteinfo, "Category")
        sub_itv(siteinfo, "Platform").text = "DotCom"
        sub_itv(siteinfo, "Site").text = "ItvCom"

        # build deviceInfo
        deviceinfo = sub_item(get_playlist, "deviceInfo")
        sub_itv(deviceinfo, "ScreenSize").text = "Big"

        # build playerinfo
        playerinfo = sub_item(get_playlist, "playerInfo")
        sub_itv(playerinfo, "Version").text = "2"

        return ET.tostring(root)


__plugin__ = ITVPlayer
