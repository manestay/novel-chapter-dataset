"""
bookwolf_scrape.py

Scrapes bookwolf.com for summaries. Outputs to pickled list of BookSummary objects.

Optional flags to 1) use the archived version of pages, 2) scrape all books, instead of only those in Gutenberg catalog.

WARNING: --full flag has not been tested fully, pages will fail to be scraped due to formatting
"""

import argparse
import os
import re
import time
import urllib.parse

import dill as pickle

from archive_lib import get_archived
from scrape_lib import get_soup, get_clean_text, load_catalog, find_all_stripped, gen_gutenberg_overlap, \
                       standardize_title, load_catalog, write_sect_links, \
                       BookSummary, CATALOG_NAME, RE_CHAPTER_NOSPACE


BOOKS_LIST = 'http://www.bookwolf.com/Welcome_to_Bookwolf1/welcome_to_bookwolf1.html'

OUT_NAME_ALL = 'pks/summaries_bookwolf_all.pk'
OUT_NAME_OVERLAP = 'pks/summaries_bookwolf.pk'

RE_D = re.compile(r'\d')
RE_SUMM = re.compile(r'^S?ummary.*')
RE_CONTEXT = re.compile(r'^Context.*')
RE_INTER = re.compile(r'.*Interpretation.*')
RE_LEAR = re.compile(r'^\(It is Britain and this scene')

parser = argparse.ArgumentParser(description='scrape bookwolf')
parser.add_argument('out_name', nargs='?', default=OUT_NAME_ALL, help='name of pickle file for all summaries')
parser.add_argument('out_name_overlap', nargs='?', default=OUT_NAME_OVERLAP,
                    help='name of pickle file for overlapping summaries')
parser.add_argument('--archived', action='store_true', help='always use archived versions of scripts')
parser.add_argument('--use-pickled', action='store_true', help='use existing (partial) pickle')
parser.add_argument('--full', action='store_true', help='get all books, not just those in Gutenberg')
parser.add_argument('--catalog', default=CATALOG_NAME, help='get all books, not just those in Gutenberg')
parser.add_argument('--save-every', default=2, type=int, help='interval to save pickled file')
parser.add_argument('--sleep', default=0, type=int, help='sleep time between scraping each book')
parser.add_argument('--no-text', dest='get_text', action='store_false', help='do not get book text')


def num_in(string): return RE_D.search(string)


def get_title_url_map(books_list, title_set=None):
    soup = get_soup(books_list)
    columns = soup.find_all('table', width=None)[1].find_all('table')

    title_url_map = {}
    for column in columns:
        cells = column.find_all('tr')
        for cell in cells:
            p = cell.find('p')
            entries = p.find_all('a')
            for entry in entries:
                title = get_clean_text(entry)
                if title_set and title not in title_set:
                    continue
                href = entry.get('href')
                title_url_map[title] = urllib.parse.urljoin(books_list, href)
    return title_url_map


def process_chapter(link):
    soup = get_soup(link)
    summ_lines = find_all_stripped('p', soup, RE_SUMM) or find_all_stripped('b', soup, RE_CONTEXT)
    # manual fixes
    if link == 'http://www.bookwolf.com/Free_Booknotes/King_Lear_free_booknotes/Act_1_Scene_1_-_King_Lear/act_1_scene_1_-_king_lear.html':
        summ_lines = find_all_stripped('p', soup, RE_LEAR)
    elif link == 'http://www.bookwolf.com/Free_Booknotes/Othello/Act_3_Scene_2_-_Othello_Bookno/act_3_scene_2_-_othello_bookno.html':
        summ_lines = find_all_stripped('p', soup, 'ACT III – Scene.ii')
    if len(summ_lines) > 1:
        print('error, more than 1 summ line: ', link)
        return
    elif not summ_lines:
        print('no summ lines found: ', link)
        return
    ps = summ_lines[0].find_all_next('p')
    paragraphs = process_paragraphs(ps)
    return paragraphs


def process_paragraphs(ps):
    paragraphs = []
    for p in ps:
        if not p:
            continue
        para = get_clean_text(p)
        if para == 'Interpretation':
            break
        if not para:
            continue
#         if p.find('i') and p.find('i').get_text(strip=True):
#             continue
        if p.find('b') and p.find('b').get_text(strip=True):
            break  # reached another section's paragraphs
        paragraphs.append(para)
    return paragraphs


def standardize_section_titles(text):
    text = text.replace(' - Summary', '').replace('6 -7', '6-7')
    if 'Book' and 'Chapter' in text:
        text = text.replace(' C', ': C')
    text = text.replace(' & ', '-').replace(' - ', '-')
    return text


def get_summaries(title_url_map, out_name, use_pickled=False, get_text=True,
                  save_every=5, sleep=0):
    if use_pickled and os.path.exists(out_name):
        with open(out_name, 'rb') as f1:
            book_summaries = pickle.load(f1)
        print('loaded {} existing summaries, resuming'.format(len(book_summaries)))
        done = set([x.title for x in book_summaries])
    else:
        book_summaries = []
        done = set()

    for title, url in title_url_map.items():  # iterate through books
        if title in done:
            continue
        if sleep:
            time.sleep(sleep)

        print('processing', title, url)
        author = ''  # TODO: figure this out
        soup = get_soup(url)
        contents = soup.find('table', id='Table56')
        if contents:
            idx = 3
        else:
            contents = soup.find('table', width='99%')
            idx = 4
        if not contents:
            print('table of contents not found on ', url)
            continue

        cells = contents.find('tbody').find_all('tr', recursive=False)[idx].find_all('a')
        cells = [x for x in cells if num_in(get_clean_text(x))]
        if not cells:
            print('no chapters found for ', url)
            continue

        sects = []
        for c in cells:  # iterate through sections
            text = get_clean_text(c)
            if 'Interpretation' in text:
                continue
            href = c['href']
            link_summ = urllib.parse.urljoin(url, href)

            if get_text:
                paras = process_chapter(link_summ)
                if not paras:
                    print('no summaries found on ', link_summ)
                    continue
            else:
                paras = []
            text = standardize_section_titles(text)
            sects.append((text, paras, link_summ))

        book_summ = BookSummary(
            title=title,
            author=author,
            genre=None,
            plot_overview=None,
            source='bookwolf',
            section_summaries=sects,
            summary_url=url)
        book_summaries.append(book_summ)
        num_books = len(book_summaries)
        if num_books > 1 and num_books % save_every == 0:
            with open(out_name, 'wb') as f:
                pickle.dump(book_summaries, f)
            print("Done scraping {} books".format(num_books))

    print('Scraped {} books from bookwolf'.format(len(book_summaries)))
    with open(out_name, 'wb') as f:
        pickle.dump(book_summaries, f)
    print('wrote to', out_name)
    return book_summaries


def manual_fix(book_summaries):
    book_summaries_new = []
    for book_summ in book_summaries:
        title = book_summ.title
        title_new = standardize_title(title)
        if title_new != title:
            print('renamed {} -> {}'.format(title, title_new))
        section_summaries_new = []
        section_summaries_old = book_summ.section_summaries
        for i, curr_summ in enumerate(section_summaries_old):
            chap_title, sect_summ, url = curr_summ
            chap_title = chap_title.replace('Chapters', 'Chapter').replace('Letters', 'Letter ')
            if re.match(r'Chap \d+', chap_title):
                chap_title = chap_title.replace('Chap', 'Chapter')
            if re.search(RE_CHAPTER_NOSPACE, chap_title):
                chap_title = re.sub('Chapter', 'Chapter ', chap_title)
            section_summaries_new.append((chap_title.strip(), sect_summ, url))
        book_summ_new = book_summ._replace(section_summaries=section_summaries_new, title=title_new)
        book_summaries_new.append(book_summ_new)
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
    else:
        books_list = BOOKS_LIST
    title_url_map = get_title_url_map(books_list, title_set)
    print('{} book pages total'.format(len(title_url_map)))

    book_summaries = get_summaries(title_url_map, args.out_name, args.use_pickled,
                                   args.get_text, args.save_every, args.sleep)

    book_summaries_overlap = gen_gutenberg_overlap(book_summaries, catalog, filter_plays=True)
    book_summaries_overlap = manual_fix(book_summaries_overlap)

    with open(args.out_name_overlap, 'wb') as f:
        pickle.dump(book_summaries_overlap, f)
    print('wrote summaries to {}'.format(args.out_name_overlap))

    out_name = 'urls/chapter-level/bookwolf.tsv'
    write_sect_links(out_name, book_summaries_overlap)
    print(f'wrote urls to {out_name}')
