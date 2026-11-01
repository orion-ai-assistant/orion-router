"""The Router's PostgreSQL passwords are its own: random, created once, never the old fixed one."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bin import common


class PostgresPasswordTests(unittest.TestCase):
    def test_created_once_and_kept(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch('core.runtime_layout.data_root', return_value=Path(folder)):
            first = common.database_passwords()
            self.assertEqual(first, common.database_passwords())
            self.assertNotEqual(first['admin'], first['app'])
            self.assertNotIn('router_pass', first.values())
            saved = json.loads((Path(folder) / 'persistent/postgres.json').read_text(encoding='utf-8'))
            self.assertEqual(saved, first)

    def test_unreadable_file_gets_new_passwords(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch('core.runtime_layout.data_root', return_value=Path(folder)):
            (Path(folder) / 'persistent').mkdir()
            (Path(folder) / 'persistent/postgres.json').write_text('{', encoding='utf-8')
            self.assertTrue(common.database_passwords()['app'])

    def test_prod_uses_the_app_role_not_the_superuser(self):
        source = (ROOT / 'bin/prod.py').read_text(encoding='utf-8')
        self.assertNotIn('router_pass', source)
        self.assertIn('set_env(router_port, PG_PORT, PG_DB, PG_APP_USER, passwords["app"], "0")', source)
        self.assertIn('postgres_auth.secure(pg, admin, app, PG_DB)', source)


if __name__ == '__main__':
    unittest.main()
