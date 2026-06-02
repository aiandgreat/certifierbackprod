from django.apps import AppConfig
import os
from django.conf import settings


class CertifierAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Certifier_App'

    def ready(self):
        # Ensure media directories exist for template uploads
        media_root = getattr(settings, 'MEDIA_ROOT', None)
        if media_root:
            subdirs = ['templates', 'templates/signatures', 'certificates', 'csv_uploads']
            for subdir in subdirs:
                path = os.path.join(media_root, subdir)
                if not os.path.exists(path):
                    try:
                        os.makedirs(path, exist_ok=True)
                    except Exception as e:
                        print(f"Error creating directory {path}: {e}")
