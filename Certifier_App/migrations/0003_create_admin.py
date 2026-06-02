from django.db import migrations
import os


def create_admin(apps, schema_editor):
    """Create a superuser from environment variables if ADMIN_PASSWORD is provided.

    This migration is idempotent: it will not recreate the user if it already exists.
    It reads `ADMIN_USERNAME`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` from the
    environment. If `ADMIN_PASSWORD` is not set, the migration is a no-op.
    """
    User = apps.get_model('Certifier_App', 'User')
    username = os.environ.get('ADMIN_USERNAME', 'admin')
    email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
    password = os.environ.get('ADMIN_PASSWORD')

    if not password:
        # No admin password provided — do nothing
        return

    # Avoid creating duplicates
    if User.objects.filter(username=username).exists():
        return

    # Create the superuser
    User.objects.create_superuser(username=username, email=email, password=password)


def noop(apps, schema_editor):
    # Reverse operation does nothing — safe to leave admin account
    return


class Migration(migrations.Migration):

    dependencies = [
        ('Certifier_App', '0002_alter_certificate_certificate_id'),
    ]

    operations = [
        migrations.RunPython(create_admin, noop),
    ]
