from django import forms
from .models import Halaqa

class HalaqaForm(forms.ModelForm):
    class Meta:
        model = Halaqa
        fields = ['name', 'teachers', 'is_active']  # أزلنا "notes"
