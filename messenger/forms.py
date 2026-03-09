from django import forms
from django.core.exceptions import ValidationError
from .models import Message, Chat
from django.contrib.auth import get_user_model

User = get_user_model()


class MessageForm(forms.ModelForm):
    """
    Форма отправки сообщения
    """
    class Meta:
        model = Message
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Напишите сообщение...'
            }),
        }

    def clean_content(self):
        content = self.cleaned_data.get('content')
        if not content or len(content.strip()) == 0:
            raise ValidationError('Сообщение не может быть пустым')
        return content.strip()


class ChatCreateForm(forms.Form):
    """
    Форма создания нового чата
    """
    participant = forms.ModelChoiceField(
        queryset=User.objects.all(),
        widget=forms.Select(attrs={
            'class': 'form-control'
        }),
        label='Выберите пользователя'
    )
    initial_message = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Напишите первое сообщение...'
        }),
        label='Первое сообщение'
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['participant'].queryset = User.objects.exclude(id=self.user.id)

    def clean_participant(self):
        participant = self.cleaned_data.get('participant')
        if participant == self.user:
            raise ValidationError('Нельзя создать чат с самим собой')
        return participant


class GroupChatCreateForm(forms.Form):
    """
    Форма создания группового чата
    """
    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Название чата'
        }),
        label='Название чата'
    )
    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control',
            'size': 10
        }),
        label='Участники'
    )
    initial_message = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Приветственное сообщение...'
        }),
        required=False,
        label='Приветствие'
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['participants'].queryset = User.objects.exclude(id=self.user.id)

    def clean_participants(self):
        participants = self.cleaned_data.get('participants')
        if not participants:
            raise ValidationError('Выберите хотя бы одного участника')
        return participants