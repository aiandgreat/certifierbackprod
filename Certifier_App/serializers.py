import hashlib
import json
import logging
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model

from .models import Template, Certificate, BulkUpload
from .utils.eddsa import sign_data, VERIFY_KEY
from .utils.pdf_renderer import generate_and_attach_certificate_pdf

User = get_user_model()
logger = logging.getLogger(__name__)

# ================= CUSTOM JWT TOKEN SERIALIZER =================
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom serializer that includes user role and full_name in token response
    """
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user_id'] = self.user.id
        data['email'] = self.user.email
        data['username'] = self.user.username
        data['role'] = self.user.role
        data['full_name'] = f"{self.user.first_name} {self.user.last_name}".strip() or self.user.username
        return data


# ================= USER =================
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'role', 'password']
        extra_kwargs = {'password': {'write_only': True, 'required': False}}

    def update(self, instance, validated_data):
        # Kunin ang password at tanggalin sa validated_data
        password = validated_data.pop('password', None)
        
        # I-update ang ibang fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Eto ang pinaka-importante:
        if password:
            instance.set_password(password) # Hina-hash nito ang password
            
        instance.save()
        return instance


# ================= TEMPLATE =================
class TemplateSerializer(serializers.ModelSerializer):
    placeholders = serializers.JSONField(required=False)

    class Meta:
        model = Template
        fields = '__all__'
        read_only_fields = ['id', 'created_by', 'created_at']

    def validate_placeholders(self, value):
        # Normalize empty values so template upload does not fail with server errors.
        if value in (None, ''):
            return {'markers': []}

        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError('placeholders must be valid JSON.') from exc

        if not isinstance(value, dict):
            raise serializers.ValidationError('placeholders must be a JSON object.')

        markers = value.get('markers', [])
        if markers is None:
            value['markers'] = []
        elif not isinstance(markers, list):
            raise serializers.ValidationError("placeholders.markers must be a list.")

        # Normalize each marker to ensure font-related fields are preserved
        normalized = []
        try:
            for m in value.get('markers', []):
                if not isinstance(m, dict):
                    continue
                marker = dict(m)  # shallow copy so we don't mutate input

                # Font-related defaults (frontend will provide these, but ensure fallbacks)
                marker.setdefault('fontFamily', marker.get('fontFamily') or 'Helvetica')
                marker.setdefault('fontStyle', marker.get('fontStyle') or 'normal')
                marker.setdefault('fontWeight', marker.get('fontWeight') or 'normal')
                marker.setdefault('fontSize', marker.get('fontSize') or 24)
                marker.setdefault('color', marker.get('color') or '#000000')
                marker.setdefault('align', marker.get('align') or 'left')

                # Coerce numeric fontSize if possible
                try:
                    marker['fontSize'] = float(marker['fontSize'])
                except Exception:
                    marker['fontSize'] = 24.0

                normalized.append(marker)
        except Exception as e:
            logger.error(f"Error normalizing placeholders: {e}")
            # If normalization fails, we still want to return a valid object if possible
            # or at least not crash.
            if not normalized and markers:
                return value

        value['markers'] = normalized

        return value

    def create(self, validated_data):
        validated_data.setdefault('placeholders', {'markers': []})
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'placeholders' in validated_data and validated_data['placeholders'] in (None, ''):
            validated_data['placeholders'] = {'markers': []}
        return super().update(instance, validated_data)


# ================= CERTIFICATE =================
class CertificateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Certificate
        fields = '__all__'


class CertificateCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Certificate
        fields = [
            'template',
            'title',
            'full_name',
            'course',
            'issued_by',
            'date_issued',
            'owner'
        ]

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user

        # Remove duplicate fields just in case
        validated_data.pop('created_by', None)

        # ✅ CREATE CERTIFICATE
        cert = Certificate.objects.create(
            created_by=user,
            **validated_data
        )

        # ✅ CONSISTENT DATA STRING
        data_string = cert.get_data_string()

        # ✅ HASH (TAMPER CHECK)
        data_hash = hashlib.sha256(data_string.encode()).hexdigest()
        cert.data_hash = data_hash
        cert.original_data_hash = data_hash

        # ✅ SIGNATURE (EdDSA)
        cert.signature = sign_data(data_string)

        # ✅ STORE PUBLIC KEY
        cert.public_key = VERIFY_KEY.encode().hex()

        # Save before PDF
        cert.save()

        # Render using template background + placeholders when available.
        generate_and_attach_certificate_pdf(cert)

        return cert


# ================= CERTIFICATE PREVIEW =================
class CertificatePreviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Certificate
        fields = [
            'certificate_id',
            'title',
            'full_name',
            'course',
            'issued_by',
            'date_issued'
        ]


# ================= CERTIFICATE VERIFY =================
class CertificateVerifySerializer(serializers.ModelSerializer):
    class Meta:
        model = Certificate
        fields = [
            'certificate_id',
            'full_name',
            'course',
            'issued_by',
            'date_issued',
            'status'
        ]


# ================= BULK UPLOAD =================
class BulkUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = BulkUpload
        fields = '__all__'
        read_only_fields = [
            'id',
            'status',
            'total_records',
            'processed_records',
            'created_at'
        ]


class BulkUploadCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BulkUpload
        fields = ['id', 'csv_file', 'template']

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user

        validated_data.pop('uploaded_by', None)

        return BulkUpload.objects.create(
            uploaded_by=user,
            **validated_data
        )