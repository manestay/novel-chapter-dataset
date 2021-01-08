'''
Get 1 book entry from specified pk, and delete/show it. Useful for rescraping books.
'''

from argparse import ArgumentParser
import dill as pickle

# FNAME = 'pks/raw_texts.pk'
# FNAME = 'pks/summaries_sparknotes_all.pk'
# TITLE = "Don Quixote"

parser = ArgumentParser()
parser.add_argument('source')
parser.add_argument('title')
parser.add_argument('action', choices=['del', 'show'])

def find_dict(dd, title, action):
    to_pop = None
    for i, (t, book) in enumerate(dd.items()):
        if t == title:
            print(i, title)
            to_pop = title
        if action == 'show':
            if not book.section_summaries:
                print('NO CHAPTERS')
            for ss in book.section_summaries:
                print(ss[0], ss[1][0:5], '...')
    if action == 'del' and to_pop:
        dd.pop(to_pop)

def find_list(dd, title, action, flag=''):
    for i, x in enumerate(dd):
        t = x.title
        source_bool = True if not flag else x.source == flag
        if source_bool and t == title:
            print(i, t)
            if action == 'del':
                dd.pop(i)
            elif action == 'show':
                if not x.section_summaries:
                    print('NO CHAPTERS')
                for ss in x.section_summaries:
                    print(ss[0], ss[1][0][0:100], '...')

def get_fname(args):
    flag = ''
    if args.source == 'raw_texts':
        fname = 'pks/raw_texts.pk'
    elif args.source == 'barrons' or args.source == 'monkeynotes':
        flag = args.source
        fname = 'pks/summaries_pinkmonkey_all.pk'
    else:
        fname = f'pks/summaries_{args.source}_all.pk'
    return flag, fname

if __name__ == "__main__":
    args = parser.parse_args()
    flag, fname = get_fname(args)
    with open(fname, 'rb') as f:
        dd = pickle.load(f)
    if isinstance(dd, dict):
        find_dict(dd, args.title, args.action)
    else:
        find_list(dd, args.title, args.action, flag)

    if args.action == 'del':
        confirm = input(f'confirm delete of {args.title} from {fname} (y/n)? ')
        if confirm == 'y':
            with open(fname, 'wb') as f:
                pickle.dump(dd, f)
            print('deleted')
