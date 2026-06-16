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
