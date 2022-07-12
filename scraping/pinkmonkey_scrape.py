"""
pinkmonkey_scrape.py

Scrapes pinkmonkey.com and barronsbooksnotes.com for summaries. Outputs to pickled list of BookSummary objects.

Optional flags to 1) use the archived version of pages, 2) scrape all books, instead of only those in Gutenberg catalog.

"""

import argparse
import os
import re
import sys
import time
import urllib.parse

import dill as pickle
from bs4 import element

from archive_lib import get_archived, get_orig_url
from scrape_lib import get_soup, get_clean_text, get_absolute_links, find_all_stripped, load_catalog, BookSummary, \
                       gen_gutenberg_overlap, standardize_title, standardize_sect_title, fix_multibook, fix_multipart
from scrape_vars import CATALOG_NAME, NON_NOVEL_TITLES

tups = [
    ('monkeynotes', 'https://pinkmonkey.com', 'https://pinkmonkey.com/booknotes/notes1.asp'),
    ('barrons', 'http://barronsbooknotes.com/', 'http://barronsbooknotes.com/'),
]
OUT_NAME_ALL = 'pks/summaries_pinkmonkey_all.pk'
OUT_NAME_OVERLAP = 'pks/summaries_pinkmonkey.pk'
BAD_STARTS = set(['NOTE:', '<script', '<!--', 'Table of Contents', '©', 'Your browser'])

# TODO: merge into scraping/scrape_vars.py
RE_CHAP = re.compile(r'^(Chapter|Act|Canto|Book|Part|Section|Story|Scene|Epilogue|Prologue|Letter|Preface).*', re.IGNORECASE)
RE_OPEN = re.compile(r'^Opening\s?$')
RE_NEXT = re.compile(r'^Next.*')
RE_STORY = re.compile(r'^THE (STORY|NARRATIVE)')
RE_SUMM = re.compile(r'^Summary$', re.IGNORECASE)
RE_SUMM_2 = re.compile(r'^(Story |Chapter )?Summary', re.IGNORECASE)
RE_SUMM_3 = re.compile(r'^.*?Summary', re.IGNORECASE)
RE_SUMM_CONTINUED = re.compile(r'^Summary \(continued\)$', re.IGNORECASE)
RE_NUMDOT = re.compile(r'^((\d|[MDCLXVI])+\.)')
RE_CHAPTER_ONLY = re.compile(r'Chapters?', re.IGNORECASE)

parser = argparse.ArgumentParser(description='scrape pinkmoney')
parser.add_argument('out_name', nargs='?', default=OUT_NAME_ALL, help='name of pickle file for all summaries')
parser.add_argument('out_name_overlap', nargs='?', default=OUT_NAME_OVERLAP,
                    help='name of pickle file for overlapping summaries')
parser.add_argument('--archived', action='store_true', help='always use archived versions of scripts')
parser.add_argument('--use-pickled', action='store_true', help='use existing (partial) pickle')
parser.add_argument('--full', action='store_true', help='get all books, not just those in Gutenberg')
parser.add_argument('--catalog', default=CATALOG_NAME, help='get all books, not just those in Gutenberg')
parser.add_argument('--update-old', action='store_true', help='update out-of-date archived version')
parser.add_argument('--save-every', default=2, type=int, help='interval to save pickled file')
parser.add_argument('--sleep', default=0, type=int, help='sleep time between scraping each book')


def get_pages_titles(index_pages, books_list, title_set=None):
    book_pages = []
    titles = []
    for page_link in sorted(index_pages):  # get book pages
        soup_page = get_soup(page_link)
        book_links = soup_page.find_all('p')  # 1 p element has 1 or more book listings
        for b in book_links:
            for elem in b.find_all('a'):
                href = elem.get('href')
                basename = href.rsplit('/', 1)[-1]
                if href.endswith('.asp') and 'notes' not in basename and 'first.asp' != basename:
                    title = get_clean_text(elem)
                    title = title.replace('Downloadable/Printable Version', '')
                    title = title.replace('&nbsp', '')
                    if not title or title == 'Quotes' or title == 'Quotations' or title.startswith('Read the'):
                        continue
                    if title_set and title not in title_set:
                        continue
                    book_pages.append(href)
                    titles.append(title)
    book_pages = get_absolute_links(book_pages, books_list)
    return book_pages, titles


def get_index_pages(books_list, source):
    soup = get_soup(books_list)
    if source == 'monkeynotes':
        tables = soup.find_all('font', color='#339900', face='Arial, Helvetica')
    elif source == 'barrons':
        tables = soup.find_all('font', color='white', face='Verdana, Arial, Helvetica, sans-serif')

    index_pages = []
    for table in tables:  # get index pages for each letter
        entries = table.find_all('a')
        for entry in entries:
            href = entry.get('href')
            index_pages.append(href)
    index_pages = set(urllib.parse.urljoin(books_list, x) for x in index_pages)
    return index_pages


def is_paywall(link):
    soup = get_soup(link)
    for p in soup.find_all('p'):
        p_text = get_clean_text(p)
        if p_text.startswith('NOTICE: Unfortunately'):
            return True
    return False


def process_story(link, title=None, get_next=True, find_continued=False):
    """
    returns tuples of (title, summary list) format
    """
    soup = get_soup(link)
    chapters = []
    if find_continued:
        lines = find_all_stripped(['p', 'h4'], soup, RE_SUMM_CONTINUED)
        if not lines:
            return []
    ### specific edge cases
    elif 'WhiteFang' in link:
        lines = find_all_stripped(['p', 'h4'], soup, RE_CHAP) + find_all_stripped(['p', 'h4'], soup, RE_SUMM)
    elif 'Ulysses' in link:
        lines = find_all_stripped('p', soup, RE_SUMM_3)
    elif 'pmKidnapped16' in link:
        find_all_stripped(['p', 'h4'], soup, RE_SUMM)[0].extract()
        lines = find_all_stripped(['p', 'h4'], soup, RE_CHAP)
    ###
    else:
        lines = find_all_stripped(['p', 'h4'], soup, RE_SUMM) or find_all_stripped(['p', 'h4'], soup, RE_SUMM_2) or \
                find_all_stripped(['p', 'h4'], soup, RE_CHAP)
    lines = [x for x in lines if (x.find('b') and x.find('b').get_text(strip=True))
             or x.name == 'h4']  # line should be bold
    if not lines or 'barrons/house' in link:
        lines.extend(find_all_stripped(['p', 'h4'], soup, RE_NUMDOT))
    if not lines:
        print('    cannot find section titles on', link)
        return []
    if 'pmFrankenstein10' in link:
        lines = lines[1:]
    frank_cond = 'pmFrankenstein' in link and not any(
        get_clean_text(lines[0]).startswith(x) for x in ('Summary', 'LETTER'))
    if 'barrons/heartdk' in link or frank_cond:
        lines = [lines[0].find_next('p')]
    for line in lines:
        if len(lines) > 1 or not title:
            title_ = line if not re.match(RE_SUMM, get_clean_text(line)) else line.find_previous('p')
            title_ = get_clean_text(title_)
        else:
            title_ = title
        if 'pmIdiot' in link or 'pmSecretSharer' in link:
            ps = line.find_all_next(['p', 'b'])
        elif 'wutherg' in link or 'Ulysses' in link:
            ps = []
            indiv_strs = []
            for sib in line.next_siblings:
                if sib.name == 'p':
                    if indiv_strs:
                        p = element.Tag(name='p')
                        p.string = ' '.join(indiv_strs)
                        ps.append(p)
                        indiv_strs = []
                    ps.append(sib)
                elif isinstance(sib, element.NavigableString) and \
                    not (sib.endswith("Barron's Booknotes\n") or sib.startswith("MonkeyNotes")):
                    indiv_strs.append(sib)
            if indiv_strs:
                p = element.Tag(name='p')
                p.string = ' '.join(indiv_strs)
                ps.append(p)
        else:
            ps = line.find_all_next(['p', 'h4'])
        paragraphs = process_paragraphs(ps)
        chapters.append((title_, paragraphs))
    if 'junglex' in link: # this should be moved to manual_fix_individual()
        assert chapters[3][0] == 'CHAPTER 17'
        assert chapters[7][0] == 'CHAPTER 18'
        clean_scene = lambda x: re.sub('SCENE \d', '', x, 1)
        chapter17 = [*chapters[3][1], clean_scene(chapters[4][0]), *chapters[4][1],
                     clean_scene(chapters[5][0]), *chapters[5][1], clean_scene(chapters[6][0])]
        del chapters[6]; del chapters[5]; del chapters[4]
        chapters[3] = (chapters[3][0], chapter17)
    if get_next and chapters:  # check next page if is continued
        next_elem = soup.find('a', text=RE_NEXT)
        if not next_elem:
            pass
        else:
            next_link = urllib.parse.urljoin(link, next_elem['href'])
            chapters2 = process_story(next_link, get_next=get_next, find_continued=True)
            if not chapters2:
                pass
            elif len(chapters2) == 1:
                title1, paragraphs1 = chapters.pop(-1)
                title2, paragraphs2 = chapters2[0]
                chapters.append((title1, paragraphs1 + paragraphs2))
    return chapters


def process_paragraphs(ps):
    paragraphs = []
    for p in ps:
        if not p:
            continue
        para = get_clean_text(p, strip=False).strip()
        if para == 'Notes':
            break
        if not para or any([para.startswith(x) for x in BAD_STARTS]) or p.name == 'b':
            continue
        a = p.find('a')
        if a and a.get('href'):
            continue
        if p.find('i'):
            i_text = p.find('i').get_text(strip=True)
            if len(i_text) >= .9 * len(para):
                continue

        b_text = None
        b = p.find('b')
        if b:
            b_text = b.get_text(strip=True)
            if b_text == ', ':
                b_text = None
            elif b_text == 'Om':  # fix for http://www.pinkmonkey.com/booknotes/monkeynotes/pmSiddhartha20.asp
                para = para.replace('Om', ' Om')
                b_text = None
            else:
                b_text = b_text
        if p.name == 'h4' or b_text:
            break  # reached another section's paragraphs
        para = para.replace('', "'")  # replace weird apostrophe
        paragraphs.append(para)
    return paragraphs

# for monkeynotes
def process_next_link(link, archived, update_old):
    soup = get_soup(link)

    chapters = find_all_stripped('a', soup, RE_CHAP)
    if 'pmEthanFrome' in link:
        chapters += soup.find_all('a', text=RE_OPEN)
    elif 'pmDubliners' in link:
        h3s = soup.find_all('h3')
        for h3 in h3s:
            if h3.text.startswith('Short Story'):
                chapters = h3.find_next_sibling('p').find_all('a')
    elif 'wutherg' in link:
        if chapters[-3]['href'] != 'wutherg47.asp':
            chapters[-3]['href'] = 'wutherg47.asp'
    elif 'pmJungle' in link:
        if chapters[3]['href'] != 'pmJungle20.asp':
            chapters[3]['href'] = 'pmJungle20.asp'
        if chapters[9]['href'] != 'pmJungle31.asp':
            chapters[9]['href'] = 'pmJungle31.asp'
    if not chapters:
        return None
    section_summs = []
    url_title_map = {}
    seen_urls = set()
    for c in chapters:
        href = c.get('href')
        title = get_clean_text(c)
        title = title if 'pmBabbitt' not in link else ''
        url = urllib.parse.urljoin(link, href)
        orig_url = url
        if 'dpbolvw' in url:
            continue
        dead_links1 = set(['pmVanity'])
        dead_links2 = set(['pmPrincePauper', 'pmIdiot', 'pmFatherSon', 'pmGreenwood', 'pmOfHuman'])
        dead_links3 = set(['pmDeerSlayer', 'pmTypee'])
        is_dead1 = any(x in orig_url for x in dead_links1)
        is_dead2 = any(x in orig_url for x in dead_links2)
        is_dead3 = any(x in orig_url for x in dead_links3)
        if is_dead1 or is_dead2 or is_dead3:
            # http://www.pinkmonkey.com:80/booknotes/monkeynotes/pmIdiot16.asp and up pages are dead
            # likewise for other strings
            page_no = int(re.findall('\d+', orig_url)[-1])
            if is_dead1 and page_no >= 17:
                continue
            elif is_dead2 and page_no >= 16:
                continue
            elif is_dead3 and page_no >= 13:
                continue
        if orig_url in seen_urls:
            continue
        if archived:
            orig_url = urllib.parse.urljoin(get_orig_url(link), c.get('href'))
            url = get_archived(orig_url, update_old)
        url_title_map[url] = title
        seen_urls.add(orig_url)

    for url, title in url_title_map.items():
        summs = process_story(url, title)
        for summ in summs:
            # print(' ', summ[0])
            if summ[1]:  # not empty text
                section_summs.append(summ)

    # manual fixes
    extra_sections = []
    if 'pmWinesburg' in link:
        extra_sections = ["pmWinesburg20.asp", "pmWinesburg21.asp", "pmWinesburg22.asp"]
    elif 'pmDubliners' in link:
        extra_sections = ["pmDubliners12.asp", "pmDubliners16.asp"]  # pmDubliners57.asp has no "Summary" heading, so skip
    if extra_sections:
        if archived:
            links_addtl = [get_archived(urllib.parse.urljoin(get_orig_url(link), href), update_old)
                           for href in extra_sections]
        else:
            links_addtl = [urllib.parse.urljoin(link, x) for x in extra_sections]
        sect_summs_addtl = [process_story(x)  for x in links_addtl]
        sect_summs_addtl = [x[0] for x in sect_summs_addtl]
        section_summs.extend(sect_summs_addtl)
    return section_summs


def process_story_link(link, archived, update_old):
    soup = get_soup(link)
    stories = soup.find_all('a', text=RE_STORY)
    if not stories:
        return None
    section_summs = []
    for story in stories:  # a story page has multiple chapters
        href = story.get('href')
        ## For page http://www.pinkmonkey.com/booknotes/barrons/billbud.asp , we want Typee, but not Billy Budd
        if not href or href.startswith('billbud'):
            continue
        if archived:
            url = urllib.parse.urljoin(get_orig_url(link), href)
            url = get_archived(url, update_old)
        else:
            url = urllib.parse.urljoin(link, href)
        summs = process_story(url)
        if summs:
            section_summs.extend(summs)
    return section_summs


def get_summaries(page_title_map, out_name, use_pickled=False, archived=False, update_old=False,
                  save_every=5, sleep=0):
    if use_pickled and os.path.exists(out_name):
        with open(out_name, 'rb') as f1:
            book_summaries = pickle.load(f1)
        print('loaded {} existing summaries, resuming'.format(len(book_summaries)))
        done = set([(x.title, x.source) for x in book_summaries])
    else:
        book_summaries = []
        done = set()

    for page, title in page_title_map.items():
        if 'barrons' in page.lower():
            source = 'barrons'
        elif 'monkeynotes' in page.lower():
            source = 'monkeynotes'
        if (title, source) in done:
            continue
        if sleep:
            time.sleep(sleep)
        if archived:
            page = get_archived(page, update_old)
        print('processing', title, page)
        author = ''  # TODO: figure this out

        soup_book = get_soup(page)

        next_link = soup_book.find('a', text=RE_NEXT)
        story_link = soup_book.find('a', text=RE_STORY)
        is_hard_times = 'pinkmonkey.com/booknotes/barrons/hardtms.asp' in page

        if not (next_link or story_link or is_hard_times):
            print('cannot find any summaries for ', page)
            continue
        if is_paywall(page):
            print('    page is under a paywall, will be more errors: ', page)
            # continue

        if next_link:  # monkeynotes
            href = next_link.get('href')
            url = urllib.parse.urljoin(get_orig_url(page), href)
            url = get_archived(url, update_old)
            sect_summs = process_next_link(url, archived, update_old)
        elif story_link:  # barrons (most)
            url = page
            sect_summs = process_story_link(url, archived, update_old)
        elif is_hard_times:
            url = page
            sect_summs = process_next_link(url, archived, update_old)
        else:
            print('error')
            sys.exit()

        if not sect_summs:
            print('    Cannot process {}'.format(url))
            # NOTE: expected to reach here for barrons Oliver Twist and barrons The Secret Sharer
            continue

        book_summ = BookSummary(title=title, author=author, genre=None, plot_overview=None, source=source,
                                section_summaries=sect_summs, summary_url=page)
        book_summaries.append(book_summ)
        num_books = len(book_summaries)
        if num_books > 1 and num_books % save_every == 0:
            with open(out_name, 'wb') as f:
                pickle.dump(book_summaries, f)
            print("Done scraping {} books".format(num_books))

    print('Scraped {} books from pinkmonkey'.format(len(book_summaries)))
    with open(out_name, 'wb') as f:
        pickle.dump(book_summaries, f)
    print('wrote to', out_name)
    return book_summaries


def manual_fix_individual(book_summaries):
    start = False  # to debug
    book_summaries_new = []
    seen = set()
    for idx, book_summ in enumerate(book_summaries):
        sect_summs_new = []
        sect_summs_old = book_summ.section_summaries
        title = book_summ.title
        source = book_summ.source
        if (title, source) in seen:
            continue
        # if idx == 0:
        #     start = True
        if title in NON_NOVEL_TITLES:
            continue
        if title in set(['Kidnapped', 'Treasure Island', 'The Call of the Wild',
                         'Dr. Jekyll and Mr. Hyde', 'The House of the Seven Gables', 'The Prince and the Pauper',
                         'Huckleberry Finn', 'Tom Sawyer']) and source == 'monkeynotes' or \
                title == "The Mayor of Casterbridge" and source == 'barrons':
            sect_summs_new = [(x[0].split(':', 1)[0].strip(), x[1]) for x in sect_summs_old]
        elif title in set(["Oliver Twist", 'Candide', "Alice's Adventures in Wonderland"]) and source == 'monkeynotes' or \
                title == 'The Scarlet Letter' and source == 'barrons':
            sect_summs_new = [(x[0].split('-', 1)[0].strip(), x[1]) for x in sect_summs_old]
        elif title in set(["Uncle Tom's Cabin"]) and source == 'barrons':
            sect_summs_new = [(x[0].split('.', 1)[0], x[1]) for x in sect_summs_old]
        elif title in set(["Emma", "Pride and Prejudice"]) and source == 'monkeynotes' or \
                title in set(["Huckleberry Finn", "Great Expectations"]) and source == 'barrons':
            sect_summs_new = [(x[0].replace('&', '-', 1).strip(), x[1]) for x in sect_summs_old]
        # skip below, as inconsistent sections vs Gutenberg book
        elif title in set(['War and Peace', 'The Time Machine']) and source == 'monkeynotes':
            continue
        elif title in set(['Anna Karenina', 'Don Quixote', "Crime and Punishment", 'Madame Bovary', 'White Fang',
                           'Jude the Obscure', "Gulliver's Travels", "The Idiot", 'Under the Greenwood Tree']):  # multipart
            book_count = 0
            if title == 'Madame Bovary' and source == 'barrons':
                assert sect_summs_old[26][0] == 'Chapter 4'
                assert sect_summs_old[31][0] == 'Chapter 10'
                sect_summs_old[26] = ('Chapter 3-4', sect_summs_old[26][1])
                sect_summs_old[31] = ('Chapter 9-10', sect_summs_old[31][1])
            if title == 'The Idiot':
                sect_summs_old[1] = ('Chapter 2-3', sect_summs_old[1][1])
            for i, (chap_title, sect_summ) in enumerate(sect_summs_old):
                if title == 'Crime and Punishment':
                    chap_title = chap_title.replace('PART VI, ', '', 1)
                    if chap_title.startswith('Part'):
                        chap_title = 'Chapter {}'.format(chap_title.split(' ', 1)[-1])
                chap_title = re.sub(RE_CHAPTER_ONLY, 'Chapter', chap_title)
                if not chap_title.startswith("Chapter"):
                    continue
                chap_title, book_count = fix_multipart(chap_title, book_count)
                sect_summs_new.append((chap_title, sect_summ))
        elif title in set(['My Antonia', "A Tale of Two Cities", "The War of the Worlds", 'The House of Mirth',
                           'Hard Times']):  # multibook
            book_count = 0
            for i, (chap_title, sect_summ) in enumerate(sect_summs_old):
                if chap_title.endswith('CHAPTER I'):  # for barrons
                    chap_title = 'CHAPTER I'
                chap_title = re.sub(RE_CHAPTER_ONLY, 'Chapter', chap_title)
                if not chap_title.startswith("Chapter"):
                    continue
                if title == 'A Tale of Two Cities':
                    chap_title = chap_title.split(':')[0]
                chap_title, book_count = fix_multibook(chap_title, book_count)
                sect_summs_new.append((chap_title, sect_summ))
        elif title in set(['The House of the Seven Gables', 'Walden']) and source == 'barrons':
            sect_summs_new = [('Chapter {}'.format(x[0].split('.', 1)[0]) if not x[0].startswith('P') else x[0], x[1]) \
                              for x in sect_summs_old]
        elif title == 'Heart of Darkness':
            sect_summs_new = [(x[0].replace('Chapter', 'Part'), x[1]) for x in sect_summs_old]
        elif title == 'The Hound of the Baskervilles' and source == 'monkeynotes':
            assert book_summ.section_summaries[1][0] == 'Chapter Summary'
            book_summ.section_summaries[1] = ('Chapter 2', book_summ.section_summaries[2][1])
            book_summ_new = book_summ
        elif title == 'Tess of the D\'Urbervilles' and source == 'barrons':
            sect_summs_new = [(x[0].replace('AND', '-')
                               .replace(', 14, - ', ' - ').replace(', 27, - ', ' - ').replace(', 57, - ', ' - '),
                               x[1]) for x in sect_summs_old]
        elif title == 'The Prince':
            sect_summs_new = [(x[0].replace('AND', '-'), x[1]) for x in book_summ.section_summaries]
        elif title == 'Ivanhoe':
            sect_summs_old.pop(0)
            chapters = ['Chapter 1', 'Chapter 2', 'Chapter 3', 'Chapter 4', 'Chapter 5', 'Chapter 6', 'Chapter 7-9',
                        'Chapter 10', 'Chapter 11', 'Chapter 12', 'Chapter 13-15', 'Chapter 16-17', 'Chapter 18-19',
                        'Chapter 20-21', 'Chapter 22', 'Chapter 23', 'Chapter 24', 'Chapter 25-27', 'Chapter 28',
                        'Chapter 29', 'Chapter 30-31', 'Chapter 32', 'Chapter 33-34', 'Chapter 35', 'Chapter 37-39',
                        'Chapter 40-42', 'Chapter 43', 'Chapter 44']
            sect_summs_new = [(chap, summ) for chap, summ in zip(chapters, [x[1] for x in sect_summs_old])]
        elif title == 'Winesburg, Ohio':
            for sect_title, sect_summ in sect_summs_old:
                if sect_title == 'Story 13 -':
                    sect_title = 'The Strength of God'
                elif sect_title == 'PART I - SUMMARY':
                    sect_title = 'Godliness Part I'
                elif sect_title == 'PART II - SUMMARY':
                    sect_title = 'Godliness Part II'
                elif sect_title == 'PART III - Surrender':
                    sect_title = 'Godliness Part III'
                elif sect_title == 'PART IV - Terror':
                    sect_title = 'Godliness Part IV'
                else:
                    sect_title = sect_title.split('-', 1)[-1].strip()
                sect_summs_new.append((sect_title, sect_summ))
        elif (title == 'Silas Marner' and source == 'barrons') or \
             (title == 'Looking Backward: 2000-1887' and source == 'monkeynotes'):
            sect_summs_new = [x for x in sect_summs_old if x[0].startswith('C')]
        elif title == 'Turn of the Screw':
            sect_summs_new = [(x[0].replace('SECTION', 'Chapter'), x[1]) for x in sect_summs_old]
            sect_summs_new = sect_summs_new[4:]
            assert sect_summs_new[0][0] == 'PROLOGUE'
        elif title == 'The Metamorphosis' and source == 'monkeynotes':
            sect_summs_new = [(x[0].replace('Section', 'Part'), x[1]) for x in sect_summs_old]
        elif title == 'Sons and Lovers' and source == 'barrons':
            for sect_title, sect_summ in sect_summs_old:
                sect_title = sect_title.replace('PART TWO - ', '', 1)
                if not sect_title.startswith('CHAPTER'):
                    continue
                sect_summs_new.append((sect_title, sect_summ))
        elif title == 'Moby Dick' and source == 'monkeynotes':
            sect_summs_new = [x for x in sect_summs_old if not x[0] == 'Notes']
        elif title == 'Moby Dick' and source == 'barrons':
            chap_nums_re = r'\d+'
            for sect_title, sect_summ in sect_summs_old:
                chaps = re.findall(chap_nums_re, sect_title)
                if sect_title == 'Epilogue':
                    pass
                elif len(chaps) == 1:
                    sect_title = 'Chapter {}'.format(chaps[0])
                else:
                    sect_title = 'Chapter {}-{}'.format(chaps[0], chaps[-1])
                sect_summs_new.append((sect_title, sect_summ))
        elif title == 'Siddhartha' and source == 'monkeynotes':
            for sect_title, sect_summ in sect_summs_old:
                sect_title = sect_title.split(':', 1)[1].strip()
                sect_summs_new.append((sect_title, sect_summ))
        elif title == 'Siddhartha' and source == 'barrons':
            assert len(sect_summs_old) == 1
            continue
        elif title == "Walden":
            sect_summs_new = [(x[0].replace('Chapter1', 'Chapter 1', 1), x[1]) for x in sect_summs_old]
        elif title == "Ethan Frome" and source == 'monkeynotes':
            for sect_title, sect_summ in sect_summs_old:
                if sect_title == 'Opening':
                    sect_title = 'Prologue'
                elif sect_title.startswith('Chapter 10'):
                    sect_title = 'Epilogue'
                sect_summs_new.append((sect_title, sect_summ))
        elif title == 'Typee' and source == 'monkeynotes':
            sect_summs_new = [(x[0].replace('Chapter 1Summary', 'Chapter 1', 1), x[1]) for x in sect_summs_old]
        elif title == 'Typee' and source == 'barrons':
            sect_summs_new = [(x[0].replace('PREFACE AND CHAPTERS 1 TO 5', 'Preface to Chapter 5'),
                               x[1]) for x in sect_summs_old]
        elif title == "A Connecticut Yankee in King Arthur's Court":
            sect_summs_new = [(x[0].split('"', 1)[0].split(':', 1)[0].strip(),
                               x[1]) for x in sect_summs_old if x[0].startswith('CHAPTER')]
        elif title == 'The Count of Monte Cristo' and source == 'monkeynotes':
            sect_summs_new = [(x[0].split(':', 1)[0].split('-', 1)[0].strip(), x[1]) for x in sect_summs_old]
        elif title == 'The Secret Sharer' and source == 'monkeynotes':
            chap1 = set(['Section 1', 'Section 2', 'Section 3', 'Section 4'])
            chap2 = set(['Section 5', 'Section 6', 'Section 7', 'Section 8'])
            chap1_text, chap2_text = [], []
            for sect_title, sect_summ in sect_summs_old:
                if sect_title in chap1:
                    chap1_text.extend(sect_summ)
                elif sect_title in chap2:
                    chap2_text.extend(sect_summ)
            sect_summs_new = [('Chapter 1', chap1_text), ('Chapter 2', chap2_text)]
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
        seen.add((title, source))
        if start:  # for debugging
            print(title, source, idx)
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

    page_title_map = {}
    for source, base_url, books_list in tups:
        index_pages = get_index_pages(books_list, source)
        pages, titles = get_pages_titles(index_pages, books_list, title_set)
        d = dict(zip(pages, titles))
        page_title_map.update(d)
        print('{} book pages from {}'.format(len(d), books_list))
    print('{} book pages total'.format(len(page_title_map)))
    book_summaries = get_summaries(page_title_map, args.out_name, args.use_pickled, args.archived,
                                   args.update_old, args.save_every, args.sleep)
    # with open(args.out_name, 'rb') as f:
    #     book_summaries = pickle.load(f)
    book_summaries_overlap = gen_gutenberg_overlap(book_summaries, catalog, filter_plays=True)
    book_summaries_overlap = manual_fix_individual(book_summaries_overlap)

    with open(args.out_name_overlap, 'wb') as f:
        pickle.dump(book_summaries_overlap, f)
    print('wrote to {}'.format(args.out_name_overlap))
