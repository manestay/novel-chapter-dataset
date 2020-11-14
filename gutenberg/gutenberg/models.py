import json
import requests
from os.path import basename
from django.db import models
from django.urls import reverse
from django.contrib.postgres.fields import ArrayField
from django.conf import settings

from base.utils import sizeof_fmt

import logging
log = logging.getLogger(__name__)


COMMON_STR_LEN = 200

def show_str(s, n=50):
    if len(s) < n:
        return s
    else:
        return s[:n] + '...'


class BaseItem(models.Model):
    name = models.CharField(max_length=COMMON_STR_LEN, unique=True)
    display = models.CharField(max_length=COMMON_STR_LEN, blank=True, null=True)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ['-count', 'name']

    @property
    def display_name(self):
        return self.display or self.name

    @property
    def display_count(self):
        return '({})'.format(self.count) if self.count else ''

    def __str__(self):
        return '{}{}'.format(self.display_name, self.display_count)

    def update_count(self):
        self.count = self.book_set.all().count()
        self.save(update_fields=['count'])


class Subject(BaseItem):
    pass


class Language(BaseItem):
    pass


class Bookshelf(BaseItem):
    pass


class Category(BaseItem):
    pass


class Author(models.Model):
    name = models.CharField(max_length=COMMON_STR_LEN)
    aliases = ArrayField(models.CharField(max_length=COMMON_STR_LEN), blank=True)
    webpage = models.URLField(blank=True, null=True, default='')
    # actually year only, can be minus like -345
    birthdate = models.SmallIntegerField(blank=True, null=True)
    deathdate = models.SmallIntegerField(blank=True, null=True)

    def __str__(self):
        return self.name


class Book(models.Model):
    id = models.PositiveIntegerField("EBook-No.", primary_key=True)
    title = models.CharField(max_length=COMMON_STR_LEN)
    alternative = models.CharField(max_length=COMMON_STR_LEN, blank=True)
    issued = models.DateField('Release Date', blank=True, null=True)
    downloads = models.PositiveIntegerField(default=0)

    cover_small = models.URLField(blank=True, default='')
    cover_medium = models.URLField(blank=True, default='')

    category = models.ForeignKey(Category, blank=True, null=True)
    languages = models.ManyToManyField(Language, blank=True)
    authors = models.ManyToManyField(Author, blank=True)
    subjects = models.ManyToManyField(Subject, blank=True)
    bookshelves = models.ManyToManyField(Bookshelf, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    push_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-downloads']

    def __str__(self):
        return show_str(self.title)

    def cover(self, size='small'):
        return self.cover_small or self.cover_medium or ''

    def get_absolute_url(self):
        return reverse('gutenberg:book_detail', kwargs={'pk': self.pk})


class File(models.Model):
    book = models.ForeignKey(Book)
    uri = models.URLField(unique=True)
    format = models.CharField(max_length=50)
    is_zip = models.BooleanField(default=False)
    modified_at = models.DateTimeField(blank=True, null=True, db_index=True)
    size = models.PositiveIntegerField(default=0)

    push_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-modified_at']

    def basename(self):
        """
        Get uri basename.

        For legacy reason, this is a method, not property
        """
        return basename(self.uri)

    @property
    def name(self):
        return self.basename()

    def get_attachment_name_and_data(self):
        # uri: http://www.gutenberg.org/ebooks/54506.kindle.noimages
        r = requests.get(self.uri)
        if r.ok:
            # real uri: http://www.gutenberg.org/cache/epub/54506/pg54506.mobi
            return basename(r.url), r.content

    def is_large(self):
        return self.size > settings.MAX_PUSHSIZE

    def __str__(self):
        return self.name

    @property
    def humansize(self):
        return sizeof_fmt(self.size)

    def can_push(self, device_mail):
        return not ('kindle' in device_mail and 'epub' in self.format)

    def has_pushed(self, user_id, device_mail, in_seconds=10):
        """
        Check whether user has pushed in seconds.

        Adaptor for gutenberg File obj.
        Pass user_id in case UserProxy was used.
        """
        from books.models import Push
        from datetime import datetime, timedelta
        when = datetime.now() - timedelta(seconds=in_seconds)
        return Push.objects.filter(
            file_uri=self.uri,
            user_id=user_id,
            email=device_mail,
            when__gt=when,
        ).exists()

    def create_push(self, **kwargs):
        from books.models import Push
        push = Push.objects.create(file_uri=self.uri, **kwargs)
        log.info('file {} push_count +1'.format(self.pk))
        self.__class__.objects.filter(id=self.id).update(push_count=models.F('push_count')+1)
        return push
