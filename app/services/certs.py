"""Kendi imzalı HTTPS sertifikası.

Neden HTTPS? (1) Tarayıcılar mikrofona yalnızca https veya localhost'ta izin verir;
LAN'daki http adreslerinde bas-konuş çalışmaz. (2) Şifreler ağda düz metin gitmez.

Sertifika sunucunun adını ve LAN IP'lerini içerir. Sunucunun IP'si değişirse
`python -m scripts.make_cert --force` ile yenilenmelidir.
"""
import datetime
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.core.config import settings


def local_ips() -> list[str]:
    ips = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:  # varsayılan çıkış arayüzünün IP'si (gerçek veri göndermez)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(ips)


def cert_paths() -> tuple[Path, Path]:
    return settings.certs_dir / "server.crt", settings.certs_dir / "server.key"


def ensure_cert(force: bool = False) -> tuple[Path, Path]:
    crt, key = cert_paths()
    if crt.exists() and key.exists() and not force:
        return crt, key
    settings.certs_dir.mkdir(parents=True, exist_ok=True)

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    host = socket.gethostname()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Ofis Asistani")])
    san = [x509.DNSName("localhost"), x509.DNSName(host)]
    san += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in local_ips()]
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(private.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private, hashes.SHA256())
    )
    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key.write_bytes(private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    return crt, key
