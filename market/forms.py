from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Offer

class SignupForm(UserCreationForm):
    first_name = forms.CharField(label='Nombre', max_length=150)
    email = forms.EmailField(label='Correo')
    class Meta:
        model = User
        fields = ['username', 'first_name', 'email', 'password1', 'password2']

class BookingForm(forms.Form):
    quantity = forms.IntegerField(label='Cantidad', min_value=1, max_value=2147483647)
    contact = forms.CharField(label='Contacto para coordinar con el prestador', max_length=200)
    token = forms.UUIDField(widget=forms.HiddenInput)
    quote = forms.CharField(widget=forms.HiddenInput)

class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        exclude = ['provider', 'stock', 'stock_version']
        widgets = {name: forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type':'datetime-local'}) for name in ['starts_at', 'ends_at', 'expires_at']}


class InventoryForm(forms.Form):
    new_stock = forms.IntegerField(label='Nuevo cupo disponible', min_value=0, max_value=2147483647)
    expected_version = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
