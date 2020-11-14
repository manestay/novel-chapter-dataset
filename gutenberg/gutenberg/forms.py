from django import forms
from . import models as m

class BookFilterForm(forms.Form):

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                'placeholder': '搜索关键字',
            }
        )
    )

    language = forms.ModelChoiceField(
        required=False,
        queryset=m.Language.objects.all(),
        empty_label='全部语言',
    )

    category = forms.ModelChoiceField(
        required=False,
        queryset=m.Category.objects.all(),
        empty_label='全部类别',
    )

    ORDER_BY_CHOICES = (
        ('downloads', '按下载数量'),
        ('id', '按收录顺序'),
        ('issued', '按出版日期'),
    )
    order_by = forms.ChoiceField(
        choices=ORDER_BY_CHOICES,
    )

    ORDER_CHOICES = (
        ('desc', '降序排序'),
        ('asc', '升序排序'),
    )
    order = forms.ChoiceField(
        choices=ORDER_CHOICES,
    )
