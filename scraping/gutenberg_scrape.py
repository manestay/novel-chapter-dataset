"""
gutenberg_scrape.py

Collects raw text of books from Project Gutenberg, and writes to a pickled file.
Will only use books that occur in at least 2 sources.

Optionally, scrape only a selected book, and write raw text as JSON.
"""

import argparse
import json
import pickle
import re
import sys
from collections import Counter

from bs4 import element
import requests

from scrape_lib import *
from scrape_vars import *

PICKLE_NAME = 'pks/raw_texts.pk'
SOURCES = ['gradesaver', 'cliffsnotes', 'pinkmonkey', 'novelguide', 'bookwolf']
SUMMARY_PATHS = ['pks/summaries_{}.pk'.format(x) for x in SOURCES]

H_TAGS = set(['h1', 'h2', 'h3', 'h4', 'h5', 'center'])
P_TAGS = set(['p', 'pre', 'blockquote', None])
SUBTITLE_MARKERS = [':', '.', '—']
EXCLUDED_SUB = set(['Preface', 'Scene'])
RE_BRACKET_NUM = re.compile(r'\[([Pp]g)?\s?\d+\]')

SIDDHARTHA_D = {
    "THE SON OF THE BRAHMAN": "The Brahmin's Son",
    "WITH THE SAMANAS": 'With the Samanas',
    "GOTAMA": 'Gotama',
    "AWAKENING": 'Awakening',
    "KAMALA": 'Kamala',
    "WITH THE CHILDLIKE PEOPLE": 'Amongst the People',
    "SANSARA": 'Samsara',
    "BY THE RIVER": 'By the River',
    "THE FERRYMAN": 'The Ferryman',
    "THE SON": 'The Son',
    "OM": 'Om',
    "GOVINDA": 'Govinda'}

parser = argparse.ArgumentParser(description='scrape gutenberg for book text')
parser.add_argument('book_title', nargs='?', help='book title')
parser.add_argument('--summaries', '-s', nargs='*', default=SUMMARY_PATHS, help='paths to summaries')
parser.add_argument('--out_name', '-o', help='out name (overrides default)')
parser.add_argument('--use-pickled', action='store_true', help='use existing (partial) pickle')


def chapter_resets(chapter_titles):
    prev_num = 0
    for title in chapter_titles:
        last_word = title.rsplit(' ', 1)[-1]
        if not last_word.isdigit():
            return True
        curr_num = int(last_word)
        if curr_num != prev_num + 1:
            return True
        prev_num += 1
    return False


def get_book_sections(title, catalog, book_soup=None, debug=False, encoding='utf-8'):
    """ Wrapper function to get book sections. Has manual fixes, which is why it is separate from
        the main _get_book_sections() function.
    """
    def strip_subtitles(soup, tag='h3', split_on='\n', class_='', start_str='Chapter'):

        regexp = re.compile(r'^{}'.format(start_str), re.IGNORECASE)
        if class_:
            h3s = soup.find_all(tag, class_=class_)
        else:
            h3s = soup.find_all(tag)
        for h3 in h3s:
            text = h3.text.strip()
            if not re.match(regexp, text):
                continue
            h3.string = text.split(split_on, 1)[0]
        return soup
    book_format = catalog[title]['book_format'][0]
    encoding = get_encoding(book_format)
    if title == 'Don Quixote':
        soup1 = get_soup("https://www.gutenberg.org/files/5921/5921-h/5921-h.htm")
        vol1 = _get_book_sections(title, catalog, book_soup=soup1, debug=debug)
        vol1 = {'Part 1: {}'.format(k.rsplit(': ', 1)[-1]): v for k, v in vol1.items()}
        soup2 = get_soup("https://www.gutenberg.org/files/5946/5946-h/5946-h.htm")
        soup2.find('h3', text=re.compile(".*OF WHAT.*")).decompose()
        vol2 = _get_book_sections(title, catalog, book_soup=soup2, debug=debug)
        vol2 = {'Part 2: {}'.format(k): v for k, v in vol2.items()}
        book = {**vol1, **vol2}
        return book
    elif title in set(['Treasure Island', "Dracula", 'Sister Carrie']):
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup = strip_subtitles(soup, 'h2')
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title in set(['Jude the Obscure']):
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        for e in soup.findAll('br'):
            e.replace_with('\n')
        soup = strip_subtitles(soup, 'h2', '\n', start_str='Part')
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "Uncle Tom's Cabin":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        for e in soup.findAll('br'):
            e.replace_with('\n')
        soup = strip_subtitles(soup, 'h3', '\n')
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title in set(['Emma']):
        book = _get_book_sections(title, catalog, book_soup=book_soup, debug=debug)
        book_new = {}
        prev_volume, prev_chapter = 0, 0
        items = [(k, v) for k, v in book.items() if ':' in k]
        for i, (k, v) in enumerate(items, 1):
            volume, chapter = [int(x.rsplit(' ', 1)[-1]) for x in k.split(':', 1)]
            assert (volume == prev_volume and chapter == prev_chapter + 1) or \
                   (volume == prev_volume + 1 and chapter == 1)
            prev_volume, prev_chapter = volume, chapter
            book_new['Chapter {}'.format(i)] = v
        return book_new
    elif title == 'Walden':
        chapter_titles = dict(zip(['Economy', 'Where I Lived, and What I Lived For', 'Reading', 'Sounds', 'Solitude',
                                   'Visitors', 'The Bean-Field', 'The Village', 'The Ponds', 'Baker Farm', 'Higher Laws', 'Brute Neighbors',
                                   'House-Warming', 'Former Inhabitants and Winter Visitors', 'Winter Animals', 'The Pond in Winter', 'Spring',
                                   'Conclusion'], range(1, 19)))
        chapter_titles.update({titlecase(k): v for k, v in chapter_titles.items()})
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        [x.decompose() for x in soup.find_all('pre', {'xml:space': 'preserve'})]

        book = _get_book_sections(title, catalog, book_soup=soup, debug=debug, chapter_titles=chapter_titles)
        book = {'Chapter {}'.format(chapter_titles[k]): v for k, v in book.items()}
        return book
    elif title in set(['Dr. Jekyll and Mr. Hyde', 'Dr Jekyll and Mr Hyde']):
        chapter_titles = dict(zip(['STORY OF THE DOOR', 'SEARCH FOR MR. HYDE', 'DR. JEKYLL WAS QUITE AT EASE',
                                   'THE CAREW MURDER CASE', 'INCIDENT OF THE LETTER', 'INCIDENT OF DR. LANYON', 'INCIDENT AT THE WINDOW',
                                   'THE LAST NIGHT', 'DR. LANYON’S NARRATIVE', 'HENRY JEKYLL’S FULL STATEMENT OF THE CASE'], range(1, 11)))
        chapter_titles.update({titlecase(k): v for k, v in chapter_titles.items()})
        book = _get_book_sections(title, catalog, book_soup=book_soup, debug=debug, chapter_titles=chapter_titles)
        book = {'Chapter {}'.format(chapter_titles[k]): v for k, v in book.items()}
        return book
    elif title == 'Siddhartha':
        book = _get_book_sections(title, catalog, book_soup=book_soup, debug=debug, chapter_titles=SIDDHARTHA_D.keys())
        book = {SIDDHARTHA_D[k.split(': ', 1)[-1]]: v for k, v in book.items()}
        return book
    elif title in set(['Winesburg, Ohio: A Group of Tales of Ohio Small Town Life', 'Winesburg, Ohio']):
        chapter_titles = set(['THE BOOK OF THE GROTESQUE', 'HANDS', 'PAPER PILLS', 'MOTHER', 'THE PHILOSOPHER',
                              'NOBODY KNOWS', 'GODLINESS', 'A MAN OF IDEAS', 'ADVENTURE', 'RESPECTABILITY', 'THE THINKER', 'TANDY',
                              'THE STRENGTH OF GOD', 'THE TEACHER', 'LONELINESS', 'AN AWAKENING', '"QUEER"', 'THE UNTOLD LIE', 'DRINK',
                              'DEATH', 'SOPHISTICATION', 'DEPARTURE'])
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        ps = soup.find_all('p', text="            *       *       *")
        for p in ps:
            p.decompose()
        soup.find('h4', id='id00013').decompose()
        soup.find('h2', id='id00064').decompose()
        soup.find('h2', id='id00065').string = 'THE BOOK OF THE GROTESQUE'
        book = _get_book_sections(title, catalog, book_soup=soup, debug=debug, chapter_titles=chapter_titles)
        book['Godliness Part 1'] = book.pop('GODLINESS')
        book['Godliness Part 2'] = book.pop('Chapter 2')
        book['Godliness Part 3'] = book.pop('Chapter 3')
        book['Godliness Part 4'] = book.pop('Chapter 4')
        book['Queer'] = book.pop('"QUEER"')
        book = {titlecase(k): v for k, v in book.items()}
        return book
    elif title == 'Dubliners':
        chapter_titles = ['THE SISTERS', 'AN ENCOUNTER', 'ARABY', 'EVELINE', 'AFTER THE RACE', 'TWO GALLANTS',
                          'THE BOARDING HOUSE', 'A LITTLE CLOUD', 'COUNTERPARTS', 'CLAY', 'A PAINFUL CASE',
                          'IVY DAY IN THE COMMITTEE ROOM', 'A MOTHER', 'GRACE', 'THE DEAD']
        book = _get_book_sections(title, catalog, book_soup=book_soup, debug=debug, chapter_titles=chapter_titles)
        book = {titlecase(k): v for k, v in book.items()}
        return book
    elif title == 'Washington Square':
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        page_nums = soup.find_all('span', class_='pagenum')
        for p in page_nums:
            p.decompose()
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == 'Cyrano de Bergerac':
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        for h3 in soup.find_all('h3'):
            scene = h3.find('a', {'name': re.compile('Scene.*')})
            if not scene:
                continue
            roman = scene.string.split('.')[1]
            scene.string.replace_with('Scene {}'.format(roman))
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "Alice's Adventures in Wonderland":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        pres = soup.find_all('pre', text=re.compile('[(?:\*    )+|THE END]'))
        for p in pres:
            p.decompose()
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "Little Women":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup.find('h2', align='center', text="\nLITTLE WOMEN PART 2\n").decompose()
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title in set(["Heart of Darkness", 'The Metamorphosis']):
        book = _get_book_sections(title, catalog, book_soup=book_soup, debug=debug)
        book = {k.replace('Chapter', 'Part'): v for k, v in book.items()}
        return book
    elif title in set(['Anthem']):
        book = _get_book_sections(title, catalog, book_soup=book_soup, debug=debug)
        book = {k.replace('Part', 'Chapter'): v for k, v in book.items()}
        return book
    elif title == "Middlemarch":
        return _get_book_sections(title, catalog, book_soup=book_soup, debug=debug, encoding='iso-8859-1')
    elif title == "Far from the Madding Crowd":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup = strip_subtitles(soup)
        book = _get_book_sections(title, catalog, book_soup=soup, debug=debug)
        return book
    elif title == 'The Three Musketeers':
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        h2 = soup.find('h2', text=re.compile("AUTHOR’S PREFACE"))
        h2.string = 'Preface'
        book = _get_book_sections(title, catalog, book_soup=soup, debug=debug)
        book = {' '.join(k.split(' ', 2)[0:2]) if k.startswith('Chapter') else k: v for k, v in book.items()}
        book['Chapter 45'] = book.pop('45 a Conjugal Scene')
        return book
    elif title == "Hard Times":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup = strip_subtitles(soup)
        for h2 in soup.find_all('h2'):
            if not h2.span:
                continue
            h2.span.decompose()
            h2.i.decompose()
        for h3 in soup.find_all('h3'):
            [x.decompose() for x in h3.find_all('span')]
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "Bleak House":  # mistake in the numbering
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        h4 = soup.find('h4', text='CHAPTER XXIX')
        h4.string = 'CHAPTER XXIV'
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "David Copperfield":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        h2 = soup.find('h2', text=re.compile('.*PREFACE TO THE.*'))
        h2.string = 'Preface'
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "The Turn of the Screw":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        h2 = soup.find('h2', text='THE TURN OF THE SCREW')
        h2.string = 'Prologue'
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "Arms and the Man":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        h3 = soup.find('h3', text=re.compile('INTRODUCTION'))
        h3.string = 'Preface'
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "The War of the Worlds":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup.find('a', {'name': 'book01'}).parent.string = 'Book 1'
        soup.find('a', {'name': 'book02'}).parent.string = 'Book 2'
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "The House of the Seven Gables":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == 'The Iliad':
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        [x.decompose() for x in soup.find_all('span', class_='lnm')]
        [x.decompose() for x in soup.find_all('h3', class_='')]
        [x.decompose() for x in soup.find_all('span', class_='pgnm')]
        book = _get_book_sections(title, catalog, book_soup=soup, debug=debug)
        return {k: v for k, v in book.items() if 'Argument' not in k}
    elif title == 'The Trial':
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        for h2 in soup.find_all('h2'):
            text = h2.text.strip()
            chapter = text.split('\n', 1)[0]
            h2.string = chapter
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == 'The Prince and the Pauper':
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        for chap in soup.find_all('p', text=re.compile('Chapter.*')):
            chap.name = 'h2'
        soup.find('p', text=re.compile('Conclusion\.')).name = 'h2'
        soup.find('p', text=re.compile('FOOTNOTES')).name = 'h2'
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == 'The Adventures of Tom Sawyer':
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup.find('h4').name = 'p'
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == 'The Scarlet Letter':
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup.find('h2', text='The Scarlet Letter.').decompose()
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == 'The Adventures of Huckleberry Finn':
        book = _get_book_sections(title, catalog, book_soup=book_soup, debug=debug)
        book['Chapter 43'] = book.pop('Chapter the Last')
        return book
    elif title == 'The American':
        book = _get_book_sections(title, catalog, book_soup=book_soup, debug=debug)
        book['Chapter 2'] = book.pop('Chapter Ii')
        return book
    elif title == 'The Mill on the Floss':
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup = strip_subtitles(soup, start_str='Book')
        book = _get_book_sections(title, catalog, book_soup=soup, debug=debug)
        return book
    elif title == 'Oliver Twist':
        soup = get_soup(catalog[title]['url'][0], encoding='utf-8')
        soup.find_all('h4')[-1].name = 'p'
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "Persuasion":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup.find('h3', align='center', text=re.compile('.*ELLIOT.*')).name = 'p'
        soup.find('h3', align='center', text=re.compile('volume one')).decompose()
        book = _get_book_sections(title, catalog, book_soup=soup, debug=debug)
        return {k.replace('(end Of Volume 1: ', ''): v for k, v in book.items()}
    elif title == "The Picture of Dorian Gray":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup.find('h3', text=re.compile('.*PREFACE.*')).string = 'Preface'
        book = _get_book_sections(title, catalog, book_soup=soup, debug=debug)
        return book
    elif title == "The Yellow Wallpaper":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup.find('h2').string = 'Chapter 1'
        book = _get_book_sections(title, catalog, book_soup=soup, debug=debug)
        book['Book'] = book.pop('Chapter 1')
        return book
    elif title == "Vanity Fair":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        [x.decompose() for x in soup.find_all('h3', align='center', text=re.compile('.*Chapter.*'))]
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "A Connecticut Yankee in King Arthur's Court":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup.find('h3', text=re.compile('.*LOCAL.*')).name = 'p'
        soup.find('h3', text=re.compile('.*PROCLAMATION.*')).name = 'p'
        soup.find('h3', text=re.compile('.*SOLDIERS, CHAMPIONS.*')).name = 'p'
        final_ps = soup.find('p', text=re.compile('FINAL P.S.'))
        final_ps.name = 'h2'
        final_ps.string = 'Chapter 45'
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "Ethan Frome":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        prologue_start = soup.find_all('h1', text=re.compile('\s*ETHAN FROME\s*'))[-1].string = 'Prologue'
        epilogue_start = soup.find('p', text=re.compile('.*THE QUER.*')).previous_sibling
        epilogue_tag = soup.new_tag('h2')
        epilogue_tag.append('Epilogue')
        epilogue_start.insert_before(epilogue_tag)
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "What Maisie Knew":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        intro_start = soup.find('p', text=re.compile('The litigation')).previous_sibling
        intro_tag = soup.new_tag('h3')
        intro_tag.append('Introduction')
        intro_start.insert_before(intro_tag)
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "Pygmalion":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        sequel_start = soup.find('hr').previous_sibling
        sequel_tag = soup.new_tag('h3')
        sequel_tag.append('Sequel')
        sequel_start.insert_before(sequel_tag)
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "Frankenstein":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        final_start = soup.find('p', text=re.compile('aright\.')).next_sibling
        final_tag = soup.new_tag('h2')
        final_tag.append('Final Letters')
        final_start.insert_before(final_tag)
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    elif title == "Crime and Punishment":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup.find('h2', text=re.compile('.*EPI.*')).string = 'Part 7' # Epilogue -> Part 7
        book = _get_book_sections(title, catalog, book_soup=soup, debug=debug)
        return book
    elif title == "The Brothers Karamazov":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup.find('span', text=re.compile('.*Epi.*')).string = 'Book 13'  # Epilogue -> Part 13
        book = _get_book_sections(title, catalog, book_soup=soup, debug=debug)
        return book
    elif title == "Ulysses":
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        pattern = re.compile("\[ (\d+) \]")
        for h2 in soup.find_all('h3'):
            match = re.match(pattern, h2.text)
            if not match:
                continue
            h2.string = match.group(1)
        book = _get_book_sections(title, catalog, book_soup=soup, debug=debug)
        return book
    elif title == "Northanger Abbey":
        book = _get_book_sections(title, catalog, book_soup=book_soup, debug=debug)
        for i in range(1, 16):
            book['Book 1: Chapter {}'.format(i)] = book.pop('Chapter {}'.format(i))
        for i in range(16, 32):
            book['Book 2: Chapter {}'.format(i-15)] = book.pop('Chapter {}'.format(i))
        return book
    elif title == "The Way of the World":
        book = _get_book_sections(title, catalog, book_soup=book_soup, debug=debug)
        book['Epilogue'] = book.pop("Act 5: Epilogue")
        return book
    elif title == 'A Study in Scarlet':
        soup = get_soup(catalog[title]['url'][0], encoding=encoding)
        soup.find('h2', text=re.compile('CHAPTER I\. O')).find_previous_sibling('h2').string = 'PART II'
        soup.find('h2', text=re.compile('CHAPTER VI\. A')).string = 'CHAPTER VI'
        return _get_book_sections(title, catalog, book_soup=soup, debug=debug)
    else:
        return _get_book_sections(title, catalog, book_soup=book_soup, debug=debug)


def get_encoding(book_format):
    arr = book_format.split('charset=')
    if len(arr) == 2:
        return arr[1]
    else:
        return None


def sub_roman(sect_title): return re.sub(RE_ROMAN, lambda x: str(roman_to_int(x[0])), sect_title)
def sub_numword(sect_title): return re.sub(RE_NUMWORD, lambda x: str(numword_to_int(x[0], numwords)), sect_title)
def sub_text(sect_title): return sub_numword(sub_roman(sect_title))


def _get_book_sections(title, catalog, book_soup=None, debug=False, encoding='utf-8', chapter_titles=[]):
    """ Main function to get book sections.
    """
    book = {}
    ind = 0
    book_link = catalog[title]['url'][0]
    encoding = get_encoding(catalog[title]['book_format'][0])
    if debug:
        print(book_link)
    if not book_soup:
        if not book_link:
            return {}
        book_soup = get_soup(book_link, encoding=encoding)
    divs_children = book_soup.find_all('div', class_='chapter')
    divs_children2 = book_soup.find_all('div', class_='tei tei-div')
    if divs_children:
        children = [x for div in divs_children for x in list(div.children)]
    elif divs_children2:
        children = [x for div in divs_children2 for x in list(div.children)]
    elif title == 'The Three Musketeers':
        divs_children = book_soup.find_all('div', class_='level-2 section')
        children = [x for div in divs_children for x in list(div.children)]
    else:
        children = list(book_soup.find('body').children)
    section, subsection = '', ''
    ind = 0
    break_flag = False
    while ind < len(children):
        if break_flag:
            break
        found = False
        while ind < len(children) and not found:
            if children[ind].name not in H_TAGS:
                ind += 1
                continue
            sect_title = children[ind].text.strip()
            sect_title_orig = sect_title
            sect_title = collapse_spaces(sect_title)
            if not '.D.' in sect_title:  # LL.D. Ph.D. etc D != 100
                sect_title = sub_text(sect_title)
            sect_title = titlecase(sect_title)
            for marker in SUBTITLE_MARKERS:
                sect_title = sect_title.split(marker, 1)[0].strip()
            match_section = any(re.search(regex, sect_title) for regex in
                                [book_re, act_re, part_re, volume_re, phase_re, epilogue_re])
            match_subsection = any(re.search(regex, sect_title) for regex in
                                   [chapter_re, scene_re, act_scene_re, additional_sub_re, letters_re, stave_re])
            match_additional_sect = re.search(additional_sect_re, sect_title)
            match_num = re.match(num_re, sect_title)

            if sect_title == 'Contents':
                ind += 1
                continue
            if chapter_titles and sect_title_orig in chapter_titles:
                match_subsection = True
                match_section = False
                sect_title = sect_title_orig
            if match_section:
                section = sect_title
                section = book_map[section.lower()] if section.lower() in book_map else section
                if title in ACT_ONLY_PLAYS:
                    found = True
            elif match_additional_sect:
                subsection = sect_title
                subsection = book_map[subsection.lower()] if subsection.lower() in book_map else subsection
                found = True
            elif match_subsection:
                subsection = sect_title
                if not (sect_title == 'Scene' and book_link == 'https://www.gutenberg.org/files/1508/1508-h/1508-h.htm'):
                    found = True
            # elif match_num and (section or book_link in  'https://www.gutenberg.org/files/19033/19033-h/19033-h.htm'):
            elif match_num:
                if sect_title.endswith('.'):
                    sect_title = sect_title[:-1]
                subsection = 'Chapter {}'.format(sect_title)
                found = True
            else:
                if debug:
                    print(sect_title, 'not matched')
            ind += 1

        if found:
            if title in ACT_ONLY_PLAYS:
                if section in book and subsection:
                    section_name = subsection
                else:
                    section_name = section
            elif section and subsection and (subsection not in EXCLUDED_SUB):
                section_name = '{}: {}'.format(section, subsection)
            elif section and subsection and (subsection in EXCLUDED_SUB):
                section_name = section
            elif not subsection:
                section_name = section
            else:
                section_name = subsection

            if debug:
                print(section_name)
            ind += 1
            text = []

            while ind < len(children):
                if children[ind].name in H_TAGS:
                    if not re.search(chapter_re, children[ind].text) and \
                            (len(text) == 0 or children[ind].find('i') or children[ind].find('img')):
                        # ex. https://www.gutenberg.org/files/1400/1400-h/1400-h.htm
                        ind += 1
                        continue
                    else:
                        break
                if children[ind].name == 'div':  # such as #16452
                    for x in children[ind].children:
                        if x.name in ['p', 'blockquote', None] and isinstance(x, element.Tag):
                            p_text = get_text(x)
                            if p_text:
                                text.append(p_text)

                if children[ind].name in P_TAGS and isinstance(children[ind], element.Tag):
                    p_text = get_text(children[ind])
                    p_text = re.sub(RE_BRACKET_NUM, '', p_text)  # remove page and line numbers
                    if re.match(re.compile('(?:\*\*\*)?End of(?: the|this)? Project Gutenberg.*', re.IGNORECASE), p_text) or \
                       re.match(re.compile('SELECTED BIBLIOGRAPHY'), p_text):
                        break_flag = True
                        break
                    if p_text:
                        text.append(p_text)
                ind += 1

            if section_name in book or not section_name:
                continue
            book[section_name] = text

    # remove "Book X" if the chapter number does not reset at each book
    keys = [x for x in list(book.keys()) if ':' in x and x.rsplit(' ', 1) and re.match(num_re, x.rsplit(' ', 1)[-1])]
    if keys and not chapter_resets(keys):
        if debug:
            print('removing Book number')
        book = {k.split(': ', 1)[-1]: v for k, v in book.items()}
    # book['title'] = title
    for key in list(book.keys()):
        if 'Project Gutenberg' in key:
            del book[key]
    return book


def get_text(tag):
    """ Get raw text without links.
    """
    p_texts = []
    for t in tag.contents:
        if isinstance(t, element.NavigableString):
            p_texts.append(t)
            continue
        if t.name == 'a':
            continue
        p_texts.append(t.text)
    return collapse_spaces("".join(p_texts)).strip()

def get_raw_texts(titles, out_name, use_pickled=False):
    if use_pickled and os.path.exists(out_name):
        with open(out_name, 'rb') as f1:
            books_d = pickle.load(f1)
        print('loaded {} existing raw texts, resuming'.format(len(books_d)))
        done = list(books_d.keys())
    else:
        books_d = {}
        done = set()

    for title in titles:
        if title in done:
            continue
        print('processing', title)
        print(gutenberg_catalog[title])
        book = get_book_sections(title, gutenberg_catalog)
        books_d[title] = book
        num_books = len(books_d)
        if num_books > 1 and num_books % 5 == 0:
            with open(out_name, 'wb') as f:
                pickle.dump(books_d, f)
            print("Done scraping {} books".format(num_books))

    with open(out_name, 'wb') as f:
        pickle.dump(books_d, f)
    print('wrote to', out_name)
    return books_d


def get_titles_to_scrape(summary_objs, min_count):
    counter = Counter()
    for summ_name in summary_objs:
        with open(summ_name, 'rb') as f:
            summ_list = pickle.load(f)
        titles = [x[0] for x in summ_list]
        # titles = [standardize_title(title) for title in titles]  # already done in the summary objects
        counter.update(titles)
    all_titles = [k for k, v in counter.items() if v > min_count]
    return all_titles


if __name__ == "__main__":
    args = parser.parse_args()
    gutenberg_catalog = load_catalog(CATALOG_NAME)

    if args.book_title: # get 1 book
        print(gutenberg_catalog[args.book_title])
        book = get_book_sections(args.book_title, gutenberg_catalog, debug=True)
        print(book.keys(), len(book.keys()))
        out_name = args.out_name or './{}.json'.format(args.book_title.replace(' ', '_'))
        with open(out_name, 'w') as f:
            json.dump(book, f, indent=4)
        print('wrote to', out_name)
    else: # get all books
        titles = get_titles_to_scrape(args.summaries, 1)
        out_name = args.out_name or PICKLE_NAME
        get_raw_texts(titles, out_name, use_pickled=args.use_pickled)
