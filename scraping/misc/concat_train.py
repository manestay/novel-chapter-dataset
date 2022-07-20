import json
from copy import deepcopy
from pathlib import Path

import dill as pickle

from make_data_splits import get_section_titles

PICKLE_DIR_OLD = Path('pks')
PICKLE_DIR_NEW = Path('pks')
# PICKLE_DIR_NEW = Path('pks_concat')
MISSING_LIST = Path('missing_summaries_novelchaps.txt')

LIST = [
'The Scarlet Pimpernel.Chapter 5-6.novelguide',
'The Count of Monte Cristo.Chapter 16-20.novelguide',
'The Mayor of Casterbridge.Chapter 27-32.novelguide',
'The Mayor of Casterbridge.Chapter 33-38.novelguide',
'The Mayor of Casterbridge.Chapter 39-45.novelguide',
'The War of the Worlds.Book 2: Chapter 6-10.novelguide',
]

if __name__ == "__main__":
    entries = []
    with MISSING_LIST.open('r') as f:
        for line in f:
            entries.append(json.loads(line))

    pk_d = {}

    with (Path('raw_splits') / f'train_og.pk').open('rb') as f:
        source_books = pickle.load(f)
        pk_d = {x['id']: x for x in source_books}


    good = 0
    for i, entry in enumerate(entries):
        source = entry['source']
        chap_id = entry['chapter_id']
        book, chap = chap_id.rsplit('.', 1)

        entry_id = f'{chap_id}.{source}'
        if entry_id not in LIST:
            continue

        print(f'processing {entry_id}')

        all_chaps = [x['id'] for x in pk_d.values() if x['id'].startswith(book)]
        all_chaps = [x.rsplit('.', 1)[-1] for x in all_chaps]

        section_titles = get_section_titles(all_chaps, chap)

        for st in section_titles:
            print(st)
            summs = pk_d[f'{book}.{st}']['summaries']
            for summ in summs:
                if summ['source'] == source:
                    for sent in summ['summary']:
                        print(sent)
                print()
        input()
