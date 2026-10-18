"""The Router panel's update check understands one feed, several feeds and a Router-only install."""
import json
import tempfile
import unittest
from pathlib import Path

from core.updater import _release_sources, router_feed_configured

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


    def test_all_feeds_file_is_preferred_over_the_legacy_hub_only_file(self):
        # Since bootstrap 0.1.5 release-source.json stays Hub-only (older Hubs read it); the Router is listed in
        # release-sources.json. Reading only the legacy file made 'Denetle' refuse with 'Router kaynağı yok'.
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / 'bootstrap'
            folder.mkdir()
            (folder / 'release-source.json').write_text(json.dumps({'schema': 1, **feed(HUB, {'hub': 'h.zip'})}))
            self.assertEqual(_release_sources(Path(root)), {})
            both = {'schema': 2, 'sources': [feed(HUB, {'hub': 'h.zip'}), feed(ROUTER, {'router': 'r.zip'})]}
            (folder / 'release-sources.json').write_text(json.dumps(both))
            self.assertTrue(router_feed_configured(_release_sources(Path(root))))


if __name__ == '__main__':
    unittest.main()
