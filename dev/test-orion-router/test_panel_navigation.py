import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from api.hubs import providers


class PanelNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_metadata_reports_actual_local_http_port_and_ipv6_https(self):
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(dynamic_router=SimpleNamespace(get_capabilities=lambda: {'local': []}))))
        with patch('database.db_manager.fetch', AsyncMock(return_value=[])), patch('core.key_policy.candidates', AsyncMock(return_value=[])), patch('core.mdns.lan_addresses', return_value=['fd00::1']), patch('core.mdns.container', return_value=False), patch('core.config.LOCAL_HTTP_PORT', 20555), patch('core.config.TLS_PORT', 9555):
            result = await providers(request, {'key_id': 'fixture'})
        self.assertEqual(result['local_dashboard_url'], 'http://localhost:20555/dashboard')
        self.assertEqual(result['dashboard_url'], 'https://[fd00::1]:9555/dashboard')
