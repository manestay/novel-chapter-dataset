"""
novelguide_scrape.py

Scrapes novelguide.com for summaries. Outputs to pickled list of BookSummary objects.

Optional flags to 1) use the archived version of pages, 2) scrape all books, instead of only those in Gutenberg catalog.

Script is very hacky because the website is very inconsistent with formatting.
"""

import argparse
import os
import re
import time
import urllib.parse
from copy import deepcopy

import dill as pickle
import unicodedata
from bs4.element import NavigableString, Tag

from archive_lib import get_archived, get_orig_url
from number_lib import roman_to_int
from scrape_lib import BookSummary, get_soup, gen_gutenberg_overlap, clean_title, clean_sect_summ, get_clean_text, \
                       standardize_title, standardize_sect_title, load_catalog, write_sect_links, \
                       fix_multipart, fix_multibook
from scrape_vars import CATALOG_NAME, NON_NOVEL_TITLES, RE_SUMM_START, chapter_re, RE_CHAPTER_START, \
                        RE_CHAPTER_NOSPACE, RE_PART_NOSPACE


BOOKS_LIST = 'https://novelguide.com/novelguides?items_per_page=All'
OUT_NAME_ALL = 'pks/summaries_novelguide_all.pk'
OUT_NAME_OVERLAP = 'pks/summaries_novelguide.pk'
SLEEP = 0.5  # sleep, since pages fail to load if scraped too fast

NONBOLD_WITH_SECTIONS = ['www.novelguide.com/hard-times/',
                         'www.novelguide.com/gullivers-travels/summaries/parti-chaptersi-iii',
                         'www.novelguide.com/gullivers-travels/summaries/parti-chaptersvii-viii',
                         'www.novelguide.com/gullivers-travels/summaries/partii-chaptersiv-viii',
                         'www.novelguide.com/gullivers-travels/summaries/partiii-chaptersiv-xi',
                         'www.novelguide.com/gullivers-travels/summaries/partiv-chaptersiv-vii',
                         'www.novelguide.com/gullivers-travels/summaries/partiv-chaptersviii-xii',
                         'www.novelguide.com/main-street/',
                         'www.novelguide.com/my-antonia/']
BREAK_TITLES = ('seven-gables', 'great-expectations', 'wuthering-heights', 'uncle-toms-cabin', 'oliver-twist',
                'pride-and', 'don-quixote', 'frankenstein', 'crime-and-punishment', 'notes-from-the-underground',
                'the-scarlet-letter', 'the-iliad')
ANALYSIS = ('Analysis', 'Commentary', 'advertisement')

RE_PLOT = re.compile(r'(Novel )?[Ss]ummary:?$')
RE_CHAP_OPEN = re.compile(r'^(Volume \d, )?(Chapter|Act|Canto|Book|Part|Section|Story|Scene) \d+:')
RE_CHAP_NUM = re.compile(r'^Chapter ([MDCLXVI]+|\d+)')
RE_SUMM_LINK = re.compile(r'(/summ[ae]ries/|/novel-summary)')
RE_PLOT_LINK = re.compile(r'(/novel-summary)')
RE_SUMM_LINK_ARCHIVE = re.compile(r'.*(/summaries/|novel-summary).*')
RE_ROMAN = re.compile(r'Part [MDCLXVI]+')
DASH_START_RE = r'^\s?[–-]'

parser = argparse.ArgumentParser(description='scrape novelguide')
parser.add_argument('out_name', nargs='?', default=OUT_NAME_ALL, help='name of pickle file for all summaries')
parser.add_argument('out_name_overlap', nargs='?', default=OUT_NAME_OVERLAP,
                    help='name of pickle file for overlapping summaries')
parser.add_argument('--archived', action='store_true', help='always use archived versions of scripts')
# parser.add_argument('--archived-list', action='store_true', help='use archived books list page')
parser.add_argument('--use-pickled', action='store_true', help='use existing (partial) pickle')
parser.add_argument('--full', action='store_true', help='get all books, not just those in Gutenberg')
parser.add_argument('--catalog', default=CATALOG_NAME, help='get all books, not just those in Gutenberg')
parser.add_argument('--update-old', action='store_true', help='update out-of-date archived version')
parser.add_argument('--save-every', default=2, type=int, help='interval to save pickled file')
parser.add_argument('--sleep', default=0, type=int, help='sleep time between scraping each book')
parser.add_argument('--no-text', dest='get_text', action='store_false', help='do not get book text')


def get_title_url_map(books_list, title_set=None):
    soup = get_soup(books_list, sleep=SLEEP)
    # book_links = soup.find('table', class_='views-table cols-2').find_all('a')
    book_links = soup.find('table', class_='cols-2').find_all('a')
    title_url_map = {}
    for link in book_links:
        title = get_clean_text(link).replace(' Study Guide', '')
        if title_set and title not in title_set:
            continue
        link = link.get('href')
        title_url_map[title] = urllib.parse.urljoin(books_list, link)
    return title_url_map


def get_title(soup):
    return soup.find('h1', class_='title').get_text().rsplit(': ', 1)[-1]


def process_plot(link):
    plot_summ = []
    soup = get_soup(link, sleep=SLEEP)
    content = soup.find('div', id='content-content')
    paras = content.find_all('p')
    for p in paras:
        text = get_clean_text(p, strip=False)
        bold = p.find(['b', 'strong'])
        if bold:
            if bold.get_text() == 'Analysis':
                break
            sibs = list(bold.next_siblings)
            if sibs:
                text = str(sibs[-1])
            else:
                continue
        if p and not text.startswith('Log in'):
            plot_summ.append(text)
    return plot_summ

# TODO: really confusing which pages call which functions, should standardize at some point
def process_chapters(p, title=None):
    # for sections where the text is in one <p> tag separated by <br>
    bold = p.find_all(['b', 'strong'])
    colon_found = any(':' in x.get_text() for x in bold)
    if not bold:
        chapters = process_nonbold_section(p, title)
    elif not colon_found and bold:
        chapters = process_bold_section(p, title)
    elif colon_found:
        chapters = process_colon_and_bold_section(p, title)
    return chapters


def process_nonbold_section(p, title=None):
    texts = list(p.stripped_strings)
    if texts[0] == 'Summary':
        chapters = no_colon_section(texts, title)
    elif ':' in texts[0]:
        chapters = colon_section(texts, title)
    else:
        chapters = other_section(texts, title)
    return chapters


def process_bold_section(p, title_):
    title = ''
    sect_summ = []
    chapters = []
    write = True
    for content in p.contents:
        is_bold = False
        if type(content) == NavigableString:
            text = str(content).strip()
        elif type(content) == Tag:
            text = content.get_text(strip=True)
            is_bold = content.name == 'strong'
            if any(text.startswith(x) for x in ANALYSIS):
                write = False
                continue
        if not text:
            continue
        if is_bold:
            write = True
            if sect_summ and title:
                if title == 'Summary' or not title:
                    title = title_
                chapters.append((title, sect_summ))
            title = text if not re.match(RE_PLOT, text) else title
            sect_summ = []
            continue
        if write:
            sect_summ.append(text)

    if sect_summ:
        if title == 'Summary' or not title:
            title = title_
        chapters.append((title, sect_summ))
    return chapters


def colon_section(texts, title_):
    # Called by process_nonbold_section
    title = ''
    sect_summ = []
    chapters = []
    for text in texts:
        if any(text == x for x in ANALYSIS):
            break
        arr = text.split(':', 1)
        if len(arr) == 2 and title and len(arr[0]) < 22:
            chapters.append((title, sect_summ))
            sect_summ = []
        if len(arr) == 2 and len(arr[0]) < 22:
            title = arr[0] if arr[0] != 'Summary' else title_
            content = arr[1]
        else:
            content = text
        sect_summ.append(content)
    if sect_summ and title != 'Analysis':
        chapters.append((title, sect_summ))
    return chapters


def no_colon_section(texts, title):
    sect_summ = []
    chapters = []
    write = False
    for text in texts:
        if any(text.startswith(x) for x in ANALYSIS):
            chapters.append((title, sect_summ))
            break
        elif text == 'Summary':
            write = True
            continue
        if write:
            sect_summ.append(text)
    return chapters


def other_section(texts, title_, always_write=False):
    # ex. https://www.novelguide.com/ivanhoe/summaries/chapter9-12
    sect_summ = []
    chapters = []
    title = ''
    write = True if always_write else False
    for text in texts:
        cond = (text.startswith('Chapter') or text.startswith('Part')) and not text[-1] == '.'
        if any(text.startswith(x) for x in ANALYSIS):
            write = False
            continue
        elif cond:
            write = True
            if sect_summ and title:
                chapters.append((title, sect_summ))
            title = text

            sect_summ = []
        else:
            if write and text != 'Tweet':
                sect_summ.append(text)
    if sect_summ:
        #         if not title or always_write:
        if not title:
            title = title_
        chapters.append((title, sect_summ))
    return chapters


def process_colon_and_bold_section(p, title):
    # a format found, for ex. on https://www.novelguide.com/dracula/summaries/chapter15
    sect_summ = []
    chapters = []
    write = True
    texts = p.stripped_strings
    for text in texts:
        if text == 'Analysis:':
            write = False
            break
        elif text == 'Summary:':
            write = True
            continue
        if write and not re.match(RE_CHAP_NUM, text):
            sect_summ.append(text)
    if sect_summ:
        chapters.append((title, sect_summ))
    return chapters


def process_story(link, title=None):
    link = link.replace('http://www.novelguide.com', 'https://www.novelguide.com', 1)
    chapters = []
    soup = get_soup(link, sleep=SLEEP)
    if 'mansfield-park/' in link or 'jude-the-obscure' in link:
        content = soup.find('div', class_='content clear-block')
        paras = content.find_all(['p', 'strong', 'div'])[2:]
    else:
        content = soup.find('div', id='content-content')
        paras = content.find_all('p')
    if link.endswith('the-adventures-of-tom-sawyer/novel-summary'):
        initial = paras[1].children.__next__()
        initial.insert_before(paras[0])
    sect_summ = []
    title = get_title(soup)
    break_found = False
    write = True
    if 'ivan-fyodorovich' in link: # this page from The Brothers Karamazov is different from the others
        texts = [p.text for p in paras]
        summs = colon_section(texts, title)
        summs[9] = (summs[9][0], summs[9][1][:-7])
        chapters.extend(summs)
    else:
        for p in paras:
            text = get_clean_text(p, strip=False).strip()
            if not text or text.startswith('Log in'):
                continue
            br = p.find_all('br')
            if any(x in link for x in NONBOLD_WITH_SECTIONS):
                texts = list(p.stripped_strings)
                chapters.extend(other_section(texts, title))
            elif any(x in link for x in set(['ulysses', 'siddhartha', 'awakening', 'brothers-karamazov', 'tess-of',
                                            'the-ambass', 'jekyll', 'heart-of-darkness', 'winesburg'])):
                texts = list(p.stripped_strings)
                chapters.extend(other_section(texts, title, always_write=True))
            elif any(x in link for x in set(['monte-cristo'])):
                texts = list(p.stripped_strings)
                chapters.extend(colon_section(texts, title))
            elif (len(br) > 3 or re.match(RE_CHAP_OPEN, p.get_text()) or any(x in link for x in BREAK_TITLES)) and \
                    'fathers-and-sons' not in link and 'hound' not in link:
                break_found = True
                chapters.extend(process_chapters(p, title))
                title = list(p.stripped_strings)[0]
            else:  # for sections where the text is in multiple <p> tags
                if text == 'advertisement' and not 'the-awakening' in link:
                    break
                elif text == 'advertisement':
                    continue
                bold = p if p.name == 'strong' else p.find(['b', 'strong'])
                if bold:
                    write = True
                    bold_text = bold.get_text(strip=True)
                    is_summ = re.match(RE_PLOT, bold_text)
                    if any(bold_text.startswith(x) for x in ANALYSIS):
                        write = False
                        if sect_summ:
                            chapters.append((title, sect_summ, link))
                            sect_summ = []
                        continue
                    elif not is_summ:
                        if sect_summ:
                            chapters.append((title, sect_summ, link))
                        title = bold_text if not is_summ else title
                        sect_summ = []
                    sibs = list(bold.next_siblings)
                    if write and sibs:
                        sibs = [x.strip() for x in sibs if isinstance(x, str)]
                        text = ' '.join(sibs).strip()
                        sect_summ.append(text)
                elif text == 'Analysis':
                    write = False
                    continue
                else:
                    if write:
                        sect_summ.append(text)
    if not break_found and sect_summ:
        chapters.append((title, sect_summ, link))

    for i, chapter in enumerate(chapters):
        norm = [unicodedata.normalize("NFKD", p).strip() for p in chapter[1]]
        norm = [x for x in norm if x]
        link_chap = chapters[i][2] if len(chapter) == 3 else link
        chapters[i] = (chapters[i][0], norm, link_chap)
    return chapters


def get_chapter_num(x): return int(x.split(',', 1)[1].strip()[8:])
def get_first_last_chapter(sect_title):
    arr = re.findall(r'Chapter\s.*?\s', sect_title)
    return '{} - {}'.format(arr[0].strip(), arr[-1].split(' ', 1)[-1].strip())


def manual_fix(book_summaries):
    """ First pass manual fix of chapter titles. Need to do book-specific ones later for edge cases.
    """
    book_summaries_new = []
    for book_summ in book_summaries:
        title = book_summ.title
        section_summaries_new = []
        section_summaries_old = book_summ.section_summaries
        for i, curr_summ in enumerate(section_summaries_old):
            chap_title, sect_summ, link = curr_summ
            chap_title = clean_title(chap_title, preserve_summary=True)
            sect_summ = clean_sect_summ(sect_summ)
            if re.match(r'{}:'.format(chapter_re), chap_title):
                chap_title = chap_title.split(':', 1)[0]
            if re.match(RE_CHAPTER_NOSPACE, chap_title):
                chap_title = re.sub('Chapters?', 'Chapter ', chap_title)
            if re.match(RE_PART_NOSPACE, chap_title):
                chap_title = re.sub('Part', 'Part ', chap_title)
            if re.match(DASH_START_RE, chap_title):
                chap_title = re.sub(DASH_START_RE, '', chap_title, 1)
            if chap_title:
                section_summaries_new.append((chap_title.strip(), sect_summ, link))
        book_summ_new = book_summ._replace(section_summaries=section_summaries_new)
        book_summaries_new.append(book_summ_new)
    return book_summaries_new


def manual_fix_individual(book_summaries, get_text=True):
    """
    Note we do not manually fix the plays, since we do not use them in the literature dataset.
    """
    def remove_duplicates(sect_summs_old):
        seen = set()
        sect_summs = []
        for sect_title, sect_summ, link in sect_summs_old:
            if sect_title in seen:
                continue
            sect_summs.append((sect_title, sect_summ, link))
            seen.add(sect_title)
        return sect_summs

    def add_dash_numwords(sect_summs_old):
        sect_summs_new = []
        tens = ['Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty']
        for sect_title, sect_summ, link in sect_summs_old:
            sect_title = sect_title.replace('Sixty Two', 'Sixty Two and Sixty Three')
            for t in tens:
                sect_title = sect_title.replace(t + ' ', t + '-')
            sect_title = sect_title.replace(',', ' ')
            words = sect_title.split()
            if len(words) > 2:
                sect_title = '{} {} - {}'.format(words[0], words[1], words[-1])
            else:
                sect_title = '{} {}'.format(words[0], words[1])

            sect_summs_new.append((sect_title, sect_summ, link))
        return sect_summs_new

    def greenwood_fix(sect_summs_old, get_text=True):
        sect_summs_new = []
        sect_summs_old = remove_duplicates(sect_summs_old)
        for sect_title, sect_summ, link in sect_summs_old:
            if sect_title.startswith('C'):
                sect_title = get_first_last_chapter(sect_title)
                sect_summs_new.append((sect_title, sect_summ, link))
            else:  # Part Two
                ss, st = [], ''
                curr_summ = []
                write = False
                for line in sect_summ:
                    if line.startswith('Analysis'):
                        ss.append((st, curr_summ, link))
                        curr_summ = []
                        write = False
                    elif line.startswith('Summary'):
                        st = get_first_last_chapter(line)
                        write = True
                    elif write:
                        curr_summ.append(line)
                sect_summs_new.extend(ss)
        return sect_summs_new

    def ambass_fix(sect_summs_old):
        sect_summs_old = remove_duplicates(sect_summs_old)
        numbers = [1, 2, 3, 1, 2, 1, 2, 1, 2, 1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3, 4]
        sect_summs_new  = [('Chapter {}'.format(num), summ, link) for num, (_, summ, link) in zip(numbers, sect_summs_old)]
        return sect_summs_new

    def mirth_fix(sect_summs_old):
        sect_summs_new = []
        for sect_title, sect_summ, link in sect_summs_old:
            sect_title = sect_title.split(' – ', 1)[-1]
            sect_title = sect_title.replace('6,7,8', '6-8').replace(',', '-')
            sect_title = sect_title.replace('and', '-')
            sect_summs_new.append((sect_title, sect_summ, link))
        return sect_summs_new

    def bovary_fix(sect_summs_old):
        sect_summs_old = deepcopy(sect_summs_old)
        sect_summs_new = sect_summs_old[0:-5]
        chap_8 = []
        for chap_title, chap_summ, link in sect_summs_old[-5:]:
            if chap_title.endswith('8'):
                chap_8.extend(chap_summ)
            elif chap_title.endswith('9'):
                chap_8.extend(chap_summ)
                sect_summs_new.append(('Chapter 8', chap_8, link))
            else:
                orig = int(chap_title.rsplit(' ', 1)[-1])
                sect_summs_new.append(('Chapter {}'.format(orig-1), chap_summ, link))
        return sect_summs_new

    start = False  # True to debug
    book_summaries_new = []
    for idx, book_summ in enumerate(book_summaries):
        sect_summs_new = []
        sect_summs_old = book_summ.section_summaries
        title = book_summ.title
        # if idx == 0:
        #     start = True

        if not get_text:
            if sect_summs_old[0][0].lower() == 'summary':
                sect_summs_old = sect_summs_old[1:]

        if title in NON_NOVEL_TITLES:
            continue
        elif title == 'Don Quixote':  # not the same chapter numbering as Gutenberg
            continue
        elif title in set(['My Antonia', "The House of Mirth", 'The Ambassadors', 'War of the Worlds', 'Hard Times']):  # multibook
            book_count = 0
            if title == 'The House of Mirth':
                sect_summs_old = mirth_fix(sect_summs_old)
            elif title == 'The Ambassadors':
                sect_summs_old = ambass_fix(sect_summs_old)
            elif title == 'War of the Worlds':
                if get_text:
                    sect_summs_old = [('Chapter {}'.format(x[0].split('.', 1)[0]), *x[1:]) for x in sect_summs_old if '.' in x[0]]
                else:
                    sect_summs_old = [(f"Chapter {x[0].split(' - ', 1)[-1]}", *x[1:]) for x in sect_summs_old]
                    sect_summs_old = add_dash_numwords(sect_summs_old)
            elif title == 'My Antonia' and not get_text:
                    sect_summs_old = [(f"{x[0].split(', ', 1)[-1]}", *x[1:]) for x in sect_summs_old]
            elif title == 'Hard Times' and not get_text:
                sect_summs_new = [(re.sub('(\d)', ' \g<1>: ', x[0], 1), *x[1:]) for x in sect_summs_old]
            if sect_summs_new == []:
                for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old):
                    chap_title = chap_title.replace("Part", 'Chapter')
                    if not chap_title.startswith("Chapter"):
                        continue
                    chap_title, book_count = fix_multibook(chap_title, book_count)
                    sect_summs_new.append((chap_title, sect_summ, link))
        elif title in set(["Madame Bovary", "Gulliver's Travels", "Under the Greenwood Tree"]):  # multipart
            book_count = 0
            if title == "Under the Greenwood Tree":
                if not get_text:
                    sect_summs_new = [(x[0].replace(' Ch', ': Ch', 1), *x[1:]) for x in sect_summs_old]
                else:
                    sect_summs_old = greenwood_fix(sect_summs_old)
            elif title == 'Madame Bovary':
                if not get_text:
                    sect_summs_old = [(x[0].split(' - ', 1)[-1], *x[1:]) for x in sect_summs_old]
                else:
                    sect_summs_old = bovary_fix(sect_summs_old)
            elif title == "Gulliver's Travels" and not get_text:
                sect_summs_new = [(x[0].replace(' Ch', ': Ch', 1), *x[1:]) for x in sect_summs_old]
            if sect_summs_new == []:
                for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old):
                    if not chap_title.startswith("Chapter"):
                        continue
                    chap_title, book_count = fix_multipart(chap_title, book_count)
                    sect_summs_new.append((chap_title, sect_summ, link))

        elif title in set(['Crime and Punishment']) and get_text:
            sect_summs_new = [(chap.replace(',', ':', 1), summ, link) for chap, summ, link in sect_summs_old]
        elif title in set(['Treasure Island', 'Kidnapped']):
            sect_summs_old = remove_duplicates(sect_summs_old)
            if get_text:
                sect_summs_new = [x for x in sect_summs_old if x[0].startswith('Chapter')]
            else:
                sect_summs_new = sect_summs_old
        elif title in set(['Main Street', 'The Scarlet Letter', 'The Beast in the Jungle', "The Age of Innocence",
                           "The Call of the Wild", 'Ivanhoe']):
            sect_summs_new = remove_duplicates(sect_summs_old)
        elif title == 'Great Expectations':
            sect_summs_new = [('Chapter {}'.format(i), summ, link) for i, (_, summ, link) in enumerate(sect_summs_old, 1)]
        elif title == 'Babbitt':
            sect_summs_old = remove_duplicates(sect_summs_old)
            for sect_title, sect_summ, link in sect_summs_old:
                sect_title = sect_title.replace(',', '')
                nums = re.findall('\d+', sect_title)
                sect_title = 'Chapter {}-{}'.format(nums[0], nums[-1])
                sect_summs_new.append((sect_title, sect_summ, link))
        elif title == 'Adam Bede' and get_text:
            for sect_title, sect_summ, link in sect_summs_old:
                if sect_summ and sect_summ[0].startswith('George Eliot, Adam Bede. Edited'):
                    continue
                sect_summs_new.append((sect_title, sect_summ, link))
            assert sect_summs_new[0][0] == sect_summs_new[1][0] == 'Chapter 1'
            sect_summs_new = sect_summs_new[1:]
        elif title == 'Dracula' and get_text:
            assert sect_summs_old[0][0] == 'Summary'
            sect_summs_new = sect_summs_old[1:]
        elif title == 'Lord Jim':
            chapters = ['1 - 2', '3 - 5', '6 - 8', '9 - 11', '12 - 13', '14 - 16', '17 - 18', '19 - 21',
                        '22 - 23', '24 - 26', '27 - 29', '30 - 32', '33 - 35', '36 - 37', '38 - 40',
                        '41 - 43', '44 - 45']
            chapters = ['Chapter {}'.format(x) for x in chapters]
            sect_summs_new = [(chap, *summ[1:]) for chap, summ in zip(chapters, sect_summs_old)]
        elif title == 'Ethan Frome':
            sect_summs_new = sect_summs_old
            sect_summs_new[0] = ('Prologue', *sect_summs_new[0][1:])
            sect_summs_new[-1] = ('Epilogue', *sect_summs_new[-1][1:])
        elif title == "A Connecticut Yankee in King Arthur's Court":
            for sect_title, sect_summ, link in sect_summs_old:
                if not sect_title.startswith("Chapter"):
                    continue
                sect_summs_new.append((sect_title, sect_summ, link))
            sect_summs_new[-1] = ('Chapter 36-45', sect_summs_new[-1][1], link)
        # elif title == 'The Adventures of Tom Sawyer': # chapter 16 is split into 16 and 17
            # sect_summs_old = deepcopy(sect_summs_old)
            # sect_summs_new = sect_summs_old[0:15]
            # chap_16 = []
            # for chap_title, chap_summ, link in sect_summs_old[15:]:
            #     if chap_title.endswith('16'):
            #         chap_16.extend(chap_summ)
            #     elif chap_title.endswith('17'):
            #         chap_16.extend(chap_summ)
            #         sect_summs_new.append(('Chapter 16', chap_16, link))
            #     else:
            #         orig = int(chap_title.rsplit(' ', 1)[-1])
            #         sect_summs_new.append(('Chapter {}'.format(orig-1), chap_summ, link))
        elif title == "Tess of the d'Urbervilles":
            if get_text:
                phase_found = False
                for sect_title, sect_summ, link in sect_summs_old:
                    if sect_title.startswith('Phase'):
                        phase_found = True
                        continue
                    if not phase_found:
                        continue
                    if sect_title == 'Chapters I–XI':
                        continue
                    sect_summs_new.append((sect_title, sect_summ, link))
            else:
                sect_summs_new = [(f"{x[0].split(', ', 1)[-1]}", *x[1:]) for x in sect_summs_old]
        elif title == 'A Portrait of the Artist as a Young Man':
            sect_summs_old = remove_duplicates(sect_summs_old)
            if get_text:
                chap1_summ = []
                for sect_title, sect_summ, link in sect_summs_old:
                    if "Part" in sect_title:
                        chap1_summ.extend(sect_summ)
                        continue
                    elif chap1_summ:
                        sect_summs_new.append(('Chapter 1', chap1_summ, link))
                        chap1_summ = []
                    sect_summs_new.append((sect_title, sect_summ, link))
            else:
                sect_summs_new = sect_summs_old
        elif title == 'Of Human Bondage':
            sect_summs_old = remove_duplicates(sect_summs_old)
            sect_summs_new = [(chap.replace(' and ', '-'), summ, link) for chap, summ, link in sect_summs_old]
        elif title == 'The Secret Sharer':
            sect_summs_new = [(x[0].replace('Part', 'Chapter'), *x[1:]) for x in sect_summs_old if x[0].startswith('Part')]
        elif title == "Moby Dick":  # TODO: scrape with less manual fixing
            for sect_title, sect_summs, links in sect_summs_old:
                summs_new = []
                sect_title = sect_title.replace('\xa0', '').replace(' and ', ' - ').split(", “", 1)[0].split(",“", 1)[0].strip()
                if sect_title.startswith('hapter'):
                    sect_title = 'C' + sect_title
                elif sect_title == 'Chatper 39':
                    sect_title = 'Chapter 39'
                elif sect_title == 'Chapter 50' and sect_summs_new[-1][0] == 'Chapter 50': sect_title = 'Chapter 51'
                elif sect_title == 'Chapter 72' and sect_summs_new[-1][0] == 'Chapter 72': sect_title = 'Chapter 73'
                elif sect_title.startswith('Chapters 95'): sect_title = 'Chapters 95-98'
                elif sect_title.startswith('Chapters 101'): sect_title = 'Chapters 101-105'
                elif sect_title.startswith('Chapters 120'): sect_title = 'Chapters 120-124'
                elif sect_title == 'Chapters 10, 11, - 12': continue
                elif sect_title.startswith('Chapters 26 - 27'): sect_title = 'Chapters 26-27'
                elif sect_title == 'The Epilogue': sect_title = 'Epilogue'

                for p in sect_summs:
                    if p == 'Summary':
                        continue
                    elif p.startswith('Analysis'):
                        break
                    else:
                        summs_new.append(p)
                if not sect_title.startswith(('C', 'Epilogue')):
                    continue
                sect_summs_new.append((sect_title, summs_new, links))
            sect_summs_new = remove_duplicates(sect_summs_new)
        elif title == "Gulliver's Travels":
            for sect_title, sect_summ, link in sect_summs_old:
                if not sect_summ:
                    continue
                if sect_title.startswith("Part I"):
                    continue
                sect_summs_new.append((sect_title, sect_summ, link))
        elif title == "Siddhartha":
            for sect_title, sect_summ, link in sect_summs_old:
                if '-' in sect_title:
                    sect_title = sect_title.split('-', 1)[-1].strip()
                else:
                    sect_title, sect_summ = sect_summ[0], sect_summ[1:]
                sect_summs_new.append((sect_title, sect_summ, link))
        elif title == 'Sense and Sensibility':
            sect_summs_old = sect_summs_old[0:11] + sect_summs_old[21:]
            offset = 0
            for i, (sect_title, sect_summ, link) in enumerate(sect_summs_old, 1):
                if sect_title == 'Chapter XIII':  # chapter 12 is missing
                    offset = 1
                sect_title = 'Chapter {}'.format(i + offset)
                sect_summs_new.append((sect_title, sect_summ, link))
        elif title == 'White Fang':
            for sect_title, sect_summ, link in sect_summs_old:
                nums = sect_title.split(' ', 1)[0]
                part, chapter = nums.split('.', 1)
                sect_title = 'Part {}: Chapter {}'.format(part, chapter)
                sect_summs_new.append((sect_title, sect_summ, link))
        elif title == 'Bleak House' and get_text:
            sect_summs_new = remove_duplicates(sect_summs_old)
            assert sect_summs_new[0][0] == 'Author’s Preface'
            sect_summs_new[0] = ('Preface', *sect_summs_new[0][1:])
            assert sect_summs_new[19][0] == 'Chapter XIX'
            text = sect_summs_new[20][1]
            link = sect_summs_new[20][2]
            text[0] = 'I' + text[0]
            XIX_new = (sect_summs_new[19][0], text, link)
            sect_summs_new[19] = XIX_new
            del sect_summs_new[20]
        elif title == 'Notes from the Underground':
            sect_summs_new = [(x[0].replace(' C', ': C'), *x[1:]) for x in sect_summs_old]
        elif title == "Middlemarch":
            sect_summs_new = remove_duplicates(sect_summs_old)
            sect_summs_new = [(chap.split('(', 1)[0].strip(), summ, link) for chap, summ, link in sect_summs_new]
        elif title == "Walden":
            sect_summs_new = remove_duplicates(sect_summs_old)
            sect_summs_new = [(chap.split('‘', 1)[0].strip(), summ, link) for chap, summ, link in sect_summs_new]
            sect_summs_new[-1] = ('Chapter 17-18', *sect_summs_new[-1][1:])
        elif title == 'A Tale of Two Cities':
            sect_summs_new = []
            for sect_title, sect_summ, link in sect_summs_old:
                sect_title = re.sub(r' ?C', ': C', sect_title)
                sect_summs_new.append((sect_title, sect_summ, link))
            sect_summs_new = remove_duplicates(sect_summs_new)
        elif title == 'A Christmas Carol':
            sect_summs_new = remove_duplicates(sect_summs_old)
            sect_summs_new = [(chap.split(':', 1)[0], summ, link) for chap, summ, link in sect_summs_new if not chap.startswith('Stave 1')]
        elif title == 'The Awakening':
            sect_summs_new = [(chap.replace('Part', 'Chapter', 1), summ, link) for chap, summ, link in sect_summs_old]
        elif title == 'Around the World in Eighty Days' and get_text:
            sect_summs_old = remove_duplicates(sect_summs_old)
            sect_summs_new = [(chap.split(':', 1)[0], summ, link) for chap, summ, link in sect_summs_old if chap.startswith('Chapter')]
            assert sect_summs_new[1][0] == 'Chapter 1'
            del sect_summs_new[1]
        elif title == "Fathers and Sons":
            if get_text:
                sect_summs_old = remove_duplicates(sect_summs_old)
                for sect_title, sect_summ, link in sect_summs_old:
                    if sect_title.endswith('Analysis'):
                        continue
                    elif sect_title == 'Chapter 16':  # this one is analysis
                        continue
                    elif sect_title == 'Chapters 16':
                        sect_title = 'Chapter 16'
                    sect_summs_new.append((sect_title, sect_summ, link))
            else:
                sect_summs_new = add_dash_numwords(sect_summs_old)
        elif title == "The Yellow Wallpaper" and get_text:
            all_sects = [x[1] for x in book_summ.section_summaries]
            link = book_summ.section_summaries[0][2]
            all_sects = [sublist for l in all_sects for sublist in l]
            sect_summs_new = [('book', all_sects, link)]
        elif title == 'Anna Karenina':
            if get_text:
                sect_summs_new = [(chap.replace(' section', ': Chapter'), summ, link) for chap, summ, link in sect_summs_old]
            else:
                sect_summs_new = sect_summs_old
        elif title == 'The Metamorphosis':
            sect_summs_new = [(chap.replace('Section', 'Part'), summ, link) for chap, summ, link in sect_summs_old]
        elif title in set(['Vanity Fair', 'Mansfield Park', 'Washington Square', 'The Deerslayer']):
            sect_summs_new = add_dash_numwords(sect_summs_old)
            if title == 'The Deerslayer' and get_text:
                assert sect_summs_new[0][0] == sect_summs_new[1][0]
                sect_summs_new.pop(0)
                assert sect_summs_new[-6][0] == 'Chapters Twenty-and - Twenty-One'
                sect_summs_new[-6] = ('Chapter 20-21', *sect_summs_new[-6][1:])
        elif title == "The Jungle":
            sect_summs_new = [(chap.replace('Twenty ', 'Twenty-'), summ, link) for chap, summ, link in sect_summs_old]
        elif title == 'The Mayor of Casterbridge':
            sect_summs_new = add_dash_numwords(sect_summs_old)
            # if get_text:
            #     assert sect_summs_new[4][0] == 'Twelve Thirteen - Fourteen'
            #     sect_summs_new[4] = ('Chapter 12-14', sect_summs_new[4][1])
        elif title == 'Persuasion':
            if get_text:
                assert sect_summs_old[0][0].startswith('Volume')
                sect_summs_old = sect_summs_old[1:]
                sect_summs_old = sorted(sect_summs_old, key=lambda x: int(x[0].rsplit('-', 1)[-1]))  # sort by page number
                offset = 0
                for sect_title, sect_summ, link in sect_summs_old:
                    if sect_title == "Chapter I, pages 115-122":
                        offset = 12
                    sect_title = sect_title.split(',', 1)[0]
                    if offset:
                        chap = roman_to_int(sect_title.rsplit(' ', 1)[-1])
                        sect_title = 'Chapter {}'.format(chap+offset)
                    sect_summs_new.append((sect_title, sect_summ, link))
            else:
                chaps = ['Chapter 1', 'Chapter 2-3', 'Chapter 6-7', 'Chapter 8-10', 'Chapter 11-12', 'Chapter 13-14', 'Chapter 15-16', 'Chapter 17-18', 'Chapter 19-20', 'Chapter 21-22', 'Chapter 23-24']
                sect_summs_new = [(chap, *x[1:]) for chap, x in zip(chaps, sect_summs_old)]

        elif title == 'Far from the Madding Crowd':
            sect_summs_new = [(x[0].replace('Ch.', 'Chapter').split(':', 1)[0], *x[1:]) \
                              for x in sect_summs_old]
        elif title == 'The Turn of the Screw':  # novelguide has 2 books with same title, use the other one
            continue
        elif title == 'Turn of the Screw':
            sect_summs_new = [(x[0].replace('Section', 'Chapter'), *x[1:]) for x in sect_summs_old]
        elif title == "The Adventures of Huckleberry Finn":
            for sect_title, sect_summ, link in sect_summs_old:
                if sect_title == 'Chapter 1-3':
                    sects = sect_summ[0].split("Chapter")
                    for sect in sects:
                        if not sect:
                            continue
                        st, ss = sect.split(':', 1)
                        sect_summs_new.append(('Chapter {}'.format(st.strip()), ss, link))
                else:
                    sect_summs_new.append((sect_title, sect_summ, link))
        elif title == "The Picture of Dorian Gray":
            sect_summs_new = sect_summs_old
            sect_summs_new[0] = ('Chapters 1-3', *sect_summs_new[0][1:])
        elif title == 'The Scarlet Pimpernel':
            sect_summs_new = sect_summs_old
            sect_summs_new[3] = ('Chapter III', *sect_summs_new[3][1:])
            sect_summs_new[5] = ('Chapter VII', *sect_summs_new[7][1:])
            sect_summs_new.pop(0)
            if not get_text:
                sect_summs_new = add_dash_numwords(sect_summs_new)
        elif title == 'Jude the Obscure' and get_text:
            for sect_title, sect_summ, link in sect_summs_old:
                if not sect_summ:
                    continue
                if sect_title == 'At Marygreen':
                    sect_title = 'I–1'
                elif sect_title == 'At Melchester':
                    sect_title = 'III–1'
                elif sect_title == 'At Christminster Again':
                    sect_title = 'VI–1'

                part_, chap = sect_title.split('–', 1)
                if chap == '1':  # the roman numerals are inaccurate on the original pages
                    part = part_
                sect_title = 'Part {}: Chapter {}'.format(part, chap)
                sect_summs_new.append((sect_title, sect_summ, link))
        elif title == 'Ulysses':
            sect_summs_new = [('Chapter {}'.format(x[0].rsplit(' ', 1)[-1]), *x[1:]) for x in sect_summs_old]
        elif title == 'The American':
            sect_summs_new = [(x[0].replace('Book', 'Chapter'), *x[1:]) for x in sect_summs_old]
            sect_summs_new = add_dash_numwords(sect_summs_new)
        elif title == 'The Brothers Karamazov':
            if get_text:
                book = 0
                for sect_title, sect_summ, link in sect_summs_old:
                    if not sect_title.startswith('Chapter'):
                        continue
                    if sect_title == 'Chapter 1':
                        book += 1
                    sect_title = "Book {}: {}".format(book, sect_title)
                    sect_summs_new.append((sect_title, sect_summ, link))
            else:
                for sect_title, sect_summ, link in sect_summs_old:
                    chap = sect_title[sect_title.find('(')+1:sect_title.find(')')]
                    if sect_title.startswith('Epilogue'):
                        book = 'Book 13'
                    else:
                        book = re.search('Book \S*', sect_title)[0]
                    sect_summs_new.append((f'{book}: {chap}', sect_summ, link))

        elif title == "Winesburg, Ohio":
            sect_summs_new = [(x[0].replace('&', ',').replace('VI', 'IV').replace('Godliness', 'Godliness Part'), \
                               *x[1:]) for x in sect_summs_old]
        elif title == "War and Peace":
            ssn = [(standardize_sect_title(x[0], False), *x[1:]) for x in sect_summs_old]
            book_summ_new = book_summ._replace(section_summaries=ssn)
        elif title == 'The Hound of the Baskervilles':
            for sect_title, sect_summ, link in sect_summs_old:
                if ' - ' in sect_title:
                    sect_title = sect_title.split(' - ')[0]
                elif sect_title == 'Chapter 10' and sect_summs_new[-1][0] == 'Chapter 15':
                    continue
                elif not sect_title.startswith('C'):
                    continue
                sect_summs_new.append((sect_title, sect_summ, link))
        else:
            sect_summs_new = sect_summs_old

        if sect_summs_new:
            sect_summs_new = [(standardize_sect_title(x[0]), *x[1:]) for x in sect_summs_new]
            title_new = standardize_title(title)
            if title_new != title:
                print('renamed {} -> {}'.format(title, title_new))
                title = title_new
            book_summ_new = book_summ._replace(section_summaries=sect_summs_new, title=title_new)
            sect_summs_new = []
        book_summaries_new.append(book_summ_new)
        if start:  # for debugging
            print(title, idx)
            assert title == book_summaries_new[-1].title
            for i, x in enumerate(book_summaries_new[-1].section_summaries, 1):
                print(x[0] or x[1][0][0:100] + ' index ' + str(i))
            input()
    return book_summaries_new


def sort_cells(cells):
    pages = [x['href'].rsplit('/', 1)[-1] for x in cells]
    ordered_pages = ['a-nice-little-family-chapters-1-5', 'an-inappropriate-gathering-chapters1-4',
                     'an-inappropriate-gathering-chapters5-8', 'the-sensualists-chapters1-11', 'strains-chapters1-7',
                     'pro-and-contra-chapters1-4', 'pro-and-contra-chapter5', 'pro-and-contra-chapters6-7',
                     'the-russian-monk-chapters1-3', 'alyosha-chapters1-4', 'mitya-chapters1-8',
                     'the-preliminary-investigation-chapters1-9', 'boys-chapters1-7',
                     'brother-ivan-fyodorovich-chapters1-10', 'a-judicial-error-chapters1-14', 'epilogue-chapters1-3']
    ordered_pages_d = {x: i for i, x in enumerate(ordered_pages)}
    ordered_cells = [None] * len(ordered_pages)
    for page, cell in zip(pages, cells):
        if page not in ordered_pages_d:
            continue
        idx = ordered_pages_d[page]
        ordered_cells[idx] = cell
    assert [x['href'].rsplit('/', 1)[-1] for x in ordered_cells] == ordered_pages
    return ordered_cells


def get_summaries(title_url_map, out_name, use_pickled=False, archived=False, update_old=False,
                  get_text=True, save_every=5, sleep=0):
    if use_pickled and os.path.exists(out_name):
        with open(out_name, 'rb') as f1:
            book_summaries = pickle.load(f1)
        print('loaded {} existing summaries, resuming'.format(len(book_summaries)))
        done = set([x.title for x in book_summaries])
    else:
        book_summaries = []
        done = set()

    for title, url in title_url_map.items():
        title = title.replace("DeerSlayer", 'Deerslayer', 1)
        if title in done:
            continue
        if sleep:
            time.sleep(sleep)
        author = ''  # TODO: figure this out
        archived_local = archived

        print('processing', title, url)
        soup = get_soup(url, sleep=SLEEP)
        table = soup.find('div', id='block-booknavigation-3') or soup.find('div', id='block-block-4')

        # process plot summary
        plot_summ = ''
        if get_text:
            plot_cell = table.find('a', href=RE_PLOT_LINK)
            if plot_cell:
                plot_title = plot_cell.get_text()
                href = plot_cell['href']
                plot_link = urllib.parse.urljoin(url, href)
                if 'Chapter' not in plot_title:
                    plot_summ = process_plot(plot_link)
                if not plot_summ:
                    print('  no plot summary found', plot_link)

        # process section summaries
        cells = table.find_all('a', href=RE_SUMM_LINK)
        if title == "The Brothers Karamazov":
            cells = sort_cells(cells)
        section_summs = []

        if not cells:
            print('  no section links found for', url)
            continue

        seen_sects = set()
        for c in cells:
            section_title = get_clean_text(c)
            section_title_chap = section_title.rsplit(':', 1)[-1].strip()
            if section_title_chap in seen_sects:
                print('  seen {} already, skipped'.format(section_title_chap))
                continue
            if re.match(RE_PLOT, section_title):
                continue

            link_summ = urllib.parse.urljoin(url, c['href'])

            if get_text:
                try:
                    page_summs = process_story(link_summ)
                except AttributeError:  # page failed to load, try again
                    print('  retrying after 5 seconds...')
                    time.sleep(5.0)
                    try:
                        page_summs = process_story(link_summ)
                    except AttributeError:
                        print(f'unable to load {link_summ}, skipping')
                        continue


                if page_summs:
                    section_summs.extend(page_summs)
                    seen_sects.add(section_title_chap)
            else:
                section_summs.append((section_title_chap, [], link_summ))
        if not section_summs:
            print('  could not find summaries for {}'.format(title))
            continue
        book_summ = BookSummary(title=title, author=author, genre=None, plot_overview=plot_summ,
                                source='novelguide', section_summaries=section_summs, summary_url=url)

        book_summaries.append(book_summ)
        num_books = len(book_summaries)
        if num_books > 1 and num_books % save_every == 0:
            with open(out_name, 'wb') as f:
                pickle.dump(book_summaries, f)
            print("Done scraping {} books".format(num_books))

    print('Scraped {} books from novelguide'.format(len(book_summaries)))
    with open(out_name, 'wb') as f:
        pickle.dump(book_summaries, f)
    print('wrote to', out_name)
    return book_summaries


if __name__ == "__main__":
    args = parser.parse_args()
    catalog = load_catalog(CATALOG_NAME)
    if args.full:
        title_set = None
    else:
        print('limiting to books from', CATALOG_NAME)
        title_set = set(catalog.keys())

    if args.archived:
        books_list = get_archived(BOOKS_LIST, year=2022)
    else:
        books_list = BOOKS_LIST
    title_url_map = get_title_url_map(books_list, title_set=title_set)
    print('{} book pages total'.format(len(title_url_map)))
    book_summaries = get_summaries(title_url_map, args.out_name, args.use_pickled, args.archived,
                                   args.update_old, args.get_text, args.save_every, args.sleep)
    # with open(args.out_name, 'rb') as f:
    #    book_summaries = pickle.load(f)

    book_summaries_overlap = gen_gutenberg_overlap(book_summaries, catalog, filter_plays=True)
    book_summaries_overlap = manual_fix(book_summaries_overlap)
    book_summaries_overlap = manual_fix_individual(book_summaries_overlap, args.get_text)

    with open(args.out_name_overlap, 'wb') as f:
        pickle.dump(book_summaries_overlap, f)
    print('wrote summaries to {}'.format(args.out_name_overlap))

    out_name = 'urls/chapter-level/novelguide.tsv'
    write_sect_links(out_name, book_summaries_overlap)
    print(f'wrote urls to {out_name}')
