"""
make_data_splits.py

Makes train/val/test splits for data, saves them as .pk files.
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from copy import deepcopy

import dill as pickle

sys.path.append('./scraping')
from gutenberg_scrape import SOURCES, SUMMARY_PATHS, PICKLE_NAME, RE_MULTI_CHAPTER
from scrape_lib import titlecase
from scrape_vars import RE_CHAPTER

SPLITS_NAME = './splits.json'
PAIR_IDS_NAME = './pair_ids_expected.json'
OUT_DIR = 'raw_splits'

parser = argparse.ArgumentParser(description='make train/val/test .pk files')
parser.add_argument('--summaries', '-su', nargs='*', default=SUMMARY_PATHS, help='paths to summaries')
parser.add_argument('--splits', '-sp', default=SPLITS_NAME, help='path to split JSON')
parser.add_argument('--raw_texts', '-rt', default=PICKLE_NAME, help='path to raw texts')
parser.add_argument('--out_dir', '-o', default=OUT_DIR, help='directory to write split .pks to')
parser.add_argument('--pair_ids_expected', '-pi', default=PAIR_IDS_NAME, help='path to expected pair ids JSON')

# could integrate into *_scrape.py scripts, but quick fix to avoid rescraping
expected_errors = set([
    ('The Adventures of Tom Sawyer', 'sparknotes', frozenset(['Conclusion'])),
    ('Frankenstein', 'sparknotes', frozenset(['Preface'])),
    ('Little Women', 'sparknotes', frozenset(['Preface'])),
    ("A Connecticut Yankee in King Arthur's Court", 'sparknotes', frozenset(['Preface-Note of Explanation'])),
    ("A Connecticut Yankee in King Arthur's Court", 'cliffsnotes', frozenset(['A Word of Explanation'])),
    ("Don Quixote", 'cliffsnotes', frozenset(["Part 1: the Author's Preface", "Part 2: the Author's Preface"])),
    ("Frankenstein", 'cliffsnotes', frozenset(['Introduction-the 1831 Edition', 'Preface-the 1817 Edition'])),
    ("The Last of the Mohicans", 'cliffsnotes', frozenset(["Cooper's 3 Prefaces"])),
    ("The Scarlet Letter", 'cliffsnotes', frozenset(['The Custom-House'])),
    ("Heart of Darkness", 'barrons', frozenset(['Epilogue'])),
    ("The Scarlet Letter", 'novelguide', frozenset(['Introduction'])),
    ("The Count of Monte Cristo", 'novelguide', frozenset(['Chapter 34', 'Chapter 39', 'Chapter 44'])),
])


def split_title_sect(sect_id):
    """ Splits sect_id into title and section."""
    return sect_id.rsplit('.', 1)


def get_sect_id(title, sect):
    return '{}.{}'.format(title, sect)


def validate_titles(all_titles_raw, all_titles_splits):
    only_splits = all_titles_splits - all_titles_raw
    # validation of book titles
    if only_splits:
        print('{} books in {} but not in {} -- need to rescrape'.format(
            len(only_splits), args.splits, args.raw_texts))
        for title in only_splits:
            print(title)
    only_raw = all_titles_raw - all_titles_splits
    if only_raw:
        print('{} books in {} but not in {} -- need to rescrape'.format(
            len(only_raw), args.raw_texts, args.splits))
        for title in only_raw:
            print(title)
    if not only_raw and not only_splits:
        print('validated that titles in scraped pk files are the same as in {}'.format(args.splits))
    else:
        os._exit(-1)


def validate_pair_ids(pair_ids, expected_name):
    if not os.path.exists(expected_name):
        print('pair ids not found')
        return

    with open(expected_name, 'r') as f:
        pair_ids_expected = set(json.load(f))
    pair_ids = set(pair_ids)

    missing = pair_ids_expected - pair_ids
    extra = pair_ids - pair_ids_expected
    if not missing and not extra:
        print('validated that collected pair ids == expected pair ids')
        print('{} pair ids total'.format(len(pair_ids)))
        print('All set!')
        return
    if missing:
        print('\nWARNING: {} pair ids are missing from collected summaries, but exist in expected summaries'.format(len(missing)))
        print('You should consider rescraping')
        for x in sorted(missing):
            print(x)
    if extra:
        print('\nWARNING: {} pair ids are found in collected summaries, but not in expected summaries'.format(len(extra)))
        for x in sorted(extra):
            print(x)
    if missing or extra:
        print('to fix, try deleting and rescraping the books with issues (see FAQ.md)')


def get_section_titles(all_sections, sect, title=None):
    """ all_sections (list): list of section titles
        sect (str): section name
    """
    chapter_range = re.search(RE_MULTI_CHAPTER, sect)
    if chapter_range and 'Letters' in sect:
        sect = sect.replace('Letters', 'Letter')

    if title == 'Siddhartha' and sect == 'Part 1':
        titles = ["The Brahmin's Son", 'With the Samanas', 'Gotama', 'Awakening']
        return ['Part 1:  {}'.format(title) for title in titles]
    elif title == 'Siddhartha' and sect == 'Part 2':
        titles = ['Kamala', 'Amongst the People', 'Samsara', 'By the River', 'The Ferryman', 'The Son', 'Om', 'Govinda']
        return ['Part 2:  {}'.format(title) for title in titles]
    elif title == 'Middlemarch' and sect == 'Chapter 80-Finale':
        return get_section_titles(all_sections, 'Chapter 80-86', title) + ['Finale']
    elif title == "A Connecticut Yankee in King Arthur's Court" and sect == 'Chapter 31-Postscript':
        return get_section_titles(all_sections, 'Chapter 31-45', title)
    elif title == "A Connecticut Yankee in King Arthur's Court" and sect == 'Chapter 44-Postscript':
        return get_section_titles(all_sections, 'Chapter 31-45', title)
    elif title == "The Prince and the Pauper" and sect == 'Chapter 33-Conclusion':
        return ['Chapter 33', 'Conclusion']
    elif title == "The Three Musketeers" and sect == 'Chapter 64-Epilogue':
        return get_section_titles(all_sections, 'Chapter 64-67', title) + ['Epilogue']
    elif title == "The Three Musketeers" and sect == 'Conclusion-Epilogue':
        return ['Chapter 67', 'Epilogue']
    elif title == "Winesburg, Ohio" and sect == 'Godliness':
        return get_section_titles(all_sections, 'Godliness Part 1-4', title)
    elif title == "The Picture of Dorian Gray" and sect == 'Preface-Chapter 2':
        return ['Preface'] + get_section_titles(all_sections, 'Chapter 1-2', title)
    elif title == "Typee" and sect == 'Preface-Chapter 5':
        return ['Preface'] + get_section_titles(all_sections, 'Chapter 1-5', title)

    if chapter_range:
        chapters = []
        base = re.sub(RE_MULTI_CHAPTER, '', sect)
        start, end = chapter_range[0].split('-', 1)
        for i in range(int(start), int(end) + 1):
            chapter = '{}{}'.format(base, i)
            chapters.append(chapter)
    elif ',' in sect:
        chapters = [x.strip() for x in sect.split(',')]
    elif not re.match(RE_CHAPTER, sect):
        keys = [x for x in all_sections if x.lower().startswith(sect.lower() + ':')]
        try:
            chapters = sorted(keys, key=lambda x: int(x.rsplit(' ', 1)[-1]))
            if not chapters:
                chapters = [sect]
        except ValueError as e:
            print(e, title)
            chapters = [sect]
    else:
        chapters = [sect]
    return chapters


def get_section_text(raw_text, sect_id):
    """ raw_text (dict): raw text for book
        sect_id (str): section id of format '<title>.<section>'
    """
    section_text = []
    title, sect = split_title_sect(sect_id)
    chapters = get_section_titles(raw_text.keys(), sect, title)
    for chapter in chapters:
        chap_text = raw_text.get(chapter) or raw_text.get(titlecase(chapter))
        if not chap_text:
            # print(chapter, 'not found', title)
            continue
        section_text.extend(chap_text)
    return section_text


def process_book_summary(book_summary, title_sect_map, base_d):
    error_sects = []
    section_summaries = book_summary.section_summaries
    source = book_summary.source
    title = book_summary.title

    if not title_sect_map[title]:
        print('{} is a new book'.format(title), source)
    for sect, sect_summ, link in section_summaries:
        sect = re.sub(r'\s*-\s*', '-', sect)
        sect_id = get_sect_id(title, sect)
        summ_d = {'summary': sect_summ, 'source': source, 'link': link}
        if not sect_summ:
            # print(sect_id, 'empty sect_summ, skipped')
            error_sects.append(sect)
            continue
        if sect_id not in base_d:
            section_text = get_section_text(raw_texts[title], sect_id)
            if section_text:
                title_sect_map[title].add(sect)
            else:
                error_sects.append(sect)
                continue
            base_d[sect_id] = {'id': sect_id, 'summaries': []}
            base_d[sect_id]['raw_text'] = section_text

        base_d[sect_id]['summaries'].append(summ_d)
        # if source == 'barrons' and title == 'The Jungle':
        #     import pdb; pdb.set_trace()
    return error_sects


def get_title_sect_map(raw_texts):
    title_sect_map = {}
    for title, chapter_d in raw_texts.items():
        if title not in title_sect_map:
            title_sect_map[title] = set()
        title_sect_map[title].update(chapter_d.keys())
    return title_sect_map


def get_split_ds(base_d):
    split_ds = {'train': [], 'val': [], 'test': []}
    for sect_id, sect_obj in base_d.items():
        title, sect = split_title_sect(sect_id)
        if title in splits['train']:
            split_d = split_ds['train']
        elif title in splits['val']:
            split_d = split_ds['val']
        elif title in splits['test']:
            split_d = split_ds['test']
        split_d.append(sect_obj)
    return split_ds


def get_base_ds_source(base_d):
    """ Returns dict base_ds, which has entries
        str source_name: summary_d
    """
    base_ds = defaultdict(lambda: defaultdict(dict))
    sect_titles_expanded = {}

    for sect_id, item in base_d.items():
        for summary_d in item['summaries']:
            source = summary_d['source']
            text = summary_d['summary']
            link = summary_d['link']

            title, sect = split_title_sect(sect_id)
            if title not in raw_texts:
                continue
            if text:
                base_ds[source][title][sect] = (text, link)
            book_chapters = raw_texts[title].keys()
            sect_titles_expanded[sect_id] = get_section_titles(book_chapters, sect, title)
    return base_ds, sect_titles_expanded


def compose_multi_sect(base_d, base_ds_source, sect_titles_expanded):
    base_d_expanded = deepcopy(base_d)
    for sect_id, item in base_d.items():
        title, sect = split_title_sect(sect_id)
        if title not in raw_texts:
            continue
        sect_titles = sect_titles_expanded[sect_id]
        if len(sect_titles) < 2: # not multi-part
            continue
        for source, base_d_source in base_ds_source.items():
            source_title_d = base_d_source[title]
            if not source_title_d: continue
            if sect in source_title_d:
    #             print('already exists', sect_id, source)
                continue

            new_sect = []
            links = []
            added_sects_all = set()
            i = 0
            sect_title_len = len(sect_titles)
            while i < sect_title_len:
                chap = sect_titles[i]
                match = False
                for j in range(sect_title_len - 1, i, -1):
                    cand = '{}-{}'.format(chap, sect_titles[j].rsplit(' ', 1)[-1])
                    if cand in source_title_d:
                        curr_text, link = source_title_d[cand]
                        if isinstance(curr_text, list):
                            new_sect.extend(curr_text)
                        elif isinstance(curr_text, str):
                            new_sect.append(curr_text)
                        links.append(link)
                        cand_id = '{}.{}'.format(title, cand)
                        added_sects = sect_titles_expanded[cand_id]
                        assert not added_sects_all.intersection(added_sects)
                        added_sects_all.update(added_sects)
                        i = j + 1
                        match = True
                        break
                if not match: # try finding just the chapter
                    chap_lower = chap.lower() # for War and Peace
                    if chap_lower in source_title_d:
                        chap = chap_lower
                    if chap not in source_title_d:
                        break
                    chap_id = '{}.{}'.format(title, chap)
                    added_sects = sect_titles_expanded[chap_id]
                    if added_sects_all.intersection(added_sects):
                        print(sect_id, source, added_sects_all)
                        print(source_title_d.keys())
                    assert not added_sects_all.intersection(added_sects)
                    added_sects_all.update(added_sects)
                    curr_text, link = source_title_d[chap]
                    if isinstance(curr_text, list):
                        new_sect.extend(curr_text)
                    elif isinstance(curr_text, str):
                        new_sect.append(curr_text)
                    links.append(link)
                    i += 1
                if sect_titles[-1] in added_sects_all:
                    break

            if sect_titles[-1] in added_sects_all:
                assert(added_sects_all == set(sect_titles))
                summ_d = {'summary': new_sect, 'source': source, 'link': links}
                base_d_expanded[sect_id]['summaries'].append(summ_d)

    return base_d_expanded


def count_summaries(split_d): return sum([len(x['summaries']) for x in split_d])


def print_split_ds(base_d):
    split_ds = get_split_ds(base_d)

    assert len(base_d) == len(split_ds['train']) + len(split_ds['val']) + len(split_ds['test'])
    print('{} chapters total, train: {}, val: {}, test: {}'.format(
        len(base_d), len(split_ds['train']), len(split_ds['val']), len(split_ds['test'])))

    num_all = count_summaries(base_d.values())
    num_train = count_summaries(split_ds['train'])
    num_val = count_summaries(split_ds['val'])
    num_test = count_summaries(split_ds['test'])
    assert num_all == num_train + num_val + num_test
    print('{} summary-chapter pairs total, train: {}, val: {}, test: {}'.format(
        num_all, num_train, num_val, num_test))
    return split_ds


def get_pair_ids(base_d):
    pair_ids = []
    for sect_id, book_summ in base_d.items():
        for summ_d in book_summ['summaries']:
            summ_name = summ_d['source']
            pair_id = '{}.{}'.format(sect_id, summ_name)
            pair_ids.append(pair_id)
    return pair_ids


if __name__ == "__main__":
    args = parser.parse_args()
    with open(args.splits, 'r') as f:
        splits = json.load(f)
        splits = {k: set(v) for k, v in splits.items()}
    with open(args.raw_texts, 'rb') as f:
        raw_texts = pickle.load(f)
    all_titles_raw = set(raw_texts.keys())
    all_titles_splits = splits['test'] | splits['train'] | splits['val']
    validate_titles(all_titles_raw, all_titles_splits)
    print('{} books total, train: {}, val: {}, test: {}'.format(
        len(all_titles_splits), len(splits['train']), len(splits['val']), len(splits['test'])))

    title_sect_map = get_title_sect_map(raw_texts)

    base_d = {}
    for i, source_summ_name in enumerate(args.summaries):
        with open(source_summ_name, 'rb') as f:
            source_obj = pickle.load(f)
        errors = False
        for book_summary in source_obj:
            title = book_summary.title
            source = book_summary.source
            chaps_source = [x[0] for x in book_summary.section_summaries]
            if title not in all_titles_raw:
                continue
            error_sects = frozenset(process_book_summary(book_summary, title_sect_map, base_d))
            if error_sects and (title, source, error_sects) not in expected_errors:
                print('DEBUG: error for book {} from source {}'.format(title, source))
                print('sections in gutenberg', sorted(title_sect_map[title]))
                print('sections in source   ', sorted(chaps_source))
                print('sections not found   ', sorted(error_sects))
                bs = book_summary.section_summaries
            # if title == 'Madame Bovary' and source == 'barrons':
            #     import pdb; pdb.set_trace()
    print_split_ds(base_d)

    print('\ncomposing multi-chapter summaries from single-chapter summaries...')
    base_ds_source, sect_titles_expanded = get_base_ds_source(base_d)
    base_d_expanded = compose_multi_sect(base_d, base_ds_source, sect_titles_expanded)
    split_ds = print_split_ds(base_d_expanded)

    os.makedirs(args.out_dir, exist_ok=True)
    for split_name, split_d in split_ds.items():
        out_name = os.path.join(args.out_dir, '{}.pk'.format(split_name))
        with open(out_name, 'wb') as f:
            pickle.dump(split_d, f)
        print('wrote to', out_name)

    pair_ids = get_pair_ids(base_d_expanded)
    out_name = os.path.join(args.out_dir, 'pair_ids.json')
    with open(out_name, 'w') as f:
        json.dump(pair_ids, f, indent=4)
    print('wrote to', out_name)

    validate_pair_ids(pair_ids, args.pair_ids_expected)
