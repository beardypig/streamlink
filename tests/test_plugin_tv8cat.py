import unittest

from streamlink.plugins.tv8cat import TV8cat


class TestPluginTV8cat(unittest.TestCase):
    def test_can_handle_url(self):
        # should match
        self.assertTrue(TV8cat.can_handle_url("http://8tv.cat/directe"))
        self.assertTrue(TV8cat.can_handle_url("http://www.8tv.cat/directe"))
        self.assertTrue(TV8cat.can_handle_url("http://www.8tv.cat/directe/"))
        self.assertTrue(TV8cat.can_handle_url("https://8tv.cat/directe/"))

        # shouldn't match
        self.assertFalse(TV8cat.can_handle_url("http://www.tv8.cat/algo/"))
        self.assertFalse(TV8cat.can_handle_url("http://www.8tv.cat/algo/"))
        self.assertFalse(TV8cat.can_handle_url("http://www.tvcatchup.com/"))
        self.assertFalse(TV8cat.can_handle_url("http://www.youtube.com/"))
