from django.core.management.base import BaseCommand
from nacl.signing import SigningKey


class Command(BaseCommand):
    help = 'Generates a persistent Ed25519 signing key for CERT_EDDSA_SIGNING_KEY.'

    def handle(self, *args, **options):
        signing_key = SigningKey.generate()
        private_key_hex = signing_key.encode().hex()
        public_key_hex = signing_key.verify_key.encode().hex()

        self.stdout.write('Use the following value for CERT_EDDSA_SIGNING_KEY:')
        self.stdout.write(private_key_hex)
        self.stdout.write('Public key (keep for verification reference):')
        self.stdout.write(public_key_hex)