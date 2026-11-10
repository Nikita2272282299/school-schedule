"""Create a public artifact from an explicit allowlist, never from the repo root."""
from pathlib import Path
import shutil

import version_stamp

PUBLIC = ('index.html', 'config.js', 'offline-data.js', 'sw.js', 'manifest.json',
          'icon.svg', 'icon-192.png', 'icon-512.png', 'apple-touch-icon.png',
          'assets/fonts/manrope-cyrillic-400-800-normal.woff2',
          'assets/fonts/manrope-latin-400-800-normal.woff2')
BASE = Path(__file__).resolve().parent
OUT = BASE / 'pages-dist'

if __name__ == '__main__':
    import materialize_assets
    materialize_assets.main()
    # Чистим артефакт по файлам, а не rmtree: предыдущая сборка не теряется
    # целиком, если один файл занят, и не требует прав на удаление каталога.
    OUT.mkdir(parents=True, exist_ok=True)
    for old in sorted(OUT.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        if old.is_file():
            try:
                old.unlink()
            except OSError as e:
                print('не удалось удалить', old.name, e)
        elif old.is_dir():
            try:
                old.rmdir()
            except OSError:
                pass
    for name in PUBLIC:
        dst = OUT / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASE / name, dst)
    (OUT / '.nojekyll').touch()
    number = version_stamp.build_number()
    if number:
        version_stamp.stamp(OUT / 'index.html', number)
        print('Версия сборки:', number)
    else:
        print('Версия сборки: оставлена из index.html (git недоступен)')
    print('Pages artifact:', OUT)
