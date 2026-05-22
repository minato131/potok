from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from .models import User
from django.contrib.auth.forms import PasswordChangeForm
from django.core.validators import RegexValidator
from .models import Profile

from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from .models import User
from django.contrib.auth.forms import PasswordChangeForm
from django.core.validators import RegexValidator, EmailValidator
from .models import Profile
import re

# Список запрещённых доменов (временные почты)
BLOCKED_EMAIL_DOMAINS = [
    'tempmail.com', '10minutemail.com', 'guerrillamail.com',
    'mailinator.com', 'yopmail.com', 'throwawaymail.com',
    'temp-mail.org', 'fakeinbox.com', 'trashmail.com',
    'getairmail.com', 'sharklasers.com', 'guerrillamail.net',
    'tempinbox.com', 'throwaway.email', 'fakemailgenerator.com',
    'emailondeck.com', 'getnada.com', 'mailnator.com'
]


def validate_email_format(value):
    """Проверка формата email"""
    # Базовая проверка через EmailValidator
    EmailValidator(message='Введите корректный email адрес')(value)

    # Дополнительная проверка на недопустимые символы
    if '..' in value:
        raise ValidationError('Email содержит недопустимые символы')

    # Проверка длины
    if len(value) > 100:
        raise ValidationError('Email не может быть длиннее 100 символов')

    # Проверка на недопустимые домены верхнего уровня
    allowed_tlds = ['com', 'ru', 'net', 'org', 'ua', 'by', 'kz', 'fr', 'de', 'it', 'es', 'uk', 'pl', 'ca', 'au', 'jp',
                    'kr', 'br', 'in', 'nl', 'se', 'no', 'dk', 'fi', 'ch', 'be', 'at', 'cz', 'gr', 'hu', 'ie', 'il',
                    'mx', 'nz', 'ph', 'sg', 'tr', 'vn', 'za', 'ro', 'hr', 'lt', 'lv', 'ee', 'sk', 'si', 'bg', 'is',
                    'lu', 'mt', 'cy', 'al', 'ba', 'mk', 'rs', 'me']
    domain = value.split('@')[-1].lower()
    tld = domain.split('.')[-1]
    if tld not in allowed_tlds and len(value.split('@')) > 1:
        # Не блокируем, а только предупреждение (не строгая проверка)
        pass


def validate_email_domain(value):
    """Проверка, что email не с временного домена"""
    domain = value.split('@')[-1].lower()
    if domain in BLOCKED_EMAIL_DOMAINS:
        raise ValidationError(
            f'Использование почты с доменом {domain} запрещено. Пожалуйста, используйте основной email.')


class CustomUserCreationForm(UserCreationForm):
    """
    Форма для регистрации нового пользователя с валидацией email
    """
    email = forms.EmailField(
        required=True,
        label='Email',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Введите email'}),
        validators=[validate_email_format, validate_email_domain]
    )
    username = forms.CharField(
        required=True,
        label='Логин',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Введите логин'}),
        validators=[
            RegexValidator(
                regex=r'^[\w.@+-]+$',
                message='Имя пользователя может содержать только буквы, цифры и символы @/./+/-/_'
            )
        ]
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

    def clean_username(self):
        """Проверка имени пользователя"""
        username = self.cleaned_data.get('username')

        # Запрещённые имена
        forbidden_usernames = ['admin', 'moderator', 'support', 'root', 'system', 'administrator', 'moderator']
        if username.lower() in forbidden_usernames:
            raise ValidationError('Это имя пользователя зарезервировано')

        # Минимальная длина
        if len(username) < 3:
            raise ValidationError('Имя пользователя должно содержать минимум 3 символа')

        # Максимальная длина
        if len(username) > 30:
            raise ValidationError('Имя пользователя не может быть длиннее 30 символов')

        return username

    def clean_email(self):
        """Проверка уникальности email и дополнительная валидация"""
        email = self.cleaned_data.get('email')

        # Проверка на уникальность
        if User.objects.filter(email=email).exists():
            raise ValidationError('Пользователь с таким email уже существует')

        # Дополнительная проверка на типичные ошибки
        if email.count('@') != 1:
            raise ValidationError('Email должен содержать ровно один символ @')

        local_part, domain = email.split('@')

        # Проверка локальной части
        if len(local_part) < 1:
            raise ValidationError('Локальная часть email не может быть пустой')

        if len(local_part) > 64:
            raise ValidationError('Локальная часть email слишком длинная')

        # Проверка домена
        if not domain or '.' not in domain:
            raise ValidationError('Email должен содержать домен (например, @gmail.com)')

        if len(domain) < 4:  # Минимум "a.com" - 4 символа
            raise ValidationError('Домен email слишком короткий')

        return email

    def clean_password2(self):
        """Дополнительная проверка пароля"""
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise ValidationError('Пароли не совпадают')

        # Проверка сложности пароля
        if password1:
            if len(password1) < 8:
                raise ValidationError('Пароль должен содержать минимум 8 символов')

            if not any(c.isdigit() for c in password1):
                raise ValidationError('Пароль должен содержать хотя бы одну цифру')

            if not any(c.isupper() for c in password1):
                raise ValidationError('Пароль должен содержать хотя бы одну заглавную букву')

            if not any(c.islower() for c in password1):
                raise ValidationError('Пароль должен содержать хотя бы одну строчную букву')

        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.username = self.cleaned_data['username']
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