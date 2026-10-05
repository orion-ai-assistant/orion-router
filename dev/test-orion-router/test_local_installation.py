import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core import local_installation
from core.tls_identity import load_identity
from core.mdns import router_id


class LocalInstallationTests(unittest.TestCase):
    def installation(self, root):
        uuid_file = root / 'persistent' / 'mdns-id'
        identity = load_identity(root / 'persistent' / 'tls', router_id(uuid_file))
        return identity, uuid_file

    def test_explicit_registration_contains_only_public_locator_and_survives_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity, uuid_file = self.installation(root)
            destination = root / 'profile' / 'router-installation.json'
            first = local_installation.register(root, identity, uuid_file, 9443, destination=destination)
            self.assertEqual(first['v'], 1)
            self.assertEqual(first['kind'], local_installation.KIND)
            self.assertEqual(first['certificate_path'], str(identity.certificate_path.resolve()))
            self.assertEqual(first['identity_path'], str(uuid_file.resolve()))
            self.assertNotIn('private', destination.read_text())
            self.assertNotIn('fp', first)
            self.assertTrue(local_installation.refresh_managed_installation(root, identity, uuid_file, 9445, destination=destination))
            self.assertEqual(json.loads(destination.read_text())['tls_port'], 9445)
            self.assertEqual(load_identity(identity.key_path.parent, identity.id).fp, identity.fp)
            self.assertEqual(list(destination.parent.iterdir()), [destination])

    def test_arbitrary_dev_root_cannot_claim_registration_or_replace_other_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            one, two = root/'one', root/'two'
            first, uuid_one = self.installation(one)
            second, uuid_two = self.installation(two)
            destination = root/'profile'/'router-installation.json'
            with patch.object(local_installation, 'native_default_root', return_value=root/'native'):
                self.assertFalse(local_installation.refresh_managed_installation(one, first, uuid_one, 9443, destination=destination))
            self.assertFalse(destination.exists())
            local_installation.register(one, first, uuid_one, 9443, destination=destination)
            saved = destination.read_bytes()
            self.assertFalse(local_installation.refresh_managed_installation(two, second, uuid_two, 9443, destination=destination))
            self.assertEqual(destination.read_bytes(), saved)

    def test_existing_native_installation_registers_on_startup_without_installer_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity, uuid_file = self.installation(root)
            destination = root/'profile'/'router-installation.json'
            with patch.object(local_installation, 'native_default_root', return_value=root):
                self.assertTrue(local_installation.refresh_managed_installation(root, identity, uuid_file, 9443, destination=destination))

    def test_identity_paths_outside_registered_root_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            one, two = root/'one', root/'two'
            first, uuid_file = self.installation(one)
            other, _ = self.installation(two)
            with self.assertRaises(ValueError):
                local_installation.register(one, other, uuid_file, 9443, destination=root/'manifest.json')


if __name__ == '__main__':
    unittest.main()
