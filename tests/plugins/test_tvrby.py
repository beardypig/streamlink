import unittest


class TestPluginTVRBy(unittest.TestCase):
    def test_can_handle_url(self):
        from streamlink.plugins.tvrby import TVRBy
        # should match
        self.assertTrue(TVRBy.can_handle_url("http://www.tvr.by/televidenie/belarus-1/"))
        self.assertTrue(TVRBy.can_handle_url("http://www.tvr.by/televidenie/belarus-1"))
        self.assertTrue(TVRBy.can_handle_url("http://www.tvr.by/televidenie/belarus-24/"))
        self.assertTrue(TVRBy.can_handle_url("http://www.tvr.by/televidenie/belarus-24"))

        # shouldn't match
        self.assertFalse(TVRBy.can_handle_url("http://www.tv8.cat/algo/"))
        self.assertFalse(TVRBy.can_handle_url("http://www.tvcatchup.com/"))
        self.assertFalse(TVRBy.can_handle_url("http://www.youtube.com/"))

    def test_url_fix(self):
        from streamlink.plugins.tvrby import TVRBy
        self.assertTrue(
            "http://www.tvr.by/televidenie/belarus-1/",
            TVRBy("http://www.tvr.by/televidenie/belarus-1/").url)
        self.assertTrue(
            "http://www.tvr.by/televidenie/belarus-1/",
            TVRBy("http://www.tvr.by/televidenie/belarus-1").url)
        self.assertTrue(
            "http://www.tvr.by/televidenie/belarus-24/",
            TVRBy("http://www.tvr.by/televidenie/belarus-24/").url)
        self.assertTrue(
            "http://www.tvr.by/televidenie/belarus-24/",
            TVRBy("http://www.tvr.by/televidenie/belarus-24").url)
