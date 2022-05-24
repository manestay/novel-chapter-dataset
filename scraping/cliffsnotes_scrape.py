"""
cliffsnotes_scrape.py

Scrapes cliffsnotes.com for summaries. Outputs to pickled list of BookSummary objects.

Optional flags to 1) use the archived version of pages, 2) scrape all books, instead of only those in Gutenberg catalog.
"""

import argparse
import os
import time
import urllib.parse

import dill as pickle

from archive_lib import get_archived, get_orig_url
from scrape_lib import (BookSummary, gen_gutenberg_overlap, get_absolute_links,
                        get_soup, load_catalog, roman_to_int, write_sect_links,
                        standardize_sect_title, standardize_title)
from scrape_vars import CATALOG_NAME, NON_NOVEL_TITLES

PANE_NAME = 'medium-3 columns clear-padding-left clear-padding-for-small-only sidebar-navigation-gray'
BASE_URL = 'https://www.cliffsnotes.com/'
BOOKS_LIST = 'https://www.cliffsnotes.com/literature?filter=ShowAll&sort=TITLE'
OUT_NAME_ALL = 'pks/summaries_cliffsnotes_all.pk'
OUT_NAME_OVERLAP = 'pks/summaries_cliffsnotes.pk'


parser = argparse.ArgumentParser(description='scrape cliffsnotes')
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
    written_by = soup.find(class_='title-wrapper').find('h2')
    if not written_by:
        return ''
    assert written_by['id'] == 'phsubheader_0_spAuthor'
    return written_by.text.strip()


def get_sections(soup, base_url, archived=False, update_old=False, pane_name=PANE_NAME):
    sections = []

    for link in soup.find(class_=pane_name).findAll('li'):
        if 'summary-and-analysis' in link.a['href']:
            sections.append(link)

    section_urls = []
    for section in sections[1:]:
        name = section.span.text
        url = urllib.parse.urljoin(base_url, section.a['href'])
        section_urls.append((name, url))

    return section_urls


def get_plot_summary(soup, base_url, archived=False, update_old=False, pane_name=PANE_NAME):
    summaries = []
    for link in soup.find(class_=pane_name).findAll('li'):
        if 'summary' in link.text.lower():
            summaries.append(link)

    if len(summaries) > 1:
        # Assume that first one is overall book/play summary. Hold for most cases
        href = summaries[0].a['href']
        link = urllib.parse.urljoin(base_url, href)
        if archived:
            link = get_archived(get_orig_url(href), update_old)
        plot_summary = get_section_summary(link, base_url, archived, update_old)
        return plot_summary
    else:
        return None


class BreakIt(Exception):
    pass


def get_section_summary(url, base_url, archived=False, update_old=False):
    sense37, analysis_count = False, 0  # manual fix for this page with 2 Analysis headings
    if 'https://www.cliffsnotes.com/literature/s/sense-and-sensibility/summary-and-analysis/chapter-37' in url:
        sense37 = True
    analysis_found = False
    soup_all = get_soup(url)
    soup = soup_all.find(class_='copy')
    if not soup: # this happens if out of date, need to update the archive.org version
        print(f'{url} NO COPY CLASS!')
        return []
    children = list(soup.children)

    section_summary = []
    for i, child in enumerate(children):
        try:
            if len(child.findAll('p')) > 0:
                for c in child.children:
                    try:
                        if c.name == 'p':
                            text = c.text.strip()
                            if text == 'Analysis':
                                analysis_found = True
                                raise BreakIt
                            if len(text) > 0 and text != 'Summary':
                                section_summary.append(text)
                    except AttributeError:
                        continue
            elif child.name == 'p':
                text = child.text.strip()
                if sense37 and text == 'Analysis':
                    sense37 = False
                    continue
                elif text == 'Analysis':
                    analysis_found = True
                    break
                if len(text) > 0 and text != 'Summary':
                    section_summary.append(text)
            elif child.name == 'h2' or child.name == 'h3':
                text = child.text.strip()
                if text == 'Analysis':
                    analysis_found = True
                    break
        except AttributeError:
            continue
        except BreakIt:
            break
    if len(section_summary) > 0 and not analysis_found:
        next_soup = soup_all.find(class_='small-6 columns clear-padding-right')
        if not next_soup:
            return section_summary
        href = next_soup.a['href']
        if href.endswith('character-list'):
            return section_summary
        # if 'book-summary-2' in href: # TODO: delete this
        #     next_url = 'https://' + get_orig_url(href)
        elif archived:
            next_url = get_archived(get_orig_url(href), update_old)
        else:
            next_url = urllib.parse.urljoin(base_url, href)

        is_continued = 'continued on next page' in section_summary[-1].lower()
        if is_continued:
            del section_summary[-1]
        cond = next_url.startswith(url)
        if is_continued or cond:
            soup = get_soup(next_url)
            try:
                summary = get_section_summary(next_url, base_url, archived, update_old)
                section_summary.extend(summary)
            except IndexError:
                pass
    return section_summary


def get_summaries(books_list, base_url, out_name, use_pickled=False, archived=False, title_set=None,
                  update_old=False, get_text=True, save_every=5, sleep=0):
    if use_pickled and os.path.exists(out_name):
        with open(out_name, 'rb') as f1:
            book_summaries = pickle.load(f1)
        print('loaded {} existing summaries, resuming'.format(len(book_summaries)))
        done = set([x.title for x in book_summaries])
    else:
        book_summaries = []
        done = set()

    soup = get_soup(books_list)
    title_url_map = {}
    for book in soup.find(class_='content active').findAll('li'):
        title = book.find('h4').text.strip()
        if title_set and title not in title_set:
            continue
        url = urllib.parse.urljoin(base_url, book.a['href'])
        title_url_map[title] = url
    print('found {} books'.format(len(title_url_map)))
    for i, (book, url) in enumerate(title_url_map.items()):
        if book in done:
            continue
        if sleep:
            time.sleep(sleep)
        print('processing {} {}'.format(book, url))

        soup = get_soup(url)
        author = get_author(soup)
        if not author:
            print('author not found, skipping', book, url)
            continue
        if get_text:
            plot_overview = get_plot_summary(soup, base_url, archived, update_old)
        else:
            plot_overview = ''

        section_summaries = []
        for (section_name, summ_url) in get_sections(soup, base_url, archived, update_old):
            if get_text:
                summary = get_section_summary(summ_url, base_url, archived, update_old)
            else:
                summary = []
            section_summaries.append((section_name, summary, summ_url))
        bs = BookSummary(title=book,
                         author=author,
                         genre=None,  # TODO: Implement retrieving genre from external source
                         plot_overview=plot_overview,
                         source='cliffsnotes',
                         section_summaries=section_summaries,
                         summary_url=url)

        book_summaries.append(bs)
        num_books = len(book_summaries)
        if num_books > 1  and num_books % save_every == 0:
            with open(out_name, 'wb') as f:
                pickle.dump(book_summaries, f)
            print("Done scraping {} books".format(num_books))

    print('Scraped {} books from cliffsnotes'.format(len(book_summaries)))
    with open(out_name, 'wb') as f:
        pickle.dump(book_summaries, f)
    print('wrote to', out_name)
    return book_summaries


def manual_fix_individual(book_summaries):
    """
    Note we do not manually fix the plays, since we do not use them in the literature dataset.
    """
    start = False  # to debug
    book_summaries_new = []
    for idx, book_summ in enumerate(book_summaries):
        sect_summs_new = []
        sect_summs_old = book_summ.section_summaries
        title = book_summ.title
        # if idx == 79:
        #     start = True
        if title in NON_NOVEL_TITLES:
            continue
        if title in set(['Adam Bede', 'The Brothers Karamazov', 'The Age of Innocence', 'Siddhartha', 'Silas Marner',
                         'The Three Musketeers']):
            sect_summs_new = [(x[0].split(':', 1)[1].strip(), *x[1:]) for x in sect_summs_old]
            if title == 'The Brothers Karamazov':
                assert sect_summs_new[-1][0] == 'Epilogue'
                sect_summs_new[-1] = ('Book 13', *sect_summs_new[-1][1:])
            if title == 'Siddhartha':
                sect_summs_new = [('Samsara' if chap_title == 'Sansara' else
                                  'Amongst the People' if chap_title == 'With the Childlike People' else chap_title, \
                                      chap_summ, link) for chap_title, chap_summ, link in sect_summs_new]
        elif title in set(["Tess of the d'Urbervilles"]):
            sect_summs_new = [(x[0].rsplit(':', 1)[1].strip(), *x[1:]) for x in sect_summs_old]
        elif title == 'White Fang':
            sect_summs_new = [(x[0].split('(', 1)[0].strip(), *x[1:]) for x in sect_summs_old]
        elif title == 'The Adventures of Huckleberry Finn':
            sect_summs_new = sect_summs_old
            sect_summs_new[-1] = ('Chapter 43', *sect_summs_new[-1][1:])
            assert sect_summs_new[0][0] == 'Notice; Explanatory'
            sect_summs_new = sect_summs_new[1:]
        elif title == "A Connecticut Yankee in King Arthur's Court":
            sect_summs_new = sect_summs_old
            sect_summs_new[-1] = ('Chapter 39-45', *sect_summs_new[-1][1:])
        elif title == 'Jane Eyre':
            sect_summs_new = sect_summs_old
            sect_summs_new[-1] = ('Chapter 38', *sect_summs_new[-1][1:])
        elif title in set(['The Mill on the Floss', 'My Ántonia']):
            for sect_title, summ, link in sect_summs_old:
                if sect_title.startswith('Introduction'):
                    pass
                elif sect_title.endswith('Conclusion'):
                    sect_title = 'Book 7: Conclusion'
                else:
                    arr = sect_title.split()
                    sect_title = '{} {} {} {}'.format(arr[0], arr[1], arr[-2], arr[-1])
                sect_summs_new.append((sect_title, summ, link))
        elif title == "The Turn of the Screw":
            sect_summs_new = [(x[0].replace('Section', 'Chapter').replace('"', ''), *x[1:]) for x in sect_summs_old]
        elif title == 'The Way of All Flesh':
            for sect_title, summ. link in sect_summs_old:
                if '(' in sect_title:
                    chapter_nums = sect_title.split('(', 1)[1].split(' ', 1)[0].replace(')', '')
                    sect_title = 'Chapter {}'.format(chapter_nums)
                sect_title = sect_title.replace('87', '86', 1)  # fix typo
                sect_summs_new.append((sect_title, summ, link))
        elif title == 'The Secret Sharer':
            sect_summs_new = [(x[0].replace('Part', 'Chapter'), *x[1:]) for x in sect_summs_old]
        elif title == 'Winesburg, Ohio':
            sect_summs_new = [(x[0].replace('"', ''), *x[1:]) for x in sect_summs_old]
        elif title == 'Treasure Island':
            treasure_chapters = ["1-6", "7-12", "13-15", "16-21", "22-27", "28-34"]
            for i, (chap, sect_summ) in enumerate(zip(treasure_chapters, sect_summs_old)):
                sect_summs_new.append(('Chapter ' + chap, *sect_summ[1:]))
        elif title == 'Emma':
            for sect_title, summ, link in sect_summs_old:
                if 'Volume 1' in sect_title:
                    offset = 0
                elif 'Volume 2' in sect_title:
                    offset = 18
                else:
                    offset = 36
                last = sect_title.rsplit(' ', 1)[-1]

                if '-' in last:
                    first, last = [roman_to_int(x) + offset for x in last.split('-', 1)]
                    sect_title = 'Chapter {}-{}'.format(first, last)
                else:
                    sect_title = 'Chapter {}'.format(roman_to_int(last) + offset)
                sect_summs_new.append((sect_title, summ, link))
        elif title == "War and Peace":
            ssn = [(standardize_sect_title(x[0], False), *x[1:]) for x in sect_summs_old]
            book_summ_new = book_summ._replace(section_summaries=ssn)
        else:
            sect_summs_new = sect_summs_old

        if sect_summs_new:
            sect_summs_new = [(standardize_sect_title(x[0]), *x[1:]) for x in sect_summs_new]
            title_new = standardize_title(title)
            if title_new != title:
                print('renamed {} -> {}'.format(title, title_new))
                title = title_new
            book_summ_new = book_summ._replace(section_summaries=sect_summs_new, title=title_new)

        book_summaries_new.append(book_summ_new)
        if start:  # for debugging
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
        # TODO: figure out why calling the function doesn't work
        # books_list = get_archived(BOOKS_LIST)
        books_list = 'https://web.archive.org/web/20201107055349/https://www.cliffsnotes.com/literature?filter=ShowAll&sort=TITLE'
        base_url = 'https://web.archive.org/'
    else:
        books_list = BOOKS_LIST
        base_url = BASE_URL
    book_summaries = get_summaries(books_list, base_url, args.out_name, args.use_pickled,
                                   args.archived, title_set, args.update_old, args.get_text, args.save_every, args.sleep)
    # with open(args.out_name, 'rb') as f:
    #     book_summaries = pickle.load(f)
    book_summaries_overlap = gen_gutenberg_overlap(book_summaries, catalog, filter_plays=True)
    book_summaries_overlap = manual_fix_individual(book_summaries_overlap)

    with open(args.out_name_overlap, 'wb') as f:
        pickle.dump(book_summaries_overlap, f)
    print('wrote summaries to {}'.format(args.out_name_overlap))

    out_name = 'urls/chapter-level/cliffsnotes.tsv'
    write_sect_links(out_name, book_summaries_overlap)
    print(f'wrote urls to {out_name}')
