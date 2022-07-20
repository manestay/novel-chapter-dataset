import json
from copy import deepcopy
from pathlib import Path

import dill as pickle

from make_data_splits import get_section_titles

PICKLE_DIR_OLD = Path('pks')
PICKLE_DIR_NEW = Path('pks')
# PICKLE_DIR_NEW = Path('pks_concat')
MISSING_LIST = Path('missing_summaries_novelchaps.txt')

# BAD_LINKS = [
#     'The Adventures of Tom Sawyer.Chapter 16-18.novelguide',
#     'The Adventures of Tom Sawyer.Chapter 19-21.novelguide',
#     'The Adventures of Tom Sawyer.Chapter 22-25.novelguide',
# ]

MISSING_ENTRIES = [
    'The Scarlet Pimpernel.Chapter 5-6.novelguide',
    'The Count of Monte Cristo.Chapter 16-20.novelguide',
    'The Mayor of Casterbridge.Chapter 27-32.novelguide',
    'The Mayor of Casterbridge.Chapter 33-38.novelguide',
    'The Mayor of Casterbridge.Chapter 39-45.novelguide',
    'Washington Square.Chapter 31-35.gradesaver',
    'Washington Square.Chapter 10-12.novelguide',
    'Great Expectations.Part 1: Chapter 1-10.gradesaver',
    'Great Expectations.Part 1: Chapter 11-19.gradesaver',
    'Great Expectations.Part 2: Chapter 1-10.gradesaver',
    'Great Expectations.Part 2: Chapter 11-20.gradesaver',
    'Great Expectations.Part 3: Chapter 1-10.gradesaver',
    'Great Expectations.Part 3: Chapter 11-20.gradesaver',
    'Silas Marner.Chapter 21-conclusion.gradesaver',
    'Silas Marner.Chapter 19.novelguide',
    'Moby Dick.Chapter 17-19.novelguide',
    'The War of the Worlds.Book 2: Chapter 6-10.novelguide',
    'The Adventures of Tom Sawyer.Chapter 35-36.novelguide',
]

if __name__ == "__main__":
    entries = []
    with MISSING_LIST.open('r') as f:
        for line in f:
            entries.append(json.loads(line))

    sources = set(x['source'] for x in entries)

    pk_d = {}
    for source in sources:
        with (PICKLE_DIR_OLD / f'summaries_{source}.pk').open('rb') as f:
            source_books = pickle.load(f)
            pk_d[source] = {x.title: x for x in source_books}

    good = 0
    for i, entry in enumerate(entries):
        source = entry['source']
        chap_id = entry['chapter_id']
        book, chap = chap_id.rsplit('.', 1)

        entry_id = f'{chap_id}.{source}'
        # print(f'processing {entry_id}')

        curr_book = pk_d[source][book]

        sect_summs_old = curr_book.section_summaries

        # sect_summs_new = deepcopy(sect_summs_old)

        curr_summs = {x[0]: x for x in sect_summs_old}

        all_chaps = list(curr_summs.keys())
        section_titles = get_section_titles(all_chaps, chap)

        try:
            sect_summs_concat = [curr_summs[st][1] for st in section_titles]
            sect_summs_concat = [sent for summ in sect_summs_concat for sent in summ]
        except KeyError as e:
            if entry_id in MISSING_ENTRIES:
                print(f'skipping missing entry {entry_id}')
                continue
            else:
                raise KeyError(entry_id)
                continue

        links = [curr_summs[st][2] for st in section_titles]

        # if entry_id not in BAD_LINKS:
        #     assert all(x == links[0] for x in links)

        sect_summ_entry = (
            chap,
            sect_summs_concat,
            links[0]
        )
        sect_summs_old.append(sect_summ_entry)
        good += 1
        pk_d[source][book] = curr_book

    PICKLE_DIR_NEW.mkdir(exist_ok=True)

    for source, new_dict in pk_d.items():
        new_name = (PICKLE_DIR_NEW / f'summaries_{source}_new.pk')
        print(new_name)
        new_list = list(new_dict.values())
        with new_name.open('wb') as f:
            pickle.dump(new_list, f)

    print(f'{good} / {len(entries)}')
