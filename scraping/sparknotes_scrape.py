"""
sparknotes_scrape.py

Scrapes sparknotes for summaries. Outputs to pickled list of BookSummary objects.

By default, uses archived version of page if a "Page Not Found" error occurs. Recommended to use the
archived version, since the live version of sparknotes limits the rate of scraping.

Optional flags to 1) use the archived version of pages, 2) scrape all books, instead of only those
in Gutenberg catalog.

NOTE: Sparknotes did a major rehaul of their website mid-2020. This script probably has a lot of
code for the old version that can be refactored out.
"""

import argparse
import logging
import os
import re
import time
import urllib.parse

import dill as pickle
import requests

from archive_lib import get_archived, get_orig_url
from scrape_lib import BookSummary, get_soup, gen_gutenberg_overlap, clean_title, fix_multibook, fix_multipart, \
                       standardize_sect_title, standardize_title, load_catalog, get_clean_text, find_all_stripped
from scrape_vars import CATALOG_NAME, NON_NOVEL_TITLES, chapter_re

# default variables
GUIDES_PAGE = 'https://www.sparknotes.com/lit/#'
BASE_URL = 'https://www.sparknotes.com'
OUT_NAME_ALL = 'pks/summaries_sparknotes_all.pk'
OUT_NAME_OVERLAP = 'pks/summaries_sparknotes.pk'
SLEEP = 1  # comply with robots.txt

HTTPS = re.compile('https?://.*')
RE_ANALYSIS = re.compile('^((Overall )?Anal?ysis|Commentary)')
H3H4 = ['h3', 'h4']

parser = argparse.ArgumentParser(description='scrape sparknotes')
parser.add_argument('out_name', nargs='?', default=OUT_NAME_ALL, help='name of pickle file for all summaries')
parser.add_argument('out_name_overlap', nargs='?', default=OUT_NAME_OVERLAP, help='name of pickle file for overlapping summaries')
parser.add_argument('--archived', action='store_true', help='always use archived versions of scripts')
parser.add_argument('--use-pickled', action='store_true', help='use existing (partial) pickle')
parser.add_argument('--full', action='store_true', help='get all books, not just those in Gutenberg')
parser.add_argument('--catalog', default=CATALOG_NAME, help='get all books, not just those in Gutenberg')
parser.add_argument('--update-old', action='store_true', help='update out-of-date archived version')
parser.add_argument('--verbose', action='store_true', help='verbose output')
parser.add_argument('--save-every', default=2, type=int, help='interval to save pickled file')
parser.add_argument('--sleep', default=SLEEP, type=int, help='sleep time between scraping each book')


def get_author(soup):
    # written_by = soup.find(class_='subnav__writtenby')
    # try:
    #     return written_by.find('a').text.strip()
    # except AttributeError as e:
    #     print(e, 'in get_author')
    #     return ''
    written_by = soup.find(class_='TitleHeader_authorLink') or soup.find(class_='TitleHeader_authorName')
    return get_clean_text(written_by)


def get_plot_section_urls(url, base_url=BASE_URL, archived=False, update_old=False, sleep=SLEEP):
    soup = get_soup(url, sleep=sleep)
    plot_url = urllib.parse.urljoin(url, 'summary/')
    status_code = requests.get(plot_url).status_code
    if status_code in set([404, 500]):
        try:
            plot_url = get_archived(plot_url)
        except requests.exceptions.HTTPError as e:
            print('plot url not found at', plot_url)
            plot_url = ''

    section_urls = []
    seen = set()
    # lists = soup.find_all(class_='lists')
    # litems = lists[0].find_all('li')
    lists = soup.find_all(class_='landing-page__umbrella__section__list')
    litems = lists[1].find_all('li')
    if not litems:
        litems = lists[1].findAll('li')
    if len(litems) == 1:
        litems = lists[2].findAll('li')
    for item in litems:
        if not item.a:
            continue
        href = item.a.get('href')
        # if not href:
        #     pass
        if 'section' in href:
            if archived:
                orig_url = get_orig_url(href)
                url = get_archived(orig_url, update_old)
            else:
                url = urllib.parse.urljoin(base_url, item.a['href'])
                orig_url = url
            if orig_url not in seen:
                section_urls.append(url)
                seen.add(orig_url)

    return plot_url, section_urls


def _get_paragraphs(soup):
    paragraphs = []
    for paragraph in soup.find('div', {'class': 'studyGuideText'}).findAll('p'):
        paragraphs.append(paragraph.text.strip().replace('\n', ' '))

    return paragraphs


def get_plot_summary(url, sleep=SLEEP):
    soup = get_soup(url, sleep=sleep)

    pagination = soup.find(class_='pagination-links') or soup.find(class_='interior-sticky-nav__navigation__list--short')
    assert pagination is None

    studyguide = soup.find('div', {'class': 'studyGuideText'})
    if not studyguide:
        soup = get_soup(url, sleep=sleep)
        studyguide = soup.find('div', {'class': 'studyGuideText'})
    if not studyguide:
        archived_url = get_archived(url)
        print('WARNING: study guide not found for {} , trying archived version from {}'.format(url, archived_url))
        soup = get_soup(archived_url, sleep=sleep)
        studyguide = soup.find('div', {'class': 'studyGuideText'})
    if studyguide and not studyguide.findAll(H3H4):
        return _get_paragraphs(soup)
    else:
        return get_section_summary(url)[1]


def get_section_summary(section_url, archived=False, update_old=False, retry=0, sleep=SLEEP):
    def _get_type(child):
        name = child.name if child.name in H3H4 or child.name == 'p' else None
        return name

    def _get_first(soup):
        summary = soup.find('div', {'class': 'studyGuideText'})
        page_elements = list(summary.children)

        def _increment_ind(ind, page_elements=page_elements, ):
            while ind < len(page_elements) and _get_type(page_elements[ind]) is None:
                ind += 1
            return ind

        ind = _increment_ind(0)
        elem = page_elements[ind]

        paragraphs = []
        while _get_type(elem) == 'p':
            paragraphs.append(elem.text.strip().replace('\n', ' '))
            ind = _increment_ind(ind+1)
            elem = page_elements[ind]
        return paragraphs, ind

    def _scrape_page(soup, ind=0):
        sub_section_summaries = []
        summary = soup.find('div', {'class': 'studyGuideText'})
        page_elements = list(summary.children)

        def _increment_ind(ind, page_elements=page_elements):
            while ind < len(page_elements) and _get_type(page_elements[ind]) is None:
                ind += 1
            return ind
        # reached first subsection heading
        while ind < len(page_elements):
            ind = _increment_ind(ind)
            elem = page_elements[ind]
            el_type = _get_type(elem)
            assert el_type == 'h3' or el_type == 'h4'
            sub_section_name = elem.text.strip()

            ind = _increment_ind(ind+1)
            elem = page_elements[ind]
            paragraphs = []
            while _get_type(elem) == 'p':
                paragraphs.append(elem.text.strip().replace('\n', ' '))
                ind = _increment_ind(ind+1)
                if ind == len(page_elements):
                    break
                elem = page_elements[ind]

            sub_section_summaries.append((sub_section_name, paragraphs))

        return sub_section_summaries

    # scrape main page
    soup = get_soup(section_url, sleep=sleep)
    title_tag = soup.find(class_='interior-header__title__pagetitle') or soup.find('h2')
    ERRORS = set(['Something bad happened. Sorry.', 'read ECONNRESET'])
    is_error_page = not title_tag or title_tag.text in ERRORS
    if retry == 0 and is_error_page:
        return get_section_summary(section_url, archived, update_old, retry=1)
    # elif retry == 1 and is_error_page:
    #     archived_url = get_archived(section_url, update_old)
    #     print('WARNING: could not load page {} , trying archived version from {}'.format(section_url, archived_url))
        # return get_section_summary(archived_url, archived, update_old, retry=2)
    elif is_error_page:
        print('could not process {}'.format(section_url))
        os._exit(-1)
    section_name = title_tag.text.strip()
    studyguide = soup.find('div', {'class': 'studyGuideText'})
    if not studyguide.findAll(H3H4):
        paragraphs = _get_paragraphs(soup)
        summaries = [(section_name, paragraphs)]
    else:
        # skip any initial notes
        paragraphs, ind = _get_first(soup)
        summaries = _scrape_page(soup, ind)
    # scrape other pages, if any
    pagination = soup.find(class_='pagination-links') or \
                 soup.find(class_='interior-sticky-nav__navigation__list--short') or \
                 soup.find(class_='interior-sticky-nav__navigation')
    # # TODO: we can use below logic if sparknotes fixes www.sparknotes.com/lit/crime/section10/ ,
    # # which has chapters 1-4 on page 2, then chapter 5 on page 3
    # if summaries:
    #     at_analysis = re.match(RE_ANALYSIS, summaries[-1][0])
    # else:
    #     at_analysis = False
    # if not at_analysis and pagination is not None:
    if pagination is not None:
        pages = pagination.findAll('a')
        for page in pages[1:]:
            page_url = urllib.parse.urljoin(section_url, page['href'])
            if archived:
                orig_url = urllib.parse.urljoin(get_orig_url(section_url), page['href'])
                page_url = get_archived(orig_url, update_old)
                page_url = page_url.replace('/https://', '/', 1) # avoid strange bug with archive.org
            soup = get_soup(page_url, sleep=sleep)
            studyguide = soup.find('div', {'class': 'studyGuideText'})
            if not studyguide:
                soup = get_soup(page_url, sleep=sleep)
                studyguide = soup.find('div', {'class': 'studyGuideText'})
            # if not studyguide:
            #     archived_url = get_archived(page_url)
            #     print('WARNING: study guide not found for {} , trying archived version from {}'.format(page_url, archived_url))
            #     soup = get_soup(archived_url, sleep=sleep)
            #     studyguide = soup.find('div', {'class': 'studyGuideText'})
            if studyguide and not studyguide.findAll(H3H4):
                # no sub-sections, so get all paragraphs and add to previous
                paragraphs = _get_paragraphs(soup)
                summaries[-1][1].extend(paragraphs)
            else:
                # get paragraphs before first subsection
                paragraphs, ind = _get_first(soup)
                summaries[-1][1].extend(paragraphs)
                page_summaries = _scrape_page(soup, ind=ind)
                summaries.extend(page_summaries)
    return section_name, summaries


def get_summaries(guides_page, base_url, out_name, use_pickled=False, archived=False,
                  update_old=False, save_every=5, title_set=None, sleep=SLEEP, flatten=True):
    def add_summaries(url, section_summaries, flatten=True):
        # helper function
        summary_obj = get_section_summary(url, archived, update_old)
        multisect_title, sect_summs = summary_obj
        logging.info(multisect_title)
        if flatten:
            for sect_summ in sect_summs:
                sect_title, sect_paras = sect_summ
                if sect_title == 'Summary':
                    sect_title = multisect_title
                if re.match(RE_ANALYSIS, sect_title):
                    continue
                logging.info(sect_title)
                summary_obj_new = (sect_title, sect_paras)
                section_summaries.append(summary_obj_new)
        else:
            section_summaries.append(summary_obj)
    if use_pickled and os.path.exists(out_name):
        with open(out_name, 'rb') as f1:
            book_summaries = pickle.load(f1)
        print('loaded {} existing summaries, resuming'.format(len(book_summaries)))
        done = set([x.title for x in book_summaries])
    else:
        book_summaries = []
        done = set()

    soup = get_soup(guides_page, sleep=sleep)
    title_url_map = {}
    for section in soup.findAll('section'):
        for book in section.findAll('h4'):
            title = book.a.text.strip()
            if title_set and title not in title_set:
                continue
            url = urllib.parse.urljoin(base_url, book.a['href'])
            title_url_map[title] = url

    print('found {} books'.format(len(title_url_map)))
    for i, (book, url) in enumerate(title_url_map.items()):
        if book in done:
            continue
        if archived:
            url = get_archived(url, update_old)
        print('processing {} {}'.format(book, url))
        soup = get_soup(url, sleep=sleep)
        author = get_author(soup)
        if not author:
            print('author not found, skipping', book, url)
            continue
        plot_url, section_urls = get_plot_section_urls(url, base_url, archived, update_old)
        if plot_url:
            plot_overview = get_plot_summary(plot_url)
        else:
            plot_overview = None

        section_summaries = []
        for url in section_urls:
            add_summaries(url, section_summaries)
        if book == 'The Yellow Wallpaper':
            section_summaries = [('Book', plot_overview)]
        if not section_summaries:
            continue
        bs = BookSummary(title=book,
                         author=author,
                         genre=None,  # TODO: get genre from external source
                         plot_overview=plot_overview,
                         source='sparknotes',
                         section_summaries=section_summaries)

        book_summaries.append(bs)
        num_books = len(book_summaries)
        if num_books > 1 and num_books % save_every == 0:
            with open(out_name, 'wb') as f:
                pickle.dump(book_summaries, f)
            print("Done scraping {} books".format(num_books))

    print('Scraped {} books from sparknotes'.format(len(book_summaries)))
    with open(out_name, 'wb') as f:
        pickle.dump(book_summaries, f)
    print('wrote to', out_name)
    return book_summaries


def manual_fix(book_summaries):
    """ First pass manual fix of chapter titles. Need to do book-specific ones later for edge cases.
    """
    book_summaries_new = []
    for book_summ in book_summaries:
        title = book_summ.title
        section_summaries_new = []
        section_summaries_old = book_summ.section_summaries
        for i, curr_summ in enumerate(section_summaries_old):
            chap_title, sect_summ = curr_summ
            chap_title = clean_title(chap_title, preserve_summary=True)
            if chap_title.startswith('—'):
                chap_title = chap_title[1:].strip()
            if re.match(chapter_re, chap_title) and ':' in chap_title:
                chap_title = chap_title.split(':', 1)[0]
            if re.search(RE_ANALYSIS, chap_title) and 'Summary' not in chap_title:
                pass
            elif not sect_summ:
                pass
            else:
                section_summaries_new.append((chap_title.strip(), sect_summ))
        book_summ_new = book_summ._replace(section_summaries=section_summaries_new)
        book_summaries_new.append(book_summ_new)

    return book_summaries_new


def manual_fix_individual(book_summaries):
    start = False
    book_summaries_new = []
    for idx, book_summ in enumerate(book_summaries):
        sect_summs_old = book_summ.section_summaries
        sect_summs_new = []
        title = book_summ.title
        # if idx == 73:
        #     start = True
        if title in NON_NOVEL_TITLES:
            continue
        elif title == 'Homecoming':  # not the same as one in Gutenberg
            continue
        elif title in set(['A Christmas Carol']):
            sect_summs_new = [(x[0].split(':', 1)[0], x[1]) for x in sect_summs_old]
            # sect_summs_new[0] = ('Stave One', sect_summs_new[0][1])
        elif title in set(['Bleak House']):
            sect_summs_new = [(x[0].split(',', 1)[0], x[1]) for x in sect_summs_old]
        elif title in set(['David Copperfield']):
            sect_summs_new = [(x[0].split('.', 1)[0], x[1]) for x in sect_summs_old]
        elif title in set(['Moll Flanders']):
            sect_summs_new = [(x[0].split(' (', 1)[0], x[1]) for x in sect_summs_old]
        elif title in set(['The Idiot', "The Good Soldier", "Anna Karenina", 'The Return of the Native']):
            sect_summs_new = [(x[0].replace(',', ':'), x[1]) for x in sect_summs_old]
        elif title in set(['Crime and Punishment', 'Don Quixote', 'Madame Bovary']):  # multipart
            book_count = 0
            for i, (chap_title, sect_summ) in enumerate(sect_summs_old):
                if not chap_title.startswith("Chapter"):
                    continue
                chap_title, book_count = fix_multipart(chap_title, book_count)
                sect_summs_new.append((chap_title, sect_summ))
        elif title in set(['The Brothers Karamazov', 'Hard Times', 'The Mill on the Floss', 'My Ántonia',
                           'Northanger Abbey', 'A Tale of Two Cities', "The House of Mirth"]):  # multibook
            book_count = 0
            for i, (chap_title, sect_summ) in enumerate(sect_summs_old):
                if not chap_title.startswith("Chapter"):
                    continue
                chap_title, book_count = fix_multibook(chap_title, book_count)
                sect_summs_new.append((chap_title, sect_summ))
        elif title == 'Ethan Frome':
            for i, (chap_title, sect_summ) in enumerate(sect_summs_old):
                arr = chap_title.split(' ', 1)
                if len(arr) == 2:
                    chap_title = '{} {}'.format(arr[0], arr[1].upper())
                elif chap_title == 'Introduction':
                    chap_title = 'Prologue'
                elif chap_title == 'Conclusion':
                    chap_title = 'Epilogue'
                sect_summs_new.append((chap_title, sect_summ))
        elif title == 'O Pioneers!':
            sect_summs_new = [(x[0].replace(',', ':'), x[1]) for x in sect_summs_old if x[0].startswith('Part')]
        elif title == 'The Age of Innocence':
            sect_summs_new = [(x[0].replace('Book One ', '', 1).replace('Book Two ', ''), x[1]) for x in sect_summs_old]
        elif title == 'The Three Musketeers':
            offset = 0
            for i, (chap_title, sect_summ) in enumerate(sect_summs_old):
                if not chap_title.startswith(('Chapter', 'Part')):
                    continue
                if chap_title.startswith('Part II'):
                    offset = 37
                if offset:
                    chapter_range = re.search(('\d+-.+'), chap_title)
                    beg, end = chapter_range[0].split('-')
                    beg = int(beg) + offset
                    end = end if end == 'Epilogue' else int(end) + offset
                    chap_title = 'Chapter {}-{}'.format(beg, end)
                sect_summs_new.append((chap_title, sect_summ))
        elif title == 'Frankenstein':
            for sect_title, sect_summ in sect_summs_old:
                sect_title = sect_title.replace('Letters', 'Letter', 1)
                if sect_title.startswith("Walton"):
                    sect_title = "Final Letters"
                sect_summs_new.append((sect_title, sect_summ))
        elif title in set(['Kidnapped', 'The House of the Seven Gables', "Northanger Abbey", "The Scarlet Letter",
                           'Typee', "Anthem", "Ivanhoe", 'The Adventures of Huckleberry Finn',
                           'Maggie: A Girl of the Streets']):
            sect_summs_new = [x for x in sect_summs_old if x[0].startswith(('Chapter', 'Preface'))]
        elif title == 'Siddhartha':
            book_summ.section_summaries[0] = ("The Brahmin's Son", book_summ[0][1])
            book_summ_new = book_summ
        elif title == 'Heart of Darkness':
            part = 'Part 1'
            curr_summ = []
            for sect_title, sect_summ in sect_summs_old:
                if sect_title != part:
                    sect_summs_new.append((part, curr_summ))
                    part = sect_title
                    curr_summ = []
                curr_summ.extend(sect_summ)
            if curr_summ:
                sect_summs_new.append((part, curr_summ))
        elif title == 'Jane Eyre':
            sect_summs_new = [(x[0].replace('Summary', 'Chapter 26'), x[1]) for x in sect_summs_old]
        elif title == 'Moby-Dick':
            for sect_title, sect_summ in sect_summs_old:
                if sect_title in set(['Etymology', 'Extracts']):
                    continue
                sect_summs_new.append((sect_title, sect_summ))
        elif title == 'This Side of Paradise':
            sect_summs_new = [(x[0].split(':', 1)[0].replace(',', ':'), x[1]) for x in sect_summs_old if x[0].startswith('Book')]
        elif title == 'A Portrait of the Artist as a Young Man':
            curr_chap = 'Chapter 1'
            curr_summ = []
            for sect_title, sect_summ in sect_summs_old:
                chap_title = sect_title.split(',', 1)[0]
                if chap_title != curr_chap:
                    sect_summs_new.append((curr_chap, curr_summ))
                    curr_chap = chap_title
                    curr_summ = []
                curr_summ.extend(sect_summ)
            if curr_summ and curr_chap.startswith('Chapter'):
                sect_summs_new.append((curr_chap, curr_summ))
        elif title == "Dubliners":
            sect_summs_new = [(x[0].replace('“', '').replace('”', ''), x[1]) for x in sect_summs_old]
        elif title == "Jude the Obscure":
            sect_summs_new = [(x[0].split(':', 1)[0], x[1]) for x in sect_summs_old if x[0].startswith('Part')]
        elif title == "Lord Jim":
            sect_summs_new = [(x[0].replace('and', '-'), x[1]) for x in sect_summs_old]
        elif title == "Middlemarch":
            sect_summs_new = [(x[0].split(': ', 1)[1], x[1]) for x in sect_summs_old]
        elif title in set(["Sense and Sensibility", "Dracula", "Don Quixote"]):
            sect_summs_new = [(x[0], x[1]) for x in sect_summs_old if x[0].startswith('Chapter')]
        elif title == "This Side of Paradise":
            sect_summs_new = [(x[0].split(':', 1)[0].replace(',', ''), x[1]) for x in sect_summs_old if x[0].startswith('Chapter')]
            # start = True
        elif title == 'The Time Machine':
            sect_summs_new = [(x[0].replace('and', '-'), x[1]) for x in sect_summs_old]
            sect_summs_new[-1] = ('Chapter 11 - Epilogue', sect_summs_new[-1][1])
        elif title == 'Ulysses':
            sect_summs_new = [(x[0].replace('Episode', 'Chapter').split(':', 1)[0], x[1]) for x in sect_summs_old]
        elif title == 'Walden':
            sect_summs_new = [('Chapter {}'.format(i), x[1]) for i, x in enumerate(sect_summs_old, 1)]
        elif title == 'Winesburg, Ohio':
            for sect_title, sect_summ in sect_summs_old:
                sect_title = sect_title.replace('"', '')
                if sect_title == "Godliness, Parts I-II":
                    sect_title = "Godliness Part I, Godliness Part II"
                elif sect_title.startswith("Godliness, Parts III"):
                    sect_title = "Godliness Part III, Godliness Part IV, A Man of Ideas"
                elif sect_title.startswith("Analytical"):
                    continue
                sect_summs_new.append((sect_title, sect_summ))
        elif title == "White Fang":
            sect_summs_new = [(x[0].replace(',', ':').replace('and', '-', 1), x[1]) for x in sect_summs_old]
        elif title == 'The Picture of Dorian Gray':
            sect_summs_new = sect_summs_old
            sect_summs_new[0] = ('Preface', sect_summs_new[0][1])
        elif title == "War and Peace":
            ssn = [(standardize_sect_title(x[0].replace(',', ':'), False), x[1]) for x in sect_summs_old]
            book_summ_new = book_summ._replace(section_summaries=ssn)
        else:
            sect_summs_new = sect_summs_old

        if sect_summs_new:
            sect_summs_new = [(standardize_sect_title(x[0]), x[1]) for x in sect_summs_new]
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
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    if args.full:
        title_set = None
    else:
        print('limiting to books from', CATALOG_NAME)
        title_set = set(catalog.keys())
    # if args.archived:
    #     guides_page = get_archived(GUIDES_PAGE)
    #     base_url = 'https://web.archive.org'
    # else:
    guides_page = GUIDES_PAGE
    base_url = BASE_URL
    book_summaries = get_summaries(guides_page, base_url, args.out_name, args.use_pickled,
                                   args.archived, args.update_old, args.save_every,
                                   title_set=title_set, sleep=args.sleep_time)
    # with open(args.out_name, 'rb') as f:
    #     book_summaries = pickle.load(f)

    book_summaries_overlap = gen_gutenberg_overlap(book_summaries, catalog, filter_plays=True)
    book_summaries_overlap = manual_fix(book_summaries_overlap)
    book_summaries_overlap = manual_fix_individual(book_summaries_overlap)

    with open(args.out_name_overlap, 'wb') as f:
        pickle.dump(book_summaries_overlap, f)
    print('wrote to {}'.format(args.out_name_overlap))
