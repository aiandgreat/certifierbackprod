from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Certificate, Template, BulkUpload, Department

# ================= USER ADMIN =================
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {
            'fields': (
                'username',
                'email',
                'password',
                'first_name',
                'last_name',
                'role',
                'department',
            )
        }),
        ('Permissions', {
            'fields': (
                'is_staff',
                'is_superuser',
                'is_active',
                'groups',
                'user_permissions',
            )
        }),
        ('Important dates', {
            'fields': ('last_login', 'date_joined')
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username',
                'email',
                'password1',
                'password2',
                'role',
                'department',
                'is_staff',
                'is_superuser',
                'is_active',
            ),
        }),
    )

    list_display = ('username', 'email', 'role', 'department', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('username',)

    def save_model(self, request, obj, form, change):
        # Automatically give staff/superuser for role='admin'
        if obj.role == 'admin':
            obj.is_staff = True
            obj.is_superuser = True
        super().save_model(request, obj, form, change)


# ================= DEPARTMENT ADMIN =================
@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'abbreviation')
    search_fields = ('name', 'abbreviation')


# ================= REGISTER MODELS =================
admin.site.register(User, UserAdmin)
admin.site.register(Certificate)
admin.site.register(Template)
admin.site.register(BulkUpload)