from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from .models import User
from django.contrib.auth.forms import PasswordChangeForm
from django.core.validators import RegexValidator
from .models import Profile

class CustomUserCreationForm(UserCreationForm):
    """
    Форма для регистрации нового пользователя
    """
    email = forms.EmailField(
        required=True,
        label='Email',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Введите email'})
    )
    username = forms.CharField(
        required=True,
        label='Логин',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Введите логин'})
    )
    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Введите пароль'})
    )
    password2 = forms.CharField(
        label='Подтверждение пароля',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Подтвердите пароль'})
    )
    first_name = forms.CharField(
        required=False,
        label='Имя',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Введите имя'})
    )
    last_name = forms.CharField(
        required=False,
        label='Фамилия',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Введите фамилию'})
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')

    def clean_email(self):
        """Проверка уникальности email"""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError('Пользователь с таким email уже существует')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class CustomUserChangeForm(UserChangeForm):
    """
    Форма для редактирования профиля пользователя
    """
    password = None  # Убираем поле пароля из формы

    class Meta:
        model = User
        fields = ('avatar', 'first_name', 'last_name', 'email', 'birth_date', 'bio')
        widgets = {
            'avatar': forms.FileInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Имя'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Фамилия'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'birth_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'О себе...'}),
        }

    def clean_email(self):
        """Проверка уникальности email при редактировании"""
        email = self.cleaned_data.get('email')
        user_id = self.instance.id

        # Проверяем, не занят ли email другим пользователем
        if User.objects.filter(email=email).exclude(id=user_id).exists():
            raise ValidationError('Пользователь с таким email уже существует')
        return email


class EmailVerificationForm(forms.Form):
    """
    Форма для ввода кода подтверждения
    """
    code = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        validators=[RegexValidator(r'^\d{6}$', 'Введите 6 цифр')],
        widget=forms.TextInput(attrs={
            'class': 'form-control code-input',
            'placeholder': '000000',
            'autocomplete': 'off',
            'maxlength': '6'
        }),
        label='Код подтверждения'
    )


class ResendCodeForm(forms.Form):
    """
    Форма для повторной отправки кода
    """
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ваш email'
        }),
        label='Email'
    )


class ProfileEditForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=False,
                                 widget=forms.TextInput(attrs={'class': 'form-input'}))
    last_name = forms.CharField(max_length=30, required=False,
                                widget=forms.TextInput(attrs={'class': 'form-input'}))
    email = forms.EmailField(required=True,
                             widget=forms.EmailInput(attrs={'class': 'form-input'}))

    class Meta:
        model = Profile
        fields = ['avatar', 'cover_image', 'bio', 'location', 'website',
                  'is_private', 'show_email']
        widgets = {
            'bio': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 4,
                'placeholder': 'Расскажите о себе...'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Город, страна'
            }),
            'website': forms.URLInput(attrs={
                'class': 'form-input',
                'placeholder': 'https://...'
            }),
            'avatar': forms.FileInput(attrs={
                'class': 'form-input',
                'accept': 'image/*'
            }),
            'cover_image': forms.FileInput(attrs={
                'class': 'form-input',
                'accept': 'image/*'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name
            self.fields['email'].initial = self.user.email

    def save(self, commit=True):
        profile = super().save(commit=False)

        if self.user:
            self.user.first_name = self.cleaned_data['first_name']
            self.user.last_name = self.cleaned_data['last_name']
            self.user.email = self.cleaned_data['email']
            if commit:
                self.user.save()

        if commit:
            profile.save()
        return profile


class CustomPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Текущий пароль'
        })
    )
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Новый пароль'
        })
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Подтвердите пароль'
        })
    )