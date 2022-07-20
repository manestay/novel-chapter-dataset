"""
sparknotes_scrape.py

Scrapes sparknotes for summaries. Outputs to pickled list of BookSummary objects.

Optional flags to 1) use the archived version of pages, 2) scrape all books, instead of only those in Gutenberg catalog.
"""

import argparse
import os
import re
import time
import urllib.parse

import dill as pickle

from archive_lib import get_archived, get_orig_url
from scrape_lib import BookSummary, get_soup, load_catalog, gen_gutenberg_overlap, standardize_title, clean_title, \
                       clean_sect_summ, standardize_sect_title, fix_multibook, fix_multipart, write_sect_links
from scrape_vars import NON_NOVEL_TITLES, RE_SUMM, CATALOG_NAME

PANE_NAME = 'navSection__list js--collapsible'
BASE_URL = 'https://www.gradesaver.com/'
OUT_NAME_ALL = 'pks/summaries_gradesaver_all.pk'
OUT_NAME_OVERLAP = 'pks/summaries_gradesaver.pk'
BOOKS_LIST = 'https://www.gradesaver.com/study-guides'
HEADINGS = ['finale:', 'analysis', 'part', 'chapter', 'book', 'act', 'volume', 'section', 'opening prelude',
            'summary', 'summaries', 'summary:', 'summaries:']
SIDDHARTHA_TITLES  = set(["The Brahmins Son", "With the Samanas", "Goatama", "Awakening", "Kamala",
                          "Amongst the People", "Samsara", "By the River", "The Ferryman", "The Son", "Om", "Govinda"])

parser = argparse.ArgumentParser(description='scrape gradesaver')
parser.add_argument('out_name', nargs='?', default=OUT_NAME_ALL, help='name of pickle file for all summaries')
parser.add_argument('out_name_overlap', nargs='?', default=OUT_NAME_OVERLAP, help='name of pickle file for overlapping summaries')
parser.add_argument('--archived', action='store_true', help='always use archived versions of scripts')
parser.add_argument('--use-pickled', action='store_true', help='use existing (partial) pickle')
parser.add_argument('--full', action='store_true', help='get all books, not just those in Gutenberg')
parser.add_argument('--catalog', default=CATALOG_NAME, help='get all books, not just those in Gutenberg')
parser.add_argument('--update-old', action='store_true', help='update out-of-date archived version')
parser.add_argument('--save-every', default=2, type=int, help='interval to save pickled file')
parser.add_argument('--sleep', default=0, type=int, help='sleep time between scraping each book')
parser.add_argument('--no-text', dest='get_text', action='store_false', help='do not get book text')


def get_author(soup):
    try:
        author = soup.find(itemprop='author').a.text.strip()
    except AttributeError:
        author = ''
    return author


def get_plot_summary(soup, pane_name, base_url, archived, update_old):
    summaries = []
    for link in soup.find(class_=pane_name).findAll('li'):
        if 'summary' in link.text.lower():
            summaries.append(link)

    if len(summaries) > 1:
        # Assumption first one is overall book/play summary. Hold for most cases
        if archived:
            orig_url = get_orig_url(summaries[0].a['href'])
            link = get_archived(orig_url, update_old)
        else:
            link = urllib.parse.urljoin(base_url, summaries[0].a['href'])
        plot_summary = get_section_summary(link)
        return plot_summary
    else:
        return None


def get_section_summary(url):
    soup = get_soup(url)
    children = list(soup.find(class_='section__article').children)
    def _is_heading(child):
        if child.name not in ['h2', 'h3', 'h4', 'p']:
            return False
        words = child.text.lower().strip().split()
        if child.name in ['h2', 'h3', 'h4']:
            return True
        elif child.strong is not None:
            return True
        elif child.name == 'p' and len(words) < 20:
            if any(heading in words for heading in HEADINGS):
                return True
            else:
                return False

    section_summary = []
    ind = 0
    while ind < len(children):
        if not _is_heading(children[ind]) and children[ind].name != 'p':
            ind += 1
            continue
        #New sub-section
        if _is_heading(children[ind]):
            sub_section_name = children[ind].text.strip()
            ind += 1
        else:
            sub_section_name = None

        subsection = []
        while ind < len(children) and not _is_heading(children[ind]):
            if children[ind].name == 'p':
                subsection.append(children[ind].text.strip())
            ind += 1

        if sub_section_name and 'analysis' in sub_section_name.lower():
            continue
        section_summary.append((sub_section_name, subsection))

    return section_summary


def get_sections(soup, pane_name, base_url, archived=False, update_old=False):
    summaries = None
    for link in soup.find(class_=pane_name).findAll('li'):
        if 'summary and analysis' in link.text.lower().strip():
            summaries = link
            break

    sections = []
    try:
        for link in summaries.findAll('li'):
            name = link.text.strip()
            url = urllib.parse.urljoin(base_url, link.a['href'])

            sections.append((name, url))
    except AttributeError:
        pass

    if len(sections) == 0:
        try:
            name = summaries.text.strip()
            url = urllib.parse.urljoin(base_url, summaries.a['href'])
            if archived:
                orig_url = get_orig_url(summaries.a['href'])
                url = get_archived(orig_url, update_old)

            sections.append((name, url))
        except:
            pass

    return sections


def get_summaries(books_list, base_url, out_name, pane_name, use_pickled=False, title_set=None,
                  archived=False, update_old=False, get_text=True, save_every=5, sleep=0):
    if use_pickled and os.path.exists(out_name) and os.path.getsize(out_name):
        with open(out_name, 'rb') as f1:
            book_summaries = pickle.load(f1)
        print('loaded {} existing summaries, resuming'.format(len(book_summaries)))
        done = set([x.title for x in book_summaries])
    else:
        book_summaries = []
        done = set()

    soup = get_soup(books_list)
    title_url_map = {}
    for link in soup.find(class_='alphabits').findAll('li'):
        href = link.a['href']
        print(f'processing {href}', end='\r')
        page_url = urllib.parse.urljoin(base_url, href)
        soup = get_soup(page_url)
        for book in soup.find(class_='columnList').findAll('li'):
            title = book.a.text.strip()
            if title_set and title not in title_set:
                continue
            url = urllib.parse.urljoin(base_url, book.a['href'])
            title_url_map[title] = url
    print()

    print('found {} books'.format(len(title_url_map)))
    for i, (book, url) in enumerate(title_url_map.items()):
        if book in done:
            continue
        if sleep:
            time.sleep(sleep)
        if archived:
            url = get_archived(url, update_old)
        print('processing {} {}'.format(book, url))
        soup = get_soup(url)
        author = get_author(soup)
        if get_text:
            plot_overview = get_plot_summary(soup, pane_name, base_url, archived, update_old)
        else:
            plot_overview = []

        section_summaries = []
        sections = get_sections(soup, pane_name, base_url, archived, update_old)
        for (section_name, summ_url) in sections:
            if get_text:
                summary = get_section_summary(summ_url)
            else:
                summary = []
            section_summaries.append((section_name, summary, summ_url))
        bs = BookSummary(title=book,
                         author=author,
                         genre=None,  # TODO: Need to fix this and get genre from external source
                         plot_overview=plot_overview,
                         source='gradesaver',
                         section_summaries=section_summaries,
                         summary_url=url)

        book_summaries.append(bs)
        num_books = len(book_summaries)

        if num_books > 1 and num_books % save_every == 0:
            print("Done scraping {} books".format(num_books))
            with open(out_name, 'wb') as f:
                pickle.dump(book_summaries, f)

    print('Scraped {} books from gradesaver'.format(len(book_summaries)))
    with open(out_name, 'wb') as f:
        pickle.dump(book_summaries, f)
    print('wrote to', out_name)
    return book_summaries


def flatten(book_summaries, get_text=True):
    book_summaries_new = []
    if not get_text:
        return book_summaries
    for book_summ in book_summaries:
        sect_summ_new = []
        sect_summs_old = book_summ.section_summaries
        for sect_tup in sect_summs_old:
            multi_sect_title, sect_summs, link = sect_tup
            if len(sect_summs) == 1 and (not sect_summs[0][0] or re.match(RE_SUMM, sect_summs[0][0])):
                sect_summs[0] = (multi_sect_title, *sect_summs[0][1:])
            elif len(sect_summs) == 2 and not sect_summs[0][0] and not sect_summs[0][1][0] and \
                re.match(RE_SUMM, sect_summs[1][0]):
                sect_summs[1] = (multi_sect_title, *sect_summs[1][1:])
                del sect_summs[0]
            sect_summs = [(*x, link) for x in sect_summs]
            sect_summ_new.extend(sect_summs)
        book_summ_new = book_summ._replace(section_summaries=sect_summ_new)
        book_summaries_new.append(book_summ_new)
    return book_summaries_new


def manual_fix(book_summaries, get_text=True):
    """ First pass manual fix of chapter titles. Need to do book-specific ones later for edge cases.
    """
    book_summaries_new = []
    for book_summ in book_summaries:
        title = book_summ.title
        section_summaries_new = []
        sect_summs_old = book_summ.section_summaries
        i = 0
        num_summs = len(sect_summs_old)
        while i < num_summs:
            chap_title, sect_summ, link = sect_summs_old[i]
            chap_title, sect_summ = clean_title(chap_title), clean_sect_summ(sect_summ)
            chap_title_orig, sect_summ_orig = chap_title, sect_summ
            empty_ss = not sect_summ or (sect_summ and not sect_summ[0] and len(sect_summ) <= 1)
            if not chap_title and empty_ss:
                i += 1
                continue
            if chap_title and not sect_summ and get_text:
                arr = chap_title.split(':', 1)
                if i + 1 < num_summs:
                    next_chap, next_summ, next_link = sect_summs_old[i+1]
                    if re.match(RE_SUMM, next_chap) and next_summ:
                        sect_summ1 = next_summ
                        i += 2
                        section_summaries_new.append((chap_title, sect_summ1, link))
                        continue
                if len(arr) != 2 or not arr[1]:  # have to fix in a second pass
                    section_summaries_new.append((chap_title, sect_summ, link))
                    i += 1
                    continue
                chap_title, sect_summ1 = arr
                chap_title, sect_summ1 = clean_title(chap_title), clean_sect_summ([sect_summ1])


                if len(sect_summ1[0]) > 100:
                    section_summaries_new.append((chap_title, sect_summ1, link))
                else:  # split on a subtitle, handle later
                    section_summaries_new.append((chap_title_orig, sect_summ_orig, link))
            # elif not chap
            else:
                section_summaries_new.append((chap_title_orig, sect_summ_orig, link))
            i += 1
        book_summ_new = book_summ._replace(section_summaries=section_summaries_new)
        book_summaries_new.append(book_summ_new)
    return book_summaries_new


def manual_fix_individual(book_summaries, get_text=True):
    """
    Note we do not manually fix the plays, since we do not use them in the literature dataset.
    """
    def fix_north(title):
        return title.replace(',', ':', 1).replace('Vol.', 'Book', 1).replace('Volume', 'Book', 1) \
                    .replace('of ', '').replace('Chaper', 'Chapter')
    start = False
    book_summaries_new = []
    for idx, book_summ in enumerate(book_summaries):
        sect_summs_new = []
        sect_summs_old = book_summ.section_summaries
        title = book_summ.title
        # if idx == 125:
        #     start = True
        if title in NON_NOVEL_TITLES:
            continue
        elif title in set(["Connecticut Yankee in King Arthur's Court", "Little Women", "Walden"]):
            sect_summs_new = [(' '.join(chap_title.split(' ', 2)[0:2]), sect_summ, link)
                              for chap_title, sect_summ, link in sect_summs_old if chap_title]
        elif title in set(['Germinal', "Little Dorrit", "Our Mutual Friend", "The War of the Worlds"]) and get_text:
            sect_summs_new = [(x[0].replace(',', ':', 1), *x[1:]) for x in sect_summs_old]
        elif title == 'The Adventures of Huckleberry Finn':
            if get_text:
                sect_summs_new = [x for x in sect_summs_old if x[0]]
            else:
                sect_summs_new = [[x[0].replace(' to Chapter ', '-'), *x[1:]] for x in sect_summs_old]
        elif title == 'The Age of Innocence':
            for chap_title, sect_summ, link in sect_summs_old:
                arr = chap_title.split(':', 1)
                if len(arr) == 2:
                    chap_title = clean_title(arr[0])
                    sect_summ = [arr[1].strip()] + sect_summ
                if not chap_title.startswith('Chapter'):
                    continue
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'Alice in Wonderland':
            for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old, 1):
                if not chap_title:
                    chap_title = 'Chapter {}'.format(i)
                else:
                    chap_title = chap_title.split(':', 1)[0]
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'The Ambassadors' and get_text:
            book_idx = 'O'
            for chap_title, sect_summ, link in sect_summs_old:
                if chap_title.startswith('Volume'):
                    continue
                if chap_title.startswith('Book'):
                    book_idx = chap_title.split(' ', 1)[-1]
                    continue
                sect_idx = chap_title.split(' ', 1)[-1]
                chap_title = 'Book {}: Chapter {}'.format(book_idx, sect_idx)
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'Black Beauty':
            sect_summs_new = [(chap_title.split(', ', 1)[-1], sect_summ, link)
                              for chap_title, sect_summ, link in sect_summs_old]
        elif title == 'Bleak House':
            for chap_title, sect_summ, link in sect_summs_old:
                if not chap_title:
                    prev_title = sect_summs_new[-1][0]
                    if prev_title == 'Chapters 60-63':
                        chap_title = 'Chapter 64-67'
                elif not chap_title.startswith('Chapter'):
                    continue
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'The Count of Monte Cristo':
            sect_summs_new = [x for x in sect_summs_old if not x[0].startswith('The book has')]
        elif title == 'Emma':
            for chap_title, sect_summ, link in sect_summs_old:
                if chap_title.startswith('Chapter Eighteen:'):
                    chap_title, sect_summ = chap_title.split(':', 1)
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'Ethan Frome' and get_text:
            assert sect_summs_old[0][0] == sect_summs_old[1][0]== ''
            book_summ.section_summaries[0] = ('Prologue', *book_summ.section_summaries[1][1:])
            book_summ.section_summaries[-1] = ('Epilogue', *book_summ.section_summaries[-1][1:])
            del book_summ.section_summaries[1]
            book_summ_new = book_summ
        elif title == 'Far from the Madding Crowd':
            for chap_title, sect_summ, link in sect_summs_old:
                if chap_title == '':
                    chap_title = 'Chapter 38-45'
                elif not chap_title.startswith('Chapter'):
                    continue
                elif chap_title == 'Chapters 54-Conclusion':
                    chap_title = 'Chapter 54-57'
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'Frankenstein':
            sect_summs_new = sect_summs_old
            sect_summs_new[-1] = ('Final Letters', *sect_summs_new[-1][1:])
        elif title == 'The American':
            sect_summs_new = [('Chapter {}'.format(chap_title) if not chap_title.startswith('Ch') else chap_title,
                               sect_summ, link) for chap_title, sect_summ, link in sect_summs_old]
        elif title == 'Great Expectations' and get_text:
            i = 1
            for chap_title, sect_summ, link in sect_summs_old:
                if not chap_title.startswith(('Part', 'Chapter')):
                    addtl_text = [chap_title] + sect_summ
                    sect_summs_new[-1] = (sect_summs_new[-1][0], sect_summs_new[-1][1] + addtl_text)
                else:
                    chap_title = 'Chapter {}'.format(i)
                    sect_summs_new.append((chap_title, sect_summ, link))
                    i += 1
        elif title == 'The Hound of the Baskervilles':
            for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old):
                chap_title = chap_title.split(':', 1)[0]
                if not chap_title.startswith('Chapter'):
                    continue
                if not sect_summ and get_text:
                    assert sect_summs_old[i+1][0].startswith(('This chapter', 'In this final'))
                    sect_summ = [sect_summs_old[i+1][0]] + sect_summs_old[i+1][1]
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'Howards End':
            for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old):
                if not chap_title and len(sect_summ) == 2:
                    continue
                elif not chap_title:
                    chap_title = 'Chapter 16-19'
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == "Lady Audley's Secret":
            for chap_title, sect_summ, link in sect_summs_old:
                if chap_title == "Volume 3, Chapter 1":
                    chap_title = 'Chapter 1'
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == "Mary Barton":
            for chap_title, sect_summ, link in sect_summs_old:
                if not chap_title:
                    chap_title = 'Chapters XVI-XX'
                elif chap_title == 'Chapters XXI-XV':
                    chap_title = 'Chapters XXI-XXV'
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'Moby Dick':
            for chap_title, sect_summ, link in sect_summs_old:
                if not chap_title.startswith('Chapter'): continue
                chap_title = chap_title.split(':', 1)[0].replace('One Hundred and ', 'One-Hundred-', 1) \
                                       .replace('One Hundred', 'One-Hundred', 1)
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'Northanger Abbey':
            sect_summs_new = [(fix_north(x[0]), *x[1:]) for x in sect_summs_old]
        elif title in set(["The Vicar of Wakefield", 'Uncle Tom\'s Cabin']):
            for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old):
                if not chap_title.startswith('Chapter'): continue
                if not sect_summ and get_text:
                    sect_summ = [sect_summs_old[i+1][0]] + sect_summs_old[i+1][1]
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'Persuasion':
            for chap_title, sect_summ, link in sect_summs_old:
                if not chap_title:
                    chap_title = 'Chapter 22-24'
                elif chap_title.startswith('The final chapter'):
                    continue
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title in set(["The Scarlet Letter", "The Blithedale Romance"]):
            sect_summs_new = [x for x in sect_summs_old if x[0].startswith('Chapter')]
        elif title == 'Siddhartha' and get_text:
            for _, lines, link in sect_summs_old:
                sect_summ_curr = []
                for line in lines:
                    if line in SIDDHARTHA_TITLES:
                        if sect_summ_curr:
                            sect_summs_new.append((chap_title, sect_summ_curr, link))
                            sect_summ_curr = []
                        chap_title = line.replace("The Brahmins Son", "The Brahmin's Son").replace('Goatama', 'Gotama')
                    else:
                        sect_summ_curr.append(line)
                if sect_summ_curr:
                    sect_summs_new.append((chap_title, sect_summ_curr, link))
                    sect_summ_curr = []
        elif title == 'A Study in Scarlet':
            sect_summs_new = [(x[0].split(':', 1)[0].strip().replace(',', ':', 1), *x[1:]) for x in sect_summs_old]
        elif title == 'Treasure Island':
            for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old):
                if not sect_summ and get_text:
                    sect_summ = sect_summs_old[i+1][1]
                elif not chap_title:
                    continue
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'A Study in Scarlet':
            sect_summs_new = [(x[0].replace('of ', '', 1), *x[1:]) for x in sect_summs_old]
        elif title == "The Valley of Fear":
            sect_summs_new = [x for x in sect_summs_old if x[1]]
        elif title == "Villette":
            for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old):
                prev_chap = sect_summs_new[-1][0] if sect_summs_new else ''
                if prev_chap.endswith('XIII'):
                    sect_summ = [chap_title] + sect_summ
                    chap_title = "Chapter 14-16"
                elif prev_chap.endswith('XXV'):
                    sect_summ = [chap_title] + sect_summ
                    chap_title = "Chapter 26-28"
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'What Maisie Knew':
            book_summ.section_summaries[0] = ('Introduction', book_summ.section_summaries[0][1])
            book_summ_new = book_summ
        elif title == 'Winesburg, Ohio':
            for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old):
                chap_title = chap_title.replace('"', '').replace("'", '').replace(' Summary ', ' ')
                if chap_title.startswith("Surrender"):
                    chap_title = "Godliness Part 3"
                elif chap_title.startswith("Terror"):
                    chap_title = "Godliness Part 4"
                elif chap_title.startswith("Prologue"):
                    chap_title = "The Book of the Grotesque"
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'Wuthering Heights':
            for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old):
                if not sect_summ and get_text:
                    next_chap, next_summ, link = sect_summs_old[i+1]
                    # Chapter 25 section has a typo https://www.gradesaver.com/wuthering-heights/study-guide/summary-chapters-21-25
                    if not next_summ and not chap_title == 'Chapter 25':
                        print("need to update Wuthering Heights")
                    sect_summ = next_summ
                elif not chap_title:
                    continue
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == "The Yellow Wallpaper" and get_text:
            all_sects = [x[1] for x in sect_summs_old]
            all_sects = [sublist for l in all_sects for sublist in l]
            sect_summs_new = [('book', all_sects, sect_summs_old[0][2])]
        elif title in set(["The Mill on the Floss", 'My Antonia', "A Tale of Two Cities",
                           'War and Peace']) and get_text:  # multibook
            book_count = 0
            seen = set()
            for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old):
                if not chap_title.startswith("Chapter") or chap_title.endswith('.'):
                    continue
                chap_title, book_count = fix_multibook(chap_title, book_count)
                if not sect_summ and get_text:
                    sect_summ = [sect_summs_old[i+1][0]] + sect_summs_old[i+1][1]
                if chap_title == "Book 2: Chapter 4 -":
                    chap_title = "Book 2: Chapter 4"
                if title == 'A Tale of Two Cities':
                    if chap_title in seen:
                        continue
                    seen.add(chap_title)
                    arr = chap_title.split(':')
                    if len(arr) == 3:
                        chap_title = ':'.join(arr[0:2])
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == 'Hard Times' and get_text:
            for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old):
                if chap_title.startswith('Book III'):
                    book_num = 3
                elif chap_title == 'Book II':
                    book_num = 2
                elif chap_title.startswith('Book the First') or chap_title.startswith('Book I'):
                    book_num = 1
                else:
                    chap_title = 'Book {}: {}'.format(book_num, chap_title.split(':', 1)[0])
                    sect_summs_new.append((chap_title, sect_summ, link))
        elif title in set(["Gulliver's Travels", "Jude the Obscure", "Madame Bovary", 'Crime and Punishment']) and get_text:  # multipart
            book_count = 0
            for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old):
                if title in set(["Gulliver's Travels", 'Crime and Punishment']) and not sect_summ:
                    sect_summ = [sect_summs_old[i+1][0]] + sect_summs_old[i+1][1]
                if not chap_title.startswith("Chapter"):
                    continue
                elif title == "Madame Bovary" and "-" in chap_title:
                    continue
                chap_title, book_count = fix_multipart(chap_title, book_count)
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title in set(['Pride and Prejudice', 'Jane Eyre']) and get_text:
            for i, (chap_title, sect_summ, link) in enumerate(sect_summs_old, 1):
                chap_title = 'Chapter {}'.format(i)
                if title == 'Pride and Prejudice' and chap_title == 'Chapter 60':
                    sect_summs_new.append((chap_title, sect_summ[0:1], link))
                    sect_summs_new.append(('Chapter 61', sect_summ[1:], link))
                    continue
                sect_summs_new.append((chap_title, sect_summ, link))
        elif title == "The Phantom of the Opera":
            book_summ.section_summaries[-1] = ('Chapter 21-Epilogue', *book_summ.section_summaries[-1][1:])
            book_summ_new = book_summ
        elif title == "The Picture of Dorian Gray":
            sect_summs_new = sect_summs_old
            sect_summs_new[0] = ('Preface-Chapter 2', *sect_summs_new[0][1:])
        elif title == "Tess of the D'Urbervilles":
            if get_text:
                sect_summs_new = [(x[0], *x[1:]) for x in sect_summs_old if x[0].startswith('Chapter')]
            else:
                sect_summs_new = [(x[0].split(', ', 1)[1], *x[1:]) for x in sect_summs_old]
        elif title == 'Washington Square':
            sect_summs_new = [(x[0].replace(' Summaries', '', 1), *x[1:]) for x in sect_summs_old if x[0].startswith('Chapter')]

        elif title == "The Wind in the Willows":
            sect_summs_new = sect_summs_old
            sect_summs_new[-2] = (sect_summs_new[-2][0], sect_summs_new[-2][1] + [sect_summs_new[-1][0]])
            sect_summs_new.pop(-1)
        elif title == "The Brothers Karamazov":
            sect_summs_new = sect_summs_old
            sect_summs_new[-1] = ('Book 13', *sect_summs_old[-1][1:])
        elif title == "The Metamorphosis":
            sect_summs_new = [(x[0].replace('Chapter', 'Part', 1), *x[1:]) for x in sect_summs_old]
        elif title == 'The Secret Garden':
            assert sect_summs_old[1][0] == 'Chapters 5-19'
            sect_summs_new = sect_summs_old
            sect_summs_new[1] = ('Chapters 5-9', *sect_summs_old[1][1:])
        elif title == 'The Trial':
            continue
        elif not get_text and title == 'The War of the Worlds':
            for (chap_title, sect_summ, link) in sect_summs_old:
                parts = chap_title.split(', ')
                chap_title = f'{parts[0]}: {parts[1].split(" -", 1)[0]}-{parts[2].rsplit(" ", 1)[1]}'
                sect_summs_new.append((chap_title, sect_summ, link))
        elif not get_text and title == 'The Mill on the Floss':
            sect_summs_new = [[x[0].split('-', 1)[0], *x[1:]] for x in sect_summs_old]
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
        # if title == 'Frankenstein':
            print(title, idx)
            assert title == book_summaries_new[-1].title
            for i, x in enumerate(book_summaries_new[-1].section_summaries, 1):
                print(x[0] or x[1][0][0:100] + ' index ' + str(i))
            input()

    return book_summaries_new

if __name__ == "__main__":
    args = parser.parse_args()
    catalog = load_catalog(CATALOG_NAME)
    if args.full:
        title_set = None
    else:
        print('limiting to books from', CATALOG_NAME)
        title_set = set(catalog.keys())

    if args.archived:
        books_list = get_archived(BOOKS_LIST)
        base_url = 'https://web.archive.org'
    else:
        books_list = BOOKS_LIST
        base_url = BASE_URL

    book_summaries = get_summaries(books_list, base_url, args.out_name, PANE_NAME, args.use_pickled,
                                  title_set, args.archived, args.update_old, args.get_text,
                                  args.save_every, args.sleep)
    # with open(args.out_name, 'rb') as f1:
    #     book_summaries = pickle.load(f1)

    book_summaries = flatten(book_summaries, args.get_text)
    book_summaries_overlap = gen_gutenberg_overlap(book_summaries, catalog, filter_plays=True)
    book_summaries_overlap = manual_fix(book_summaries_overlap, args.get_text)
    book_summaries_overlap = manual_fix_individual(book_summaries_overlap, args.get_text)
    with open(args.out_name_overlap, 'wb') as f:
        pickle.dump(book_summaries_overlap, f)
    print('wrote summaries to {}'.format(args.out_name_overlap))

    out_name = 'urls/chapter-level/gradesaver.tsv'
    write_sect_links(out_name, book_summaries_overlap)
    print(f'wrote urls to {out_name}')
