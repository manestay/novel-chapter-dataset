from django.conf import settings

APP_NAME = DB_NAME = settings.GUTENBERG


class GutenbergRouter(object):
    def db_for_read(self, model, **hints):
        if model._meta.app_label == APP_NAME:
            return DB_NAME
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == APP_NAME:
            return DB_NAME
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == APP_NAME:
            return db == DB_NAME
        return None
