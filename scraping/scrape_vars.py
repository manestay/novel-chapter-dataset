import re

ID_FILE = './ids.json'
CATALOG_RAW_NAME = 'pks/gutenberg_catalog_raw.pk'
CATALOG_NAME = 'pks/gutenberg_catalog.pk'

chapter_re = r'([Cc][Hh][Aa][Pp][Tt][Ee][Rr])\s?(\w*)\.?'
letters_re = re.compile('(?:([Ll][Ee][Tt][Tt][Ee][Rr])\s?(\w*)|Final Letters)\.?')
act_re = r'\b([Aa][Cc][Tt])(?:\s+)?(\w*)'
book_re = r'\b([Bb][Oo][Oo][Kk])\s?(\w*)'
volume_re = r'([Vv][Oo][Ll][Uu][Mm][Ee])\s?(\w*)\.?'
part_re = r'([Pp][Aa][Rr][Tt])\s?(\w*)'
phase_re = re.compile(r'(Phase)\s?(\w*)')
stave_re = r'([Ss][Tt][Aa][Vv][Ee])(?:\s+)?(\w*)\.?'
scene_re = r'([Ss][Cc][Ee][Nn][Ee])(?:\s+)?(\w*)\.?'
act_scene_re = r'([Ss][Cc][Ee][Nn][Ee])\s?(\w*)\.(\w*)'
epilogue_re = re.compile('(?:First|Second) Epilogue')  # for War and Peace
additional_sect_re = re.compile('^(Induction|Conclusion|Sequel|Preface)$')
additional_sub_re = re.compile('(Introduction|Prologue|Epilogue|Finale|The Book of the Grotesque|Prelude)', re.IGNORECASE)
num_re = re.compile(r'\s*(?:\d+)\.?\s*')

play_re = re.compile('({}|{}|{})'.format(act_re, scene_re, act_scene_re))

RE_ROMAN = re.compile(r"\b(M{1,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})|M{0,4}(CM|C?D|D?C{1,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})|M{0,4}(CM|CD|D?C{0,3})(XC|X?L|L?X{1,3})(IX|IV|V?I{0,3})|M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|I?V|V?I{1,3}))\b")
# RE_NUMWORDS defined in scrape_lib.py, since it needs get_numwords function
RE_SUMM = r'\s?Summary:?$'
RE_SUMM_START = r'^(Novel )?Summary\s?(:|,|of)?\s?'
RE_ANALYSIS = r'\s?Analysis:?$'

RE_CHAPTER_START = r'^(Chapter|CHAPTER) \d+'
RE_CHAPTER = RE_CHAPTER_START + r'$'
RE_CHAPTER_NOSPACE = re.compile(r'Chapters?\d+', re.IGNORECASE)
RE_CHAPTER_DASH = re.compile(r'(Chapter|CHAPTER|Stave) \d+\s*(?:-|:)\s*[a-zA-Z]+')
RE_PART = re.compile(r'Part \d+', re.IGNORECASE)
RE_PART_NOSPACE = re.compile(r'Part\d+', re.IGNORECASE)
RE_MULTI_CHAPTER = re.compile(r'\d+\s*-\s*\d+')

book_map = {
    'book the first': 'Book 1',
    'book the second': 'Book 2',
    'book the third': 'Book 3',
    'first act': 'Act 1',
    'second act': 'Act 2',
    'third act': 'Act 3',
    'fourth act': 'Act 4',
    'first': 'Act 1',
    'second': 'Act 2',
    'third': 'Act 3',
    'fourth': 'Act 4',
    'book first': 'Book 1',
    'book second': 'Book 2',
    'book third': 'Book 3',
    'book fourth': 'Book 4',
    'book fifth': 'Book 5',
    'book sixth': 'Book 6',
    'book seventh': 'Book 7',
    'book eighth': 'Book 8',
    'book ninth': 'Book 9',
    'book tenth': 'Book 10',
    'book eleventh': 'Book 11',
    'book twelfth': 'Book 12',
    'part first': 'Part 1',
    'part second': 'Part 2',
    'part third': 'Part 3',
    'part fourth': 'Part 4',
    'part fifth': 'Part 5',
    'part sixth': 'Part 6',
    'part the first': 'Part 1',
    'part the second': 'Part 2',
    'part the third': 'Part 3',
    'part the fourth': 'Part 4',
    'part the fifth': 'Part 5',
    'part the sixth': 'Part 6',
    'phase the first': 'Phase 1',
    'phase the second': 'Phase 2',
    'phase the third': 'Phase 3',
    'phase the fourth': 'Phase 4',
    'phase the fifth': 'Phase 5',
    'phase the sixth': 'Phase 6',
    'phase the seventh': 'Phase 7',
    'first part': 'Part 1',
    'second part': 'Part 2',
}

ACT_ONLY_PLAYS = set(['The Odyssey', 'The Iliad', 'Major Barbara', "A Doll's House",
                      "An Enemy of the People", "The Aeneid", "Hedda Gabler",
                      "Pygmalion", "Arms and the Man", "Anthem"])


""" Variables for manual fixing Gutenberg and summary sources.
    TODO: better organize these different manual fix methods, since they all do similar things in various files and
    functions, but they could be done at once place
"""
ALT_ORIG_MAP = dict((
    ('Tess of the d\'Urbervilles', 'Tess of the d\'Urbervilles: A Pure Woman'),
    ('Tom Sawyer', 'The Adventures of Tom Sawyer'),
    ('Huckleberry Finn', "The Adventures of Huckleberry Finn (Tom Sawyer's Comrade)"),
    ('Dr. Jekyll and Mr. Hyde', 'The Strange Case of Dr. Jekyll and Mr. Hyde'),
    ('The Last of the Mohicans', 'The Last of the Mohicans; A narrative of 1757'),
    ('The Count of Monte Cristo', 'The Count of Monte Cristo, Illustrated'),
    ('Turn of the Screw', 'The Turn of the Screw'),
    ('Ivanhoe', 'Ivanhoe: A Romance'),
    ('Walden', 'Walden, and On The Duty Of Civil Disobedience'),
    ("Connecticut Yankee in King Arthur's Court", "A Connecticut Yankee in King Arthur's Court"),
    ("Narrative of the Life of Frederick Douglass", "Narrative of the Life of Frederick Douglass, an American Slave"),
    ('Alice in Wonderland', "Alice's Adventures in Wonderland"),
    ('Merry Wives of Windsor', "The Merry Wives of Windsor"),
    ("Aristotle's Politics", "Politics: A Treatise on Government"),
    ("Ivanhoe", "Ivanhoe: A Romance"),
    ("Romeo and Juliet", "The Tragedy of Romeo and Juliet"),
    ("Winesburg, Ohio", 'Winesburg, Ohio: A Group of Tales of Ohio Small Town Life'),
    ("The Awakening", "The Awakening, and Selected Short Stories"),
    ('Jane Eyre', 'Jane Eyre: An Autobiography'),
    ("Under the Greenwood Tree", "Under the Greenwood Tree; Or, The Mellstock Quire\rA Rural Painting of the Dutch School"),
    ('The Metamorphosis', 'Metamorphosis'),
    ('Frankenstein', 'Frankenstein; Or, The Modern Prometheus'),
    ("Gulliver's Travels", "Gulliver's Travels into Several Remote Nations of the World"),
    ("The Importance of Being Earnest", 'The Importance of Being Earnest: A Trivial Comedy for Serious People'),
    ('War of the Worlds', 'The War of the Worlds'),
    ('Moby Dick', "Moby Dick; Or, The Whale"),
    ('Moby-Dick', 'Moby Dick'),
    ('Aeneid', 'The Aeneid'),
    ('A Journal of the Plague Year', 'A Journal of the Plague Year\rWritten by a Citizen Who Continued All the While in London'),
    ('Moll Flanders', 'The Fortunes and Misfortunes of the Famous Moll Flanders'),
    ('The Secret Agent', 'The Secret Agent: A Simple Tale'),
    ('The Island of Dr. Moreau', 'The Island of Doctor Moreau'),
    ('Twenty Thousand Leagues Under the Sea', 'Twenty Thousand Leagues Under the Seas: An Underwater Tour of the World'),
    ('Looking Backward', 'Looking Backward: 2000-1887')
))

# EXCLUDED_IDS = set([100, 19033, 50834, 3070, 51713, 42671, 27, 18881, 1249, 45839, 47634, 15, 120, 19337, 42, 1232,
#                     2891, 17500, 26740, 4078])
EXCLUDED_IDS = set([100, 19033, 50834, 3070, 51713, 42671, 18881, 1249, 47634, 15, 42, 1232,
                    2891, 4078])

TO_DELETE = set([
    'The Adventures of Sherlock Holmes', 'The Power and the Glory', 'The Jew of Malta',
    'Crito', 'Meno', 'Apology', 'Phaedo', 'The Republic', "Aristotle's Politics", "Phaedra", "Phaedrus",
    "Aeneid", "The Aeneid", "The Iliad", "The Odyssey", "Ethics",
    'The Fall of the House of Usher', 'Paradise Lost', 'Utopia', 'Common Sense',
    # next line has cases where it is a different book with the same title
    'Our Town', 'Native Son', 'The Plague', 'The Inferno', 'Salome', 'Regeneration',  'The Storm', 'The Alchemist',
    'Autobiography of Benjamin Franklin', "The Autobiography of Benjamin Franklin",
    'Les Misérables', 'The Sign of the Four', 'The Sorrows of Young Werther', 'Lysistrata',
    'The Jungle Book', 'Narrative of the Life of Frederick Douglass', "Twilight", "A Journal of the Plague Year",
    # inconsistently named chapters
    'The Moonstone', 'The Woman in White', "Cane", "Swann's Way", "Moll Flanders"])

NON_NOVEL_TITLES = set(['The Consolation of Philosophy', 'The Federalist Papers', 'The Flowers of Evil', 'The Frogs',
                        'Gargantua and Pantagruel', 'Gorgias', "Leaves of Grass", 'The Rime of the Ancient Mariner',
                        "The Legend of Sleepy Hollow", 'Leviathan', 'The Prince', 'Riders to the Sea', 'The Souls of Black Folk',
                        "Second Treatise of Government", "A Sentimental Journey Through France and Italy", "Titanic", "Poetry",
                        "Shakespeare's Sonnets", "Troilus and Criseyde", "Utilitarianism", "The Waste Land", "The Praise of Folly",
                        "The Wild Swans at Coole", "The Birds", "The Blessed Damozel", "Children of Men", "On Liberty",
                        "Mr. Smith Goes to Washington", "Don Juan", "Idylls of the King", "Rope", "The Road",
                        "An Occurrence at Owl Creek Bridge"])
