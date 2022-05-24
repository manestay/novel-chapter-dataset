import dill as pickle
import os
import re
import requests
import string
import time
import unicodedata
import urllib.parse
import string

from bs4 import BeautifulSoup
from collections import namedtuple
from copy import deepcopy
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from number_lib import str_to_int, numword_to_int, int_to_roman, roman_to_int, get_numwords, RE_NUMWORD, numwords
from scrape_vars import TO_DELETE, EXCLUDED_IDS, ALT_ORIG_MAP, CATALOG_NAME, CATALOG_RAW_NAME, \
                        play_re, RE_SUMM, RE_SUMM_START, RE_ANALYSIS, RE_ROMAN, \
                        RE_CHAPTER_NOSPACE, RE_CHAPTER_DASH, RE_CHAPTER, RE_CHAPTER_START, RE_PART


BookSummary = namedtuple('BookSummary', ['title', 'author', 'genre', 'plot_overview', 'source', 'section_summaries', 'summary_url'])

###
# Text processing and BS4 helper functions
###
RE_SPACE = re.compile(r'\s+')


def get_soup(url, encoding=None, sleep=0):
    s = requests.Session()
    retries = Retry(total=4, backoff_factor=.3)
    s.mount('http://', HTTPAdapter(max_retries=retries))
    page = s.get(url)
    if sleep:
        time.sleep(sleep)
    return BeautifulSoup(page.content, 'html5lib', from_encoding=encoding)

def write_sect_links(outname, book_summaries):
    os.makedirs(os.path.dirname(outname), exist_ok=True)
    seen = set()
    with open(outname, 'w') as f:
        for idx, book_summ in enumerate(book_summaries):
            for chapter, _, link in book_summ.section_summaries:
                chap_id = f'{book_summ.title}\t{chapter}'
                if chap_id in seen:
                    print('warning: duplicated at', chap_id, idx)
                    # import pdb; pdb.set_trace()
                seen.add(chap_id)
                f.write(f'{book_summ.title}\t{chapter}\t{link}\n')


def get_absolute_links(links, base_url):
    return [urllib.parse.urljoin(base_url, x) for x in links]


def collapse_spaces(s):
    return RE_SPACE.sub(' ', s)


def find_all_stripped(tag, soup, regexp, **kwargs):
    return [x for x in soup.find_all(tag, **kwargs) if re.match(regexp, x.get_text(strip=True))]


def get_clean_text(tag, strip=True):
    return collapse_spaces(tag.get_text(strip=strip))


ARTICLES = ['a', 'an', 'of', 'the', 'in']
def titlecase(s):
    word_list = re.split(' ', s)
    final = [word_list[0].capitalize()]
    for word in word_list[1:]:
        final.append(word.lower() if word.lower() in ARTICLES else word.capitalize())
    return " ".join(final)


###
# functions for loading Gutenberg dataset
###

def load_catalog(path):
    # Load catalog from Gutenberg
    if not os.path.exists(path):
        print("ERROR: {} not found; either misnamed, or did not run gutenberg/run_all.py yet to generate catalog.")
    catalog = pickle.load(open(path, 'rb'))
    return catalog


def get_catalog_len(path='./catalog.pk'):
    catalog = pickle.load(open(path, 'rb'))
    return len(catalog)


def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def is_play(book):
    if book.author and "Shakespeare" in book.author:
        return True
    if book.title in set(['Arms and the Man', 'Cyrano de Bergerac', "An Enemy of the People",
                          "The Way of the World", "Pygmalion"]):
        return True
    sect_titles = [x[0] for x in book.section_summaries]
    for sect_title in sect_titles:
        if not sect_title:
            continue
        if re.match(play_re, sect_title):
            return True
    return False


def gen_gutenberg_overlap(book_summaries_all, catalog, filter_plays=False):
    if isinstance(catalog, str):
        catalog = load_catalog(catalog)

    book_summaries_overlap = []
    for book in book_summaries_all:
        if filter_plays and is_play(book):
            continue
        if book.title in catalog:
            book_summaries_overlap.append(book)
    print('{}/{} books overlap with Gutenberg catalog'.format(len(book_summaries_overlap), len(book_summaries_all)))

    return book_summaries_overlap


def standardize_title(title):
    """Standardize books with slightly different titles to the same title."""
    if 'Huckleberry Finn' in title:
        return 'The Adventures of Huckleberry Finn'
    elif 'Tom Sawyer' in title:
        return 'The Adventures of Tom Sawyer'
    elif 'Connecticut Yankee' in title:
        return "A Connecticut Yankee in King Arthur's Court"
    elif 'Alice' in title and 'Wonderland' in title:
        return "Alice's Adventures in Wonderland"
    elif 'War of the Worlds' in title:
        return 'The War of the Worlds'
    elif 'Moby' in title:
        return 'Moby Dick'
    elif 'ntonia' in title:
        return 'My Ántonia'
    elif 'Turn of the Screw' in title:
        return 'The Turn of the Screw'
    elif 'Jekyll' in title:
        return 'Dr Jekyll and Mr Hyde'
    elif 'Tess' in title:
        return 'Tess of the d\'Urbervilles'
    elif 'Looking Backward' in title:
        return 'Looking Backward: 2000-1887'
    elif title.lower() == 'the deerslayer':
        return 'The Deerslayer'
    return title


"""
For scraping sources
"""
def clean_title(title, preserve_summary=False):
    if title is None:
        return ''
    if preserve_summary and title == 'Summary':
        return title
    title_cleaned = re.sub(RE_SUMM_START, '', title)
    title_cleaned = re.sub(RE_SUMM, '', title_cleaned)
    if title_cleaned.endswith(':'):
        title_cleaned = title_cleaned[:-1]
    return title_cleaned


def clean_sect_summ(sect_summ):
    if sect_summ is None:
        return []
    sect_summ_cleaned = []
    for line in sect_summ:
        line = re.sub(r'\(\d+\)', '', line)
        if re.match(RE_SUMM, line):
            continue
        elif re.match(RE_ANALYSIS, line):
            break
        else:
            sect_summ_cleaned.append(line)
    return sect_summ_cleaned


subtitle_chars = ('"', '(')
replace_d = ((' & ', '-'), (' AND ', '-'), (' and ', '-'),
             (' to ', '-'), (' TO', '-'), ('—', '-'), ('–', '-'))
ord2card = {'First': '1', 'Second': '2', 'Third': '3', 'Fourth': '4', 'Fifth': '5','Sixth': '6', 'Seventh': '7',
            'Eighth': '8', 'Ninth': '9', 'Tenth': '10', 'Eleventh': '11', 'Twelfth': '12'}
RE_ORD = re.compile(r'\b({})\b'.format('|'.join(ord2card)))
RE_CHAPTERS = re.compile(r'Chapters?\s?', re.IGNORECASE)


def standardize_sect_title(candidate, process_ord=True):
    if candidate == 'Two Gallants':
        return candidate
    candidate = candidate.replace('IXX', 'XIX')  # happens in cliffsnotes
    candidate = re.sub(RE_ROMAN, lambda x: str(roman_to_int(x[0])), candidate)
    candidate = re.sub(RE_NUMWORD, lambda x: str(numword_to_int(x[0], numwords)), candidate)
    candidate = re.sub(RE_CHAPTERS, 'Chapter ', candidate)
    if re.search(RE_CHAPTER_DASH, candidate):
        chars = [':', '-']
        for char in chars:
            candidate = candidate.split(char, 1)[0]
    if candidate.endswith(':'):
        candidate = candidate[:-1]
    subtitle_match = [x in candidate for x in subtitle_chars]
    for i, match in enumerate(subtitle_match):
        if match:
            candidate = candidate.split(subtitle_chars[i], 1)[0]
            break
    if process_ord:
        ord_match = re.search(RE_ORD, candidate)
        if ord_match:
            candidate = candidate.replace(ord_match[0], ord2card[ord_match[0]])
    for x, y in replace_d:
        candidate = candidate.replace(x, y)
    candidate = re.sub(r'\s*-\s*', '-', candidate)
    return titlecase(candidate.strip())


def fix_multibook(sect, book_count):
    if sect.lower().startswith('book') or sect.lower().startswith('epilogue'):
        return sect, book_count
    if sect == "CHAPTER SUMMARIES AND NOTES":
        return None, book_count
    sect = standardize_sect_title(sect)
    match = re.search(RE_CHAPTER_START, sect)
    rexp = RE_CHAPTER_START
    if not match:
        match = re.search(RE_PART, sect)
        rexp = RE_PART
    if match and (match[0].upper() == 'CHAPTER 1' or match[0].upper() == 'PART 1'):
        book_count += 1
    sect = 'Book {}: {}'.format(book_count, sect)
    return sect, book_count


def fix_multipart(sect, book_count):
    if sect.lower().startswith('part'):
        return sect, book_count
    if 'PART' in sect:
        return None, book_count
    sect = standardize_sect_title(sect)
    sect = sect.replace('CHAPTERS', 'CHAPTER')
    match = re.search(RE_CHAPTER_START, sect)
    if match and match[0].upper() == 'CHAPTER 1':
        book_count += 1
    sect = 'Part {}: {}'.format(book_count, sect)
    return sect, book_count
