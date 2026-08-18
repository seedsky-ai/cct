#!/usr/bin/env python3
"""Encrypted key storage — plaintext `.key` → passphrase-encrypted `.key.enc`.

Design trade-offs (stated up front, so nobody mistakes this for stronger protection than it is):
  · What is encrypted is the **file at rest**. While the process runs the key is inevitably in
    memory in plaintext — no local service can dodge that. What it does defend against: the file
    being copied by mistake, committed by mistake, read by another account on the same box,
    or leaking out with a backup.
  · Passphrase source, one of three, in priority order: the `DA_KEY_PASS` env var → the file
    `DA_KEY_PASSFILE` points at → interactive getpass (only when a tty exists).
    **The passphrase must never land on disk in the same directory**, or it is not encryption.
  · Algorithm: PBKDF2-HMAC-SHA256 (480,000 iterations, 16-byte random salt) derivation →
    Fernet (AES-128-CBC + HMAC). Salt sits in the same file as the ciphertext, the passphrase
    stays outside. This is the standard recipe, no home-grown cryptography.

Usage:
    python3 keystore.py encrypt                 # read .key, write .key.enc, prompt to rm plaintext
    python3 keystore.py decrypt                 # print the plaintext (for verification)
    python3 keystore.py check                   # only check it decrypts, do not print the key
    python3 keystore.py fp                      # fingerprint only (safe to share / telemetry)
    from keystore import load_key; k = load_key()   # this is how programs use it
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
PLAIN = Path(os.environ.get("DA_KEY_FILE", DIR / ".key"))
ENC = Path(os.environ.get("DA_KEY_ENC", DIR / ".key.enc"))
ROUNDS = 480_000


def _passphrase(prompt: str = "key passphrase: ") -> str:
    p = os.environ.get("DA_KEY_PASS")
    if p:
        return p
    pf = os.environ.get("DA_KEY_PASSFILE")
    if pf and Path(pf).exists():
        return Path(pf).read_text(encoding="utf-8").strip()
    if sys.stdin.isatty():
        import getpass
        return getpass.getpass(prompt)
    raise SystemExit("passphrase required: set DA_KEY_PASS or DA_KEY_PASSFILE "
                     "(do not put it inside the deepseek/ directory)")


def _fernet(passphrase: str, salt: bytes):
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ROUNDS)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(passphrase.encode())))


def encrypt(plain: str | None = None) -> Path:
    key = plain if plain is not None else PLAIN.read_text(encoding="utf-8").strip()
    salt = os.urandom(16)
    token = _fernet(_passphrase("set passphrase: "), salt).encrypt(key.encode())
    ENC.write_bytes(b"DSKEY1\n" + base64.b64encode(salt) + b"\n" + token)
    ENC.chmod(0o600)
    return ENC


def load_key() -> str:
    """The one entry point programs use to get the key. Ciphertext first; only when no
    ciphertext exists does it fall back to plaintext, with a warning."""
    if ENC.exists():
        raw = ENC.read_bytes().split(b"\n", 2)
        if raw[0] != b"DSKEY1":
            raise SystemExit(f"{ENC} format not recognized")
        salt, token = base64.b64decode(raw[1]), raw[2]
        return _fernet(_passphrase(), salt).decrypt(token).decode()
    if PLAIN.exists():
        print(f"⚠ still using the plaintext key {PLAIN}; run "
              f"`python3 keystore.py encrypt` to switch to ciphertext", file=sys.stderr)
        return PLAIN.read_text(encoding="utf-8").strip()
    raise SystemExit(f"key not found: neither {ENC} nor {PLAIN}")


# ── fingerprint: the **irreversible** signal for remote telemetry / the ledger ───────────
# Purpose: to be able to answer afterwards "which key did this run use, and was it the same
#       one as the previous run", while **the key itself is neither stored nor sent out**.
# How: domain-separation prefix + SHA-256 → first 12 hex chars. The domain separation makes
#       this value hold for this purpose only; another purpose needs another domain string,
#       so the same value cannot be reused elsewhere as some other identity.
# Irreversibility: SHA-256 is one-way; an API key is itself a high-entropy string, so there
#       is no dictionary-attack surface.
# ⚠ The fingerprint **may** go into logs, into telemetry, into git; the key **never may**.
FP_DOMAIN = b"dsflash-relay/keyfp/v1|"


def fingerprint(key: str | None = None) -> str:
    import hashlib
    k = key if key is not None else load_key()
    return hashlib.sha256(FP_DOMAIN + k.encode()).hexdigest()[:12]


def masked(key: str | None = None) -> str:
    """Masked form for eyeball verification, showing only 4 characters at each end."""
    k = key if key is not None else load_key()
    return f"{k[:4]}…{k[-4:]}" if len(k) > 12 else "…"


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "encrypt":
        p = encrypt()
        print(f"✓ wrote {p}(600)")
        print(f"  self-check: decrypted length {len(load_key())} chars")
        print(f"  delete the plaintext only once verified: rm {PLAIN}")
        print("  ⚠ keep the passphrase **outside** deepseek/, or use only the DA_KEY_PASS env var")
    elif cmd == "decrypt":
        print(load_key())
    elif cmd == "check":
        k = load_key()
        print(f"✓ decrypts, length {len(k)}, from {'ciphertext' if ENC.exists() else 'plaintext'}")
        print(f"  fingerprint key_fp={fingerprint(k)}   masked {masked(k)}")
    elif cmd == "fp":
        print(fingerprint())
    else:
        raise SystemExit(__doc__)
