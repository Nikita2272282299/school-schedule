"""Restore tested binary public assets from their lossless text source."""
from pathlib import Path
import base64
import json

BASE = Path(__file__).resolve().parent

def main():
    assets = json.loads((BASE / 'public-assets.json').read_text())
    targets = (BASE, BASE.parent, BASE / 'pa-dist', BASE / 'hf-dist')
    for rel, encoded in assets.items():
        data = base64.b64decode(encoded, validate=True)
        for folder in targets:
            dest = folder / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or dest.read_bytes() != data:
                dest.write_bytes(data)
    print('Public icons and fonts restored')

if __name__ == '__main__':
    main()
