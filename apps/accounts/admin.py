from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser
from .forms import CustomUserCreationForm, CustomUserChangeForm


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser

    list_display = (
        'username',
        'email',
        'role',
        'employee_id',
        'department',
        'is_active',
        'is_staff',
        'date_joined',
    )
    list_filter = ('role', 'is_active', 'is_staff', 'department')
    search_fields = ('username', 'email', 'employee_id', 'first_name', 'last_name')
    ordering = ('-date_joined',)

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email', 'phone_number')}),
        ('NIT Role & Staff Details', {'fields': ('role', 'employee_id', 'department')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': (
                    'email',
                    'username',
                    'password',
                    'role',
                    'employee_id',
                    'department',
                    'first_name',
                    'last_name',
                    'is_staff',
                    'is_active',
                ),
            },
        ),
    )
