"""HTTPS sertifikasını (yeniden) üretir.
    .venv\\Scripts\\python.exe -m scripts.make_cert --force
"""
import sys

from app.services.certs import ensure_cert, local_ips

crt, key = ensure_cert(force="--force" in sys.argv)
print("Sertifika:", crt)
print("Geçerli adresler:", ", ".join(local_ips()))
