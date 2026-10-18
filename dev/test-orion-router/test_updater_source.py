"""The Router panel's update check understands one feed, several feeds and a Router-only install."""
import unittest

from core.updater import router_feed_configured

HUB = 'https://github.com/orion-ai-assistant/orion-ai-assistant/releases/download/feed/'
ROUTER = 'https://github.com/orion-ai-assistant/orion-router/releases/download/feed/'


def feed(url, targets):
    return {'metadata_url': url, 'targets_url': url, 'targets': targets}


class RouterFeedSource(unittest.TestCase):
    def test_single_feed_with_router_target(self):
        self.assertTrue(router_feed_configured({'schema': 1, **feed(HUB, {'hub': 'h.zip', 'router': 'r.zip'})}))

    def test_single_feed_without_router_target(self):
        self.assertFalse(router_feed_configured({'schema': 1, **feed(HUB, {'hub': 'h.zip'})}))

    def test_router_only_install_lists_just_the_router_feed(self):
        self.assertTrue(router_feed_configured({'schema': 1, **feed(ROUTER, {'router': 'r.zip'})}))

    def test_hub_managed_install_finds_the_router_in_its_own_feed(self):
        source = {'schema': 2, 'sources': [feed(HUB, {'hub': 'h.zip', 'client': 'c.zip'}), feed(ROUTER, {'router': 'r.zip'})]}
        self.assertTrue(router_feed_configured(source))

    def test_hub_feed_alone_has_no_router(self):
        self.assertFalse(router_feed_configured({'schema': 2, 'sources': [feed(HUB, {'hub': 'h.zip'})]}))

    def test_garbage_is_not_configured(self):
        for value in (None, [], {}, {'schema': 2, 'sources': 3}, {'schema': 2, 'sources': [None]}):
            self.assertFalse(router_feed_configured(value))


if __name__ == '__main__':
    unittest.main()
