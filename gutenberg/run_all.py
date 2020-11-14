"""
gutenberg/run_all.py

Runs all the scripts to get the gutenberg catalog, and save it to a pickled file.

You will need to download, unzip, and untar the file from
https://www.gutenberg.org/cache/epub/feeds/rdf-files.tar.zip
"""

import argparse
import glob
import json
import os
import sys
from copy import deepcopy

import dill as pickle
import requests

from run_gutenberg import rdf2json

sys.path.append('./scraping')
from scrape_vars import ALT_ORIG_MAP, TO_DELETE, EXCLUDED_IDS, ID_FILE, CATALOG_RAW_NAME, CATALOG_NAME

parser = argparse.ArgumentParser()
parser.add_argument('--use-pickled', action='store_true', help='use existing (partial) pickle')
parser.add_argument('--full', action='store_true', help='get full Gutenberg catalog (default: False)')
parser.add_argument('--ids', default=ID_FILE, help='path to files with Gutenberg IDs to collect')

TOP_LEVEL = 'cache/epub'
RDF_LIST = 'cache/rdf_list.txt'
OVERWRITE_RDF = False
BASE_URL_EBOOKS = 'https://www.gutenberg.org/ebooks/'


def load_rdf_list(fname, top_level, overwrite=False):
    if os.path.exists(fname) and not overwrite:
        with open(fname, 'r') as f:
            rdf_names = [x.strip() for x in f.readlines()]
    else:
        rdf_names = glob.glob(os.path.join(top_level, '*/pg*.rdf'))
        with open(fname, 'w') as f:
            f.writelines([x + '\n' for x in rdf_names])
    return rdf_names


def get_book_url(files):
    url, format_ret = '', ''
    for obj in files:
        write = True
        formats = obj['formats']
        for form in formats:
            if form == 'application/zip' or obj['uri'].endswith('zip'):
                break
            elif write and form.startswith('text/html'):
                url, format_ret = obj['uri'], form
                return url, format_ret
    return '', ''


def clean_catalog(catalog):
    if isinstance(catalog, str):
        catalog_str = catalog
        if not os.path.exists(catalog_str):
            print('{} not found'.format(catalog_str))
            return {}
        catalog = pickle.load(open(catalog_str, 'rb'))
    elif isinstance(catalog, dict):
        pass

    catalog = manual_fix(catalog)
    return catalog


def manual_fix(catalog):
    catalog = deepcopy(catalog)
    for k, v in ALT_ORIG_MAP.items():
        alt_item = catalog.get(k)
        orig_item = catalog.get(v)
        if not orig_item:
            continue
        if alt_item:
            old_authors, old_urls = alt_item['author'], alt_item['url']
            orig_item['author'].extend(old_authors)
            orig_item['url'].extend(old_urls)
        catalog[k] = orig_item
    catalog['The Metamorphosis']['author'] = ['Kafka, Franz']
    catalog['Typee'] = catalog['Typee: A Romance of the South Seas']
    catalog['The Adventures of Huckleberry Finn'] = catalog['Huckleberry Finn']
    catalog['Dr Jekyll and Mr Hyde'] = catalog['Dr. Jekyll and Mr. Hyde']
    catalog["Tess of the D'Urbervilles"] = catalog["Tess of the d'Urbervilles"]
    catalog["The DeerSlayer"] = catalog["The Deerslayer"]
    catalog["My Antonia"] = catalog["My Ántonia"]
    catalog["Alice's Adventures In Wonderland"] = catalog["Alice's Adventures in Wonderland"]

    for k in TO_DELETE:
        if k in catalog:
            del catalog[k]
    for book_num, (k, cat_d) in enumerate(catalog.items(), 1):
        print('\rcleaning {}/{} books'.format(book_num, len(catalog)), end='')
        for book_id in EXCLUDED_IDS:
            book_id = str(book_id)
            if book_id in cat_d['id']:
                idx = cat_d['id'].index(book_id)
                for val in cat_d.values():
                    val.pop(0)
    print()
    return catalog


if __name__ == "__main__":
    args = parser.parse_args()
    rdf_names = load_rdf_list(RDF_LIST, TOP_LEVEL, OVERWRITE_RDF)
    if args.full:
        idset = set()
        num_total = len(rdf_names)
    elif args.ids:
        with open(args.ids, 'r') as f:
            idset = set(json.load(f))
        num_total = len(idset)
    else:
        idset = set()
        num_total = len(rdf_names)

    if args.use_pickled and os.path.exists(CATALOG_RAW_NAME):
        with open(CATALOG_RAW_NAME, 'rb') as f:
            catalog = pickle.load(f)
        print('loaded {} books from {}'.format(len(catalog), CATALOG_RAW_NAME))
        done = [x['id'] for x in catalog.values()]
        done = set([item for subl in done for item in subl])
    else:
        catalog = {}
        done = set()
    for i, rdf in enumerate(rdf_names):
        id_ = rdf.split('/')[-1].split('.')[0][2:]
        if idset and id_ not in idset:
            continue
        if id_ in done:
            continue

        json_d = rdf2json(rdf)
        done.add(id_)

        title = json_d.get('title')
        author = json_d.get('author')
        if not title or not author:
            continue
        lang = json_d['language']
        if lang != ["en"]:
            continue
        type_ = json_d['type']
        if type_ != 'Text':
            continue
        description = json_d['description']

        if title not in catalog:
            catalog[title] = {'author': [], 'url': [], 'book_format': [], 'id': []}
        catalog[title]['author'].extend(author)
        book_url, book_format = get_book_url(json_d['files'])
        if not book_url or not book_format:
            print('\nno HTML-formatted text found for', id_)
        catalog[title]['url'].append(book_url)
        catalog[title]['book_format'].append(book_format)
        catalog[title]['id'].append(id_)

        num_books = len(catalog)
        print('\rprocessed {}/{} books for catalog'.format(num_books, num_total), end='')
        if num_books and num_books % 100 == 0:
            with open(CATALOG_RAW_NAME, 'wb') as f:
                pickle.dump(catalog, f)

    num_books = len(catalog)
    with open(CATALOG_RAW_NAME, 'wb') as f:
        pickle.dump(catalog, f)
    print('collected {} total books for catalog'.format(num_books))
    print('wrote to', CATALOG_RAW_NAME)

    catalog_cleaned = clean_catalog(CATALOG_RAW_NAME)
    with open(CATALOG_NAME, 'wb') as f:
        pickle.dump(catalog_cleaned, f)
    print('cleaned and wrote to', CATALOG_NAME)
