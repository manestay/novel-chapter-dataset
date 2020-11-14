from django.contrib import admin
from . import models as m


class BaseItemAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'display',
        'count',
    )
    search_fields = [
        'name',
    ]


admin.site.register(m.Bookshelf, BaseItemAdmin)
admin.site.register(m.Subject, BaseItemAdmin)
admin.site.register(m.Language, BaseItemAdmin)
admin.site.register(m.Category, BaseItemAdmin)


@admin.register(m.Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'birthdate',
        'deathdate',
        'aliases',
    )
    search_fields = [
        'name',
        'aliases',
        'webpage',
    ]


class FileInline(admin.TabularInline):
    model = m.File
    extra = 0
    fields = ['uri', 'format']


@admin.register(m.Book)
class BookAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'title',
        'cover_img',
        'issued',
        'downloads',
        'category',
    ]
    raw_id_fields = [
        'subjects',
        'bookshelves',
        'authors',
    ]
    date_hierarchy = 'issued'
    list_filter = [
        'category',
        'languages',
    ]
    search_fields = [
        'title',
        'alternative',
    ]
    inlines = [FileInline]

    def cover_img(self, obj):
        cover = obj.cover()
        return '<img src="{}" width="100">'.format(cover) if cover else ''
    cover_img.allow_tags = True


@admin.register(m.File)
class FileAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'uri',
        'format',
        'is_zip',
        'size',
        'book',
    ]
    list_filter = [
        'format',
    ]
    search_fields = [
        'book__title',
        'uri',
    ]
    raw_id_fields = [
        'book',
    ]
