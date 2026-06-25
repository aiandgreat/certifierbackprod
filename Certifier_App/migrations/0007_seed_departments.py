from django.db import migrations

def seed_departments(apps, schema_editor):
    Department = apps.get_model('Certifier_App', 'Department')
    departments_data = [
        {"name": "College of Information Technology", "abbreviation": "CIT"},
        {"name": "School of Arts and Sciences", "abbreviation": "SAS"},
        {"name": "College of Accountancy", "abbreviation": "COA"},
        {"name": "School of Business and Public Administration", "abbreviation": "SBPA"},
        {"name": "College of Engineering and Architecture", "abbreviation": "CEA"},
        {"name": "College of Nursing and Pharmacy", "abbreviation": "CONP"},
        {"name": "School of Education", "abbreviation": "SEd"},
        {"name": "College of Hospitality and Tourism Management", "abbreviation": "CHTM"},
    ]
    for dept in departments_data:
        Department.objects.get_or_create(
            name=dept["name"],
            defaults={"abbreviation": dept["abbreviation"]}
        )

def rollback_departments(apps, schema_editor):
    Department = apps.get_model('Certifier_App', 'Department')
    Department.objects.filter(abbreviation__in=["CIT", "SAS", "COA", "SBPA", "CEA", "CONP", "SEd", "CHTM"]).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('Certifier_App', '0006_department_alter_user_role_certificate_department_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_departments, rollback_departments),
    ]
