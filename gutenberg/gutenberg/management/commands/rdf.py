from datetime import datetime
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from path import Path
from ... import models as m

INDEX_S = 0
INDEX_P = 1
INDEX_O = 2

def parse_rdf(path):
    id = int(path.namebase.strip('pg'))
    print(id)
    # book = m.Book.objects.filter(id=book_id).first()
    # if not book:
        # book = m.Book(id=book_id)

    import rdflib
    g = rdflib.Graph()
    g.load(path)

    s_tree = defaultdict(list)
    p_tree = defaultdict(list)
    o_tree = defaultdict(list)

    for s, p, o in g:
        t = (str(s), str(p), str(o))
        print(t)
        s_tree[t[INDEX_S]].append(t)
        p_tree[t[INDEX_P]].append(t)
        o_tree[t[INDEX_O]].append(t)

    p_title = 'http://purl.org/dc/terms/title'
    title = p_tree[p_title][0][INDEX_O]
    print(title)

    p_language = 'http://purl.org/dc/terms/language'
    o_language = p_tree[p_language][0][INDEX_O]
    language = s_tree[o_language][0][INDEX_O]
    print(language)

    o_type = 'http://purl.org/dc/terms/DCMIType'
    s_type = o_tree[o_type][0][INDEX_S]

    for s, p, o in s_tree[s_type]:
        if p == 'http://www.w3.org/1999/02/22-rdf-syntax-ns#value':
            type = o
            print(type)
            break

    p_issued = 'http://purl.org/dc/terms/issued'
    o_issued = p_tree[p_issued][0][INDEX_O]
    issued = datetime.strptime(o_issued, '%Y-%m-%d').date()
    print(issued)

    p_downloads = 'http://www.gutenberg.org/2009/pgterms/downloads'
    o_downloads = p_tree[p_downloads][0][INDEX_O]
    downloads = int(o_downloads)
    print(downloads)

    p_subject = 'http://purl.org/dc/terms/subject'
    for _, _, o_node in p_tree[p_subject]:
        for _, p, o_value in s_tree[o_node]:
            if p == 'http://www.w3.org/1999/02/22-rdf-syntax-ns#value':
                print(o_value)
                # m.Subject.objects.get_or_create(name=o_value)

    p_subject = 'http://www.gutenberg.org/2009/pgterms/bookshelf'
    for _, _, o_node in p_tree[p_subject]:
        for _, p, o_value in s_tree[o_node]:
            if p == 'http://www.w3.org/1999/02/22-rdf-syntax-ns#value':
                print(o_value)
                # m.Bookshelf.objects.get_or_create(name=o_value)

    p_format = 'http://purl.org/dc/terms/hasFormat'
    for _, _, url in p_tree[p_format]:
        for _, p, o in s_tree[url]:
            if p == 'http://www.w3.org/1999/02/22-rdf-syntax-ns#value':
                print(url, format)
                if url.endswith('.htm'):
                    html_url = url
                elif 'cover' in url:
                    cover_url = url
                else:



class Command(BaseCommand):
    help = 'Parse RDF file'

    def add_arguments(self, parser):
        parser.add_argument('--rdf')

    def handle(self, *args, **options):

        rdf_uri = options['rdf']
        if rdf_uri:
            rdf_path = Path(rdf_uri)
            if rdf_path.isfile():
                parse_rdf(rdf_path)

