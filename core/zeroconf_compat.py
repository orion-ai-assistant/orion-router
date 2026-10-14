"""Compatibility for the duplicate-expiration bug in zeroconf 0.151.5."""
import zeroconf
from zeroconf import _core
from zeroconf._cache import DNSCache
from zeroconf.asyncio import AsyncZeroconf


class _UniqueExpirationCache(DNSCache):
    def async_remove_records(self, entries):
        # A TTL can change A -> B -> A before cleanup. Both A heap entries
        # then expire together; removing the same record twice raises KeyError.
        super().async_remove_records(dict.fromkeys(entries))

    def async_expire(self, now):
        # Also send just one removal notification per expired record.
        return list(dict.fromkeys(super().async_expire(now)))


if zeroconf.__version__ == '0.151.5':
    # Set the constructor before Zeroconf creates its cache and handlers: they
    # must all share the same object. Keep upstream's size limits/TTL policy.
    # Do not apply this private-API workaround to untested future versions.
    _core.DNSCache = _UniqueExpirationCache
