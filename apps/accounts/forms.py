from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import CustomUser


class LoginForm(forms.Form):
    """
    Authentication form allowing users to sign in with either Email or Username.
    """
    username = forms.CharField(
        label="Email or Username",
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'demo@manuflow.app or staff ID',
            'autocomplete': 'username',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'rememberMeCheck'
        }),
        label="Remember this workstation"
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            self.user_cache = authenticate(self.request, username=username, password=password)
            if self.user_cache is None:
                raise forms.ValidationError(
                    "Invalid login credentials. Please check your email/username and password.",
                    code='invalid_login',
                )
            elif not self.user_cache.is_active:
                raise forms.ValidationError(
                    "This account has been deactivated. Please contact the System Administrator.",
                    code='inactive',
                )
        return self.cleaned_data

    def get_user(self):
        return self.user_cache


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ('email', 'username', 'first_name', 'last_name', 'role', 'employee_id', 'department', 'phone_number')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = ('email', 'username', 'first_name', 'last_name', 'role', 'employee_id', 'department', 'phone_number', 'is_active', 'is_staff')


class UserProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'phone_number', 'department')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
        }


class StaffUserCreateForm(forms.ModelForm):
    """
    Administrative form to provision a new employee account with role assignment.
    """
    password = forms.CharField(
        label="Account Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Minimum 8 characters'}),
        help_text="Password must contain at least 8 characters.",
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Re-enter password'}),
    )

    class Meta:
        model = CustomUser
        fields = (
            'email',
            'username',
            'first_name',
            'last_name',
            'role',
            'employee_id',
            'department',
            'phone_number',
            'is_active',
        )
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@company.com'}),
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. jsmith'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'employee_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. MF-EMP-105'}),
            'department': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Manufacturing Operations'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. +91 98765 43210'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An employee account with this email address already exists.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if CustomUser.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("An employee account with this username already exists.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        pwd = cleaned_data.get('password')
        confirm_pwd = cleaned_data.get('confirm_password')
        if pwd and confirm_pwd and pwd != confirm_pwd:
            self.add_error('confirm_password', "Passwords do not match.")
        if pwd and len(pwd) < 8:
            self.add_error('password', "Password must be at least 8 characters long.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if user.role == CustomUser.Role.ADMIN:
            user.is_staff = True
        if commit:
            user.save()
        return user


class StaffUserEditForm(forms.ModelForm):
    """
    Administrative form to edit employee profile, role, department, and active status.
    Supports optional password reset.
    """
    new_password = forms.CharField(
        label="Reset Password (Optional)",
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Leave blank to keep current password'}),
        help_text="Leave blank to retain employee's existing password.",
    )

    class Meta:
        model = CustomUser
        fields = (
            'email',
            'first_name',
            'last_name',
            'role',
            'employee_id',
            'department',
            'phone_number',
            'is_active',
        )
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'employee_id': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another employee account with this email address already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        new_pwd = self.cleaned_data.get('new_password')
        if new_pwd:
            user.set_password(new_pwd)
        if user.role == CustomUser.Role.ADMIN:
            user.is_staff = True
        elif not user.is_superuser:
            user.is_staff = False
        if commit:
            user.save()
        return user
