"""Create a public artifact from an explicit allowlist, never from the repo root."""
from pathlib import Path
import shutil

PUBLIC = ('index.html', 'config.js', 'sw.js', 'manifest.json', 'icon.svg',
          'icon-192.png', 'icon-512.png', 'apple-touch-icon.png')
BASE = Path(__file__).resolve().parent
OUT = BASE / 'pages-dist'

if __name__ == '__main__':
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for name in PUBLIC:
        shutil.copy2(BASE / name, OUT / name)
    (OUT / '.nojekyll').touch()
    print('Pages artifact:', OUT)
