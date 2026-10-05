"""Persistent P-256 identity; renewal never silently replaces a private key."""
import hashlib
import os
import tempfile
import socket
import ipaddress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def spki_fingerprint(public_key) -> str:
    return hashlib.sha256(public_key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )).hexdigest()


def browser_names():
    names = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
             x509.IPAddress(ipaddress.ip_address("::1"))]
    host = socket.gethostname()
    names.append(x509.DNSName(host))
    try:
        addresses = {entry[4][0].split("%")[0] for entry in socket.getaddrinfo(host, None)}
        for address in sorted(addresses):
            value = ipaddress.ip_address(address)
            if not value.is_loopback and not value.is_unspecified:
                names.append(x509.IPAddress(value))
    except socket.gaierror:
        pass
    return names


def _publish(path: Path, data: bytes, replace: bool = False):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        os.chmod(temporary, 0o600)
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
    try:
        if replace:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class TLSIdentity:
    id: str
    key_path: Path
    certificate_path: Path
    fp: str

    def payload(self, name: str):
        return {"v": 1, "id": self.id, "name": name, "fp": self.fp}


def load_identity(directory: Path, identity: str, *, now=None) -> TLSIdentity:
    directory.mkdir(parents=True, exist_ok=True)
    key_path, cert_path = directory / "private-key.pem", directory / "certificate.pem"
    if not key_path.exists():
        if cert_path.exists():
            raise ValueError("TLS private key missing beside existing certificate; explicit identity reset required")
        key = ec.generate_private_key(ec.SECP256R1())
        _publish(key_path, key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    # Invalid/unreadable keys fail closed and are never regenerated.
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("TLS identity must be an ECDSA P-256 key")
    fp = spki_fingerprint(key.public_key())
    now = now or datetime.now(timezone.utc)
    names = browser_names()
    renew = not cert_path.exists()
    if not renew:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        if spki_fingerprint(cert.public_key()) != fp:
            raise ValueError("TLS certificate/private key mismatch; identity retained")
        expiry = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after.replace(tzinfo=timezone.utc)
        renew = expiry <= now
        try:
            existing = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            renew = renew or not set(names).issubset(set(existing))
        except x509.ExtensionNotFound:
            renew = True
    if renew:
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Orion Router {identity}")])
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365*50))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName(names), critical=False)
            .sign(key, hashes.SHA256()))
        _publish(cert_path, cert.public_bytes(serialization.Encoding.PEM), replace=cert_path.exists())
    return TLSIdentity(identity, key_path, cert_path, fp)
