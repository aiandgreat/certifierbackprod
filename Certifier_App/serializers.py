import hashlib
import json
import logging
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model

from .models import Template, Certificate, BulkUpload, Department
from .utils.eddsa import sign_data, VERIFY_KEY
from .utils.pdf_renderer import generate_and_attach_certificate_pdf

User = get_user_model()
logger = logging.getLogger(__name__)

# ================= DEPARTMENT =================
class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = '__all__'


# ================= CUSTOM JWT TOKEN SERIALIZER =================
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom serializer that includes user role, full_name, and department details in token response
    """
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user_id'] = self.user.id
        data['email'] = self.user.email
        data['username'] = self.user.username
        data['role'] = self.user.role
        data['full_name'] = f"{self.user.first_name} {self.user.last_name}".strip() or self.user.username
        
        if self.user.department:
            data['department_id'] = str(self.user.department.id)
            data['department_name'] = self.user.department.name
            data['department_abbreviation'] = self.user.department.abbreviation
        else:
            data['department_id'] = None
            data['department_name'] = None
            data['department_abbreviation'] = None
        return data


# ================= USER =================
class UserSerializer(serializers.ModelSerializer):
    department_details = DepartmentSerializer(source='department', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'role', 'department', 'department_details', 'password']
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
    department_details = DepartmentSerializer(source='department', read_only=True)

    class Meta:
        model = Template
        fields = '__all__'
        read_only_fields = ['id', 'created_by', 'created_at']

    def validate(self, attrs):
        request = self.context.get('request')
        if request and request.user:
            user = request.user
            if user.role == 'sub_admin':
                attrs['department'] = user.department
            elif user.role == 'admin':
                if not self.instance and not attrs.get('department'):
                    raise serializers.ValidationError({"department": "This field is required for administrators."})
        return attrs

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
    template_details = serializers.SerializerMethodField(read_only=True)
    department_details = DepartmentSerializer(source='department', read_only=True)

    class Meta:
        model = Certificate
        fields = '__all__'

    def get_template_details(self, obj):
        if obj.template:
            request = self.context.get('request')
            event_logo_url = None
            if obj.template.event_logo:
                event_logo_url = obj.template.event_logo.url
                if request:
                    event_logo_url = request.build_absolute_uri(event_logo_url)
            return {
                'id': obj.template.id,
                'name': obj.template.name,
                'event_logo': event_logo_url,
                'department': obj.template.department.id if obj.template.department else None
            }
        return None


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
            'owner',
            'recipient_email',
            'department'
        ]

    def validate(self, attrs):
        request = self.context.get('request')
        if request and request.user:
            user = request.user
            template = attrs.get('template')
            if template and user.role == 'sub_admin':
                if template.department != user.department:
                    raise serializers.ValidationError({"template": "You can only issue certificates using templates from your department."})
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user

        # Remove duplicate fields just in case
        validated_data.pop('created_by', None)

        recipient_email = validated_data.get('recipient_email', '')
        if recipient_email:
            recipient_email = recipient_email.strip()
            validated_data['recipient_email'] = recipient_email
            
            if not validated_data.get('owner'):
                from django.contrib.auth import get_user_model
                User = get_user_model()
                recipient_user = User.objects.filter(email__iexact=recipient_email).first()
                if recipient_user:
                    validated_data['owner'] = recipient_user

        # Set default department from template if not provided
        template = validated_data.get('template')
        if template and not validated_data.get('department'):
            validated_data['department'] = template.department

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

    def validate(self, attrs):
        request = self.context.get('request')
        if request and request.user:
            user = request.user
            template = attrs.get('template')
            if template and user.role == 'sub_admin':
                if template.department != user.department:
                    raise serializers.ValidationError({"template": "You can only use templates from your department."})
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user

        validated_data.pop('uploaded_by', None)

        return BulkUpload.objects.create(
            uploaded_by=user,
            **validated_data
        )