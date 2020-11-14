from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^ebooks/(?P<pk>\d+)/$', views.book_detail, name='book_detail'),
    url(r'^subject/(?P<pk>\d+)/$', views.subject, name='subject'),
    url(r'^bookshelf/(?P<pk>\d+)/$', views.bookshelf, name='bookshelf'),
]
