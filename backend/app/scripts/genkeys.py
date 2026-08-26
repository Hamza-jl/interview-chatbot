"""Generate the three cryptographic secrets and, optionally, write a .env file.

    python -m app.scripts.genkeys           # print to stdout
    python -m app.scripts.genkeys --write   # create .env from .env.example
"""
from __future__ import annotations

import argparse
import base64
import os
import secrets
import sys

# name -> byte length. JWT_SECRET is 64 bytes to match HS512.
KEYS = {"MASTER_KEK": 32, "JWT_SECRET": 64, "DOWNLOAD_SIGNING_KEY": 32}


def generate() -> dict[str, str]:
    return {name: base64.b64encode(secrets.token_bytes(n)).decode() for name, n in KEYS.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate cryptographic secrets")
    parser.add_argument("--write", action="store_true", help="write ./.env (never overwrites)")
    parser.add_argument("--force", action="store_true", help="allow overwriting an existing .env")
    args = parser.parse_args()

    values = generate()

    if not args.write:
        for name, value in values.items():
            print(f"{name}={value}")
        return 0

    if os.path.exists(".env") and not args.force:
        print(
            "Refus : .env existe deja. Regenerer les cles rendrait ILLISIBLES toutes les "
            "donnees chiffrees existantes. Utiliser --force en connaissance de cause.",
            file=sys.stderr,
        )
        return 1

    if not os.path.exists(".env.example"):
        print("Fichier .env.example introuvable.", file=sys.stderr)
        return 1

    with open(".env.example", "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        out.append(f"{key}={values[key]}\n" if key in values else line)

    with open(".env", "w", encoding="utf-8") as handle:
        handle.writelines(out)

    try:  # best effort on POSIX; a no-op on Windows
        os.chmod(".env", 0o600)
    except OSError:
        pass

    print("Ecrit : .env")
    print("Ajoutez votre ANTHROPIC_API_KEY, puis lancez : python -m app.scripts.seed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
