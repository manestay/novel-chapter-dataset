from django.shortcuts import render
from django.db.models import Q
from django.shortcuts import get_object_or_404

from annoying.decorators import render_to

from base.utils import paging
from . import models as m
from . import forms as f


def T(template_name):
    return 'gutenberg/{}'.format(template_name)


def _book_list(request, objs):
    ctx = paging(request, objs)
    data = request.GET.dict()
    ctx['filter_form'] = f.BookFilterForm(initial=data)
    get_copy = request.GET.copy()
    get_copy.pop('page', '')
    ctx['querystring'] = get_copy.urlencode()
    ctx['gutenberg_active'] = 'active'
    return render(request, T('index.html'), context=ctx)


def index(request):
    objs = m.Book.objects.all()
    data = request.GET.dict()

    language = data.get('language', '')
    if language:
        objs = objs.filter(languages__id=language)

    category = data.get('category', '')
    if category:
        objs = objs.filter(category__id=category)

    q = data.get('q', '')
    if q:
        q0 = Q(title__icontains=q)
        q1 = Q(authors__name__icontains=q)
        q2 = Q(authors__aliases__icontains=q)
        q3 = Q(subjects__name__icontains=q)
        objs = objs.filter(q0 | q1 | q2 | q3)

    order_by = data.get('order_by', 'downloads')
    order = '' if data.get('order') == 'asc' else '-'
    ordering = order + order_by
    objs = objs.order_by(ordering).distinct()
    return _book_list(request, objs)


def subject(request, pk):
    objs = m.Book.objects.filter(subjects=pk)
    return _book_list(request, objs)


def bookshelf(request, pk):
    objs = m.Book.objects.filter(bookshelves=pk)
    return _book_list(request, objs)


def book_detail(request, pk):
    book = get_object_or_404(m.Book, pk=pk)
    pjax = request.META.get('HTTP_X_PJAX')
    ctx = {'obj': book, 'pjax': pjax, 'gutenberg_active': 'active'}
    tmpl = 'book_detail_inc.html' if pjax else 'book_detail.html'
    return render(request, T(tmpl), context=ctx)


