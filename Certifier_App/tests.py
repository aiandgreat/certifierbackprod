from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from .models import User, Template, BulkUpload
from django.core.files.uploadedfile import SimpleUploadedFile

class BulkUploadDeleteTestCase(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email='admin@ua.edu.ph', 
            username='admin', 
            password='password', 
            role='admin'
        )
        self.client.force_authenticate(user=self.admin)
        
        # Setup dependencies
        self.template = Template.objects.create(
            name="Test Template",
            background=SimpleUploadedFile("bg.png", b"file_content"),
            placeholders={"markers": []},
            created_by=self.admin
        )
        self.upload = BulkUpload.objects.create(
            csv_file=SimpleUploadedFile("test.csv", b"col1,col2"),
            template=self.template,
            uploaded_by=self.admin
        )
        
    def test_delete_bulk_upload(self):
        url = f'/api/uploads/{self.upload.id}/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(BulkUpload.objects.filter(id=self.upload.id).exists())


class CertificateAutomationTestCase(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email='admin@ua.edu.ph', 
            username='admin', 
            password='password', 
            role='admin'
        )
        self.client.force_authenticate(user=self.admin)
        
        self.template = Template.objects.create(
            name="Test Template",
            background=SimpleUploadedFile("bg.png", b"file_content"),
            placeholders={"markers": []},
            created_by=self.admin
        )

    def test_bulk_upload_with_existing_user(self):
        # 1. Create a student user
        student = User.objects.create_user(
            email='student1@ua.edu.ph',
            username='student1',
            password='password',
            role='student'
        )
        
        # 2. Setup bulk upload with CSV data
        upload = BulkUpload.objects.create(
            csv_file=SimpleUploadedFile("test.csv", b"title,full_name,course,issued_by,date_issued,email\nCert,Juan,BSCS,Dean,2026-06-24,student1@ua.edu.ph\n"),
            template=self.template,
            uploaded_by=self.admin
        )
        
        # 3. Process the CSV rows synchronously
        from .views import run_bulk_upload_task
        reader_list = [
            {
                'title': 'Cert',
                'full_name': 'Juan',
                'course': 'BSCS',
                'issued_by': 'Dean',
                'date_issued': '2026-06-24',
                'email': 'student1@ua.edu.ph'
            }
        ]
        
        run_bulk_upload_task(upload.id, self.admin.id, reader_list)
        
        # 4. Verify owner assignment
        from .models import Certificate
        cert = Certificate.objects.filter(recipient_email='student1@ua.edu.ph').first()
        self.assertIsNotNone(cert)
        self.assertEqual(cert.owner, student)
        self.assertEqual(cert.recipient_email, 'student1@ua.edu.ph')

    def test_bulk_upload_with_non_existent_user_and_subsequent_registration(self):
        # 1. Setup bulk upload with student who is not yet registered
        upload = BulkUpload.objects.create(
            csv_file=SimpleUploadedFile("test.csv", b"title,full_name,course,issued_by,date_issued,email\nCert2,Jose,BSCS,Dean,2026-06-24,student2@ua.edu.ph\n"),
            template=self.template,
            uploaded_by=self.admin
        )
        
        # 2. Process CSV
        from .views import run_bulk_upload_task
        reader_list = [
            {
                'title': 'Cert2',
                'full_name': 'Jose',
                'course': 'BSCS',
                'issued_by': 'Dean',
                'date_issued': '2026-06-24',
                'email': 'student2@ua.edu.ph'
            }
        ]
        
        run_bulk_upload_task(upload.id, self.admin.id, reader_list)
        
        # 3. Verify certificate is created but has no owner
        from .models import Certificate
        cert = Certificate.objects.filter(recipient_email='student2@ua.edu.ph').first()
        self.assertIsNone(cert.owner)
        self.assertEqual(cert.recipient_email, 'student2@ua.edu.ph')
        
        # 4. Register the student later
        student = User.objects.create_user(
            email='student2@ua.edu.ph',
            username='student2',
            password='password',
            role='student'
        )
        
        # 5. Verify the certificate is now automatically owned by the registered student
        cert.refresh_from_db()
        self.assertEqual(cert.owner, student)

    def test_google_oauth_name_parsing(self):
        from .views import get_or_create_user_from_google
        
        # Test full name with multiple first/middle names and one last name
        google_data = {
            'email': 'aian.jae@ua.edu.ph',
            'name': 'AIAN JAE S. GARCIA'
        }
        user, created = get_or_create_user_from_google(google_data)
        self.assertEqual(user.first_name, 'AIAN JAE S.')
        self.assertEqual(user.last_name, 'GARCIA')
