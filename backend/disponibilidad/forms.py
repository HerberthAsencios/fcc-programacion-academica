from django import forms

from .models import CargaNoLectiva


class CargaNoLectivaForm(forms.Form):
    tipo = forms.ChoiceField(choices=CargaNoLectiva.Tipo.choices)
    actividad = forms.CharField()
    horas = forms.DecimalField(min_value=0, max_digits=6, decimal_places=2)