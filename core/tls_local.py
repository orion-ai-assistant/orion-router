"""Local maintenance probes trust only the persisted Router certificate."""
import ssl
import urllib.request
from core import config


def open_health(url: str, timeout: float = 1.0):
    if not url.startswith('https://'):
        raise ValueError('Router probes require HTTPS')
    context = ssl.create_default_context(cafile=str(config.TLS_DIRECTORY / 'certificate.pem'))
    return urllib.request.urlopen(url, timeout=timeout, context=context)


if __name__ == '__main__':
    from core.mdns import router_id
    from core.tls_identity import load_identity
    identity = load_identity(config.TLS_DIRECTORY, router_id(config.MDNS_ID_FILE))
    print('Router HTTPS identity ready; Windows certificate store unchanged.')
    print('UUID:', identity.id)
    print('SPKI SHA-256:', identity.fp)
