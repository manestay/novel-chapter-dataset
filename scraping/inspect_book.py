'''
Get 1 book entry from specified pk, and delete/show it. Useful for rescraping books.
'''

from argparse import ArgumentParser
import dill as pickle

# FNAME = 'pks/raw_texts.pk'
# FNAME = 'pks/summaries_sparknotes_all.pk'
# TITLE = "Don Quixote"

# note these sources are not exactly the same as those in scraping/gutenberg_scrape.py, since
# we split the 'pinkmonkey' sources
SOURCES = ['gradesaver', 'cliffsnotes', 'barrons', 'monkeynotes', 'novelguide', 'bookwolf']
source_choices = SOURCES + ['all']  # all scans all sources

parser = ArgumentParser()
parser.add_argument('source', choices=source_choices)
parser.add_argument('title')
parser.add_argument('action', choices=['del', 'show'])
parser.add_argument('--use_all', action='store_true', default=False, help='use *_all.pk instead')


def find_dict(dd, title, action):
    found = False
    to_pop = None
    for i, (t, book) in enumerate(dd.items()):
        if t == title:
            found = True
            print(i, title)
            to_pop = title
        if action == 'show':
            if not book.section_summaries:
                print('NO CHAPTERS')
            for ss in book.section_summaries:
                print(ss[0], ss[1][0:5], '... ', end='')
                print(ss[2] if len(ss) == 3 else '')
    if action == 'del' and to_pop:
        dd.pop(to_pop)
    return found


def find_list(dd, title, action, flag=''):
    found = False
    for i, x in enumerate(dd):
        t = x.title
        source_bool = True if not flag else x.source == flag
        if source_bool and t == title:
            found = True
            print(i, t)
            if action == 'del':
                dd.pop(i)
            elif action == 'show':
                for ss in x.section_summaries:
                    if not ss[1]:
                        print(ss[0], '{empty}', ss[2] if len(ss) == 3 else '')
                    elif isinstance(ss[1][0], tuple):
                        for ss1 in ss[1]:
                            print(ss1[0], ss1[1][0:100], '... ', end='')
                            print(ss[2] if len(ss) == 3 else '')
                    else:
                        try:
                            print(ss[0], ss[1][0][0:100], '... ', end='')
                            print(ss[2] if len(ss) == 3 else '')
                        except IndexError:
                            print(f'ERROR: {ss[0]} has no summary content')
    return found


def get_fname(args):
    flag = ''
    all = '_all' if args.use_all else ''
    if args.source == 'raw_texts':
        fname = 'pks/raw_texts.pk'
    elif args.source == 'barrons' or args.source == 'monkeynotes':
        flag = args.source
        fname = f'pks/summaries_pinkmonkey{all}.pk'
    else:
        fname = f'pks/summaries_{args.source}{all}.pk'
    return flag, fname


def main(args):
    flag, fname = get_fname(args)
    with open(fname, 'rb') as f:
        dd = pickle.load(f)
    if isinstance(dd, dict):
        found = find_dict(dd, args.title, args.action)
    else:
        found = find_list(dd, args.title, args.action, flag)

    if args.action == 'del':
        if not found:
            print(f'could not find {args.title} in {fname}')
            confirm = 'n'
        else:
            if not args.use_all:
                print(f'NOTE: If you are trying to rescrape a book, run this command with --use-all'
                      ' so you can delete from the raw pk instead.')
            confirm = input(f'confirm delete of {args.title} from {fname} (y/n)? ')
        if confirm == 'y':
            with open(fname, 'wb') as f:
                pickle.dump(dd, f)
            print('deleted')
        else:
            print('nothing modified')


if __name__ == "__main__":
    args = parser.parse_args()
    if args.source == 'all':
        for source in SOURCES:
            print(f'source: {source}')
            print('*' * 50)
            args.source = source
            main(args)
            print()
    else:
        main(args)
