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


class DepartmentSubAdminRequirementsTestCase(APITestCase):
    def setUp(self):
        from .models import Department
        # Retrieve or create test departments (seeded via migration 0007)
        self.dept_cit, _ = Department.objects.get_or_create(
            name="College of Information Technology",
            defaults={"abbreviation": "CIT"}
        )
        self.dept_sas, _ = Department.objects.get_or_create(
            name="School of Arts and Sciences",
            defaults={"abbreviation": "SAS"}
        )
        
        # Create users
        self.admin = User.objects.create_superuser(
            email='admin@ua.edu.ph',
            username='admin',
            password='password',
            role='admin'
        )
        self.sub_admin_cit = User.objects.create_user(
            email='cit_sec@ua.edu.ph',
            username='cit_sec',
            password='password',
            role='sub_admin',
            department=self.dept_cit
        )
        self.sub_admin_sas = User.objects.create_user(
            email='sas_sec@ua.edu.ph',
            username='sas_sec',
            password='password',
            role='sub_admin',
            department=self.dept_sas
        )
        self.student = User.objects.create_user(
            email='student@ua.edu.ph',
            username='student',
            password='password',
            role='student'
        )

    def test_admin_create_department(self):
        self.client.force_authenticate(user=self.admin)
        url = '/api/departments/'
        data = {
            "name": "College of Computer Studies",
            "abbreviation": "CCS"
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['abbreviation'], 'CCS')

    def test_sub_admin_cannot_create_department(self):
        self.client.force_authenticate(user=self.sub_admin_cit)
        url = '/api/departments/'
        data = {
            "name": "College of Fine Arts",
            "abbreviation": "CFA"
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_must_provide_department_for_template(self):
        self.client.force_authenticate(user=self.admin)
        url = '/api/templates/'
        bg = SimpleUploadedFile("bg.png", b"file_content")
        data = {
            "name": "Admin Template",
            "background": bg,
            "placeholders": '{"markers": []}'
        }
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('department', response.data)

        # Successful creation with department
        bg.seek(0)
        data['department'] = str(self.dept_cit.id)
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_sub_admin_creates_template_inherits_department(self):
        self.client.force_authenticate(user=self.sub_admin_cit)
        url = '/api/templates/'
        bg = SimpleUploadedFile("bg.png", b"file_content")
        data = {
            "name": "CIT Template",
            "background": bg,
            "placeholders": '{"markers": []}'
        }
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(response.data['department']), str(self.dept_cit.id))

    def test_sub_admin_visibility_boundaries(self):
        # 1. CIT sub-admin creates template & certificate
        self.client.force_authenticate(user=self.sub_admin_cit)
        
        cit_template = Template.objects.create(
            name="CIT Cert Template",
            background=SimpleUploadedFile("bg.png", b"file_content"),
            placeholders={"markers": []},
            department=self.dept_cit,
            created_by=self.sub_admin_cit
        )
        
        # 2. SAS sub-admin creates template
        sas_template = Template.objects.create(
            name="SAS Cert Template",
            background=SimpleUploadedFile("bg.png", b"file_content"),
            placeholders={"markers": []},
            department=self.dept_sas,
            created_by=self.sub_admin_sas
        )

        # Let's check listing templates
        # CIT sub-admin should only see CIT templates
        response = self.client.get('/api/templates/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        template_ids = [t['id'] for t in response.data]
        self.assertIn(str(cit_template.id), template_ids)
        self.assertNotIn(str(sas_template.id), template_ids)

        # SAS sub-admin should only see SAS templates
        self.client.force_authenticate(user=self.sub_admin_sas)
        response = self.client.get('/api/templates/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        template_ids = [t['id'] for t in response.data]
        self.assertNotIn(str(cit_template.id), template_ids)
        self.assertIn(str(sas_template.id), template_ids)

        # Admin should see both
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/templates/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        template_ids = [t['id'] for t in response.data]
        self.assertIn(str(cit_template.id), template_ids)
        self.assertIn(str(sas_template.id), template_ids)

    def test_sub_admin_bulk_upload_inherits_department(self):
        # CIT Sub-admin uploads a template
        cit_template = Template.objects.create(
            name="CIT Cert Template",
            background=SimpleUploadedFile("bg.png", b"file_content"),
            placeholders={"markers": []},
            department=self.dept_cit,
            created_by=self.sub_admin_cit
        )

        # Force authenticate CIT Sub-admin
        self.client.force_authenticate(user=self.sub_admin_cit)

        # Create bulk upload entry
        from .models import BulkUpload
        upload = BulkUpload.objects.create(
            csv_file=SimpleUploadedFile("test.csv", b"title,full_name,course,issued_by,date_issued,email\nCIT Cert,Aian,BSCS,Dean,2026-06-25,student@ua.edu.ph\n"),
            template=cit_template,
            uploaded_by=self.sub_admin_cit
        )

        # Process the bulk upload
        from .views import run_bulk_upload_task
        reader_list = [{
            'title': 'CIT Cert',
            'full_name': 'Aian',
            'course': 'BSCS',
            'issued_by': 'Dean',
            'date_issued': '2026-06-25',
            'email': 'student@ua.edu.ph'
        }]
        
        run_bulk_upload_task(upload.id, self.sub_admin_cit.id, reader_list)

        # Verify generated certificate department is CIT
        from .models import Certificate
        cert = Certificate.objects.filter(recipient_email='student@ua.edu.ph').first()
        self.assertIsNotNone(cert)
        self.assertEqual(cert.department, self.dept_cit)
