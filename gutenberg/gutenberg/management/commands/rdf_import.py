from django.core.management.base import BaseCommand, CommandError
from path import Path
from ...rdfparser import rdf2json, print_json
from ... import models as m


def process_rdf(rdf_path, full=False):
    name = rdf_path.namebase  # pg1234
    id = int(name[2:])
    if m.Book.objects.filter(id=id).exists() and not full:
        print('{} exists, skip'.format(id))
        return

    rdf_json = rdf2json(rdf_path)
    title = rdf_json.get('title')
    if not title:
        print('book {} has no title, skip'.format(id))
        return

    print(rdf_path, title)

    category = rdf_json.pop('category', '')
    languages = rdf_json.pop('languages', [])
    subjects = rdf_json.pop('subjects', [])
    bookshelves = rdf_json.pop('bookshelves', [])
    authors = rdf_json.pop('authors', [])
    files = rdf_json.pop('files', [])

    book, created = m.Book.objects.get_or_create(id=id, **rdf_json)
    if full or created:
        if category:
            obj, _ = m.Category.objects.get_or_create(name=category)
            book.category = obj
        for name in languages:
            obj, _ = m.Language.objects.get_or_create(name=name)
            book.languages.add(obj)
        for name in subjects:
            obj, _ = m.Subject.objects.get_or_create(name=name)
            book.subjects.add(obj)
        for name in bookshelves:
            obj, _ = m.Bookshelf.objects.get_or_create(name=name)
            book.bookshelves.add(obj)
        for agent in authors:
            data = agent.get('agent', {})
            name = data.pop('name', '')[:m.COMMON_STR_LEN]
            aliases = data.pop('alias', [])
            if isinstance(aliases, str):
                aliases = [aliases]
            data['aliases'] = [alias[:m.COMMON_STR_LEN] for alias in aliases]
            obj, _ = m.Author.objects.update_or_create(
                name=name, defaults=data,
            )
            book.authors.add(obj)
        for data in files:
            uri = data.pop('uri', '')
            formats = data.pop('formats', [])
            if len(formats) == 1:  # skip all zip ones
                fmt = formats[0]
                if fmt.startswith("image"):
                    if 'cover.medium' in uri:
                        if not book.cover_medium:
                            book.cover_medium = uri
                    elif 'cover.small' in uri:
                        if not book.cover_small:
                            book.cover_small = uri
                elif fmt.startswith(("text/rdf", "text/xml", "application/rdf+xml")):
                    continue
                else:
                    data['format'] = fmt
                    obj, _ = m.File.objects.update_or_create(
                        book=book, uri=uri, defaults=data
                    )
        book.save()


class Command(BaseCommand):
    help = 'Import rdf files from root'

    def add_arguments(self, parser):
        parser.add_argument('path', help='path rdf dir or file')
        parser.add_argument('--full', dest='full', action='store_true')

    def handle(self, *args, **options):
        path = Path(options['path'])
        full = options["full"]
        if path.isfile():
            process_rdf(path, full=True)
        else:
            for rdf_path in path.walkfiles(pattern='*.rdf'):
                process_rdf(rdf_path, full=full)
