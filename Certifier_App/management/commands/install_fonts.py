from django.core.management.base import BaseCommand
from django.conf import settings
import os
from urllib.request import urlopen, Request

# Google Fonts raw URLs for Poppins variants (woff2/ttf fallback)
FONT_SOURCES = {
    'Poppins-Regular.ttf': 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf',
    'Poppins-Bold.ttf': 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf',
    'Poppins-Italic.ttf': 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Italic.ttf',
    'Poppins-BoldItalic.ttf': 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-BoldItalic.ttf',
}


def _download_file(url, dest_path):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req) as resp, open(dest_path, 'wb') as out:
        out.write(resp.read())


class Command(BaseCommand):
    help = 'Downloads Poppins font variants into project static/fonts (if writable).'

    def add_arguments(self, parser):
        parser.add_argument('--dest', help='Relative destination folder (default: static/fonts)', default='static/fonts')
        parser.add_argument('--extra', action='append', default=[],
                            help='Extra font sources to download. Can be repeated. Format: <url> or <filename.ttf>=<url>')

    def handle(self, *args, **options):
        dest_folder = options.get('dest') or 'static/fonts'

        base_dir = getattr(settings, 'BASE_DIR', None)
        if not base_dir:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

        dest_path = os.path.normpath(os.path.join(base_dir, dest_folder))

        self.stdout.write(f"Downloading Poppins fonts → {dest_path}")
        success = []
        failures = []
        # First download bundled FONT_SOURCES
        for fname, url in FONT_SOURCES.items():
            out_file = os.path.join(dest_path, fname)
            try:
                _download_file(url, out_file)
                success.append(fname)
            except Exception as exc:
                failures.append((fname, str(exc)))

        # Then process extra fonts provided by user (allow multiple)
        for item in options.get('extra') or []:
            if '=' in item:
                name, url = item.split('=', 1)
                name = name.strip()
            else:
                url = item.strip()
                name = os.path.basename(url.split('?')[0]) or None

            if not name:
                # fallback filename
                name = f"font_{len(success) + len(failures) + 1}.ttf"

            out_file = os.path.join(dest_path, name)
            try:
                _download_file(url, out_file)
                success.append(name)
            except Exception as exc:
                failures.append((name, str(exc)))

        if success:
            self.stdout.write(self.style.SUCCESS(f"Downloaded: {', '.join(success)}"))
        if failures:
            for f, e in failures:
                self.stderr.write(self.style.ERROR(f"Failed {f}: {e}"))
            raise SystemExit(1)
