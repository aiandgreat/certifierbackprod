from django.db import models
import hashlib
from django.conf import settings
import uuid
from django.contrib.auth.models import AbstractUser


# ================= DEPARTMENT ==================================================
class Department(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    abbreviation = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"


# ================= USER ========================================================
class User(AbstractUser):
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=[
        ('student', 'Student'),
        ('admin', 'Administrator'),
        ('sub_admin', 'Sub-Administrator')
    ])
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users'
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.username


# ================= TEMPLATE =====================================================
class Template(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255)

    background = models.FileField(upload_to='templates/')

    signature_image = models.ImageField(
        upload_to='templates/signatures/',
        null=True,
        blank=True
    )

    event_logo = models.ImageField(
        upload_to='templates/event_logos/',
        null=True,
        blank=True
    )

    placeholders = models.JSONField()

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='templates'
    )

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# ================= CERTIFICATE =================================================
def generate_certificate_id():
    return f"CERT-{uuid.uuid4().hex[:8].upper()}"

class Certificate(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    certificate_id = models.CharField(
        max_length=100,
        unique=True,
        default=generate_certificate_id,
    )

    template = models.ForeignKey(
        Template,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='certificates'
    )

    title = models.CharField(max_length=255)
    full_name = models.CharField(max_length=255)
    course = models.CharField(max_length=255)
    issued_by = models.CharField(max_length=255)
    date_issued = models.DateField()

    # 🔐 EdDSA
    signature = models.TextField()
    public_key = models.TextField()
    data_hash = models.TextField()
    original_data_hash = models.TextField(null=True, blank=True) # ADD original_data_hash

    STATUS_CHOICES = (
        ('VALID', 'Valid'),
        ('INVALID', 'Invalid'),
        ('REVOKED', 'Revoked'),
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='VALID')

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='certificates'
    )
    recipient_email = models.EmailField(null=True, blank=True, db_index=True)

    file = models.FileField(upload_to='certificates/', null=True, blank=True)

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='certificates'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_data_string(self):
        return f"{self.title}|{self.full_name}|{self.course}|{self.issued_by}|{self.date_issued}|{self.certificate_id}"
    
    def save(self, *args, **kwargs):
        """
        Override save to detect when editable certificate data has been changed
        compared to the original signed hash. If the current data no longer
        matches `original_data_hash`, mark the certificate as INVALID.

        Also ensures the department is automatically copied from the template.
        """
        if self.template and not self.department:
            self.department = self.template.department

        # Only run the tamper check for existing records that have an original hash
        if self.pk and self.original_data_hash:
            try:
                # Load current DB state (pre-save) to distinguish creates
                orig = Certificate.objects.get(pk=self.pk)
            except Certificate.DoesNotExist:
                orig = None

            if orig is not None:
                # Compute hash for the *new* data about to be saved
                current_hash = hashlib.sha256(self.get_data_string().encode()).hexdigest()
                if current_hash != self.original_data_hash:
                    # Data changed after signing -> mark as invalid
                    self.status = 'INVALID'

        super().save(*args, **kwargs)
    


# ================= BULK UPLOAD =================================================
class BulkUpload(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    csv_file = models.FileField(upload_to='csv_uploads/')

    # Link to template (IMPORTANT)
    template = models.ForeignKey(Template, on_delete=models.CASCADE)

    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    total_records = models.IntegerField(default=0)
    processed_records = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Upload {self.id} - {self.status}"


# ================= SIGNALS =====================================================
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=User)
def claim_certificates_for_new_user(sender, instance, created, **kwargs):
    """
    Automatically search for and assign certificates to a newly registered user
    if their email matches the recipient_email field of any unclaimed certificates.
    """
    if created and instance.role == 'student':
        Certificate.objects.filter(recipient_email__iexact=instance.email, owner__isnull=True).update(owner=instance)


@receiver(post_delete, sender=Template)
def delete_template_files(sender, instance, **kwargs):
    """
    Automatically delete background, signature_image, and event_logo files
    from storage when a Template is deleted.
    """
    if instance.background:
        try:
            instance.background.delete(save=False)
        except Exception:
            pass
    if instance.signature_image:
        try:
            instance.signature_image.delete(save=False)
        except Exception:
            pass
    if instance.event_logo:
        try:
            instance.event_logo.delete(save=False)
        except Exception:
            pass


@receiver(post_delete, sender=Certificate)
def delete_certificate_file(sender, instance, **kwargs):
    """
    Automatically delete the certificate PDF file from storage when a Certificate is deleted.
    """
    if instance.file:
        try:
            instance.file.delete(save=False)
        except Exception:
            pass


@receiver(post_delete, sender=BulkUpload)
def delete_bulkupload_file(sender, instance, **kwargs):
    """
    Automatically delete the CSV file from storage when a BulkUpload is deleted.
    """
    if instance.csv_file:
        try:
            instance.csv_file.delete(save=False)
        except Exception:
            pass