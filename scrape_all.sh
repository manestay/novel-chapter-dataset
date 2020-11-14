# scrape_all.sh
# This script contains all commands to get the final data set.
# Probably best to run each command one-by-one.

## 0) Uncomment these optional flags to collect all books from all sources, and skip the filtering out
## that was done for the ACL 2020 publication. However, this has not been fully tested and you will
## have to do your own text and HTML cleanup.
# TAG="--full"
# EXT="_full"

## 1) Install requirements -- you might want to use a python3 virtualenv for this
pip install -r requirements.txt

## YOU CAN SKIP STEPS 2 AND 3 AND GO DIRECTLY TO 4, SINCE THIS REPO INCLUDES THE CATALOG.

## 2) Download and unpack the Gutenberg mirror (this takes a while).
# wget -c https://www.gutenberg.org/cache/epub/feeds/rdf-files.tar.zip
# unzip rdf-files.tar.zip
# tar xvf rdf-files.tar

## 3) Collect catalog from Project Gutenberg. Gutenberg catalog object has links to
## HTML pages of each book.
# python gutenberg/run_all.py --use-pickled ${TAG}

## RECOMMENDED TO START FROM 4, AND SKIP 2 and 3

## 4) Collect summaries from each source.
## Notes: several sources take a long time -- sparknotes, gradesaver
## --archived : remove this flag to scrape from the live pages. This is faster,  but the dataset
## but the sites update and probably will break things.
## --use-pickled : remove this flag and the following path to recollect already existing summaries.
## -- update-old : if --archived, then updates archive link if out of date (be careful with this)
PREFIX=pks/summaries_
echo -e '\nbookwolf'
python scraping/bookwolf_scrape.py ${PREFIX}bookwolf_all${EXT}.pk ${PREFIX}bookwolf${EXT}.pk --use-pickled --archived ${TAG}
echo -e '\ncliffsnotes'
python scraping/cliffsnotes_scrape.py ${PREFIX}cliffsnotes_all${EXT}.pk ${PREFIX}cliffsnotes${EXT}.pk --use-pickled --archived ${TAG}
echo -e '\npinkmonkey'
python scraping/pinkmonkey_scrape.py ${PREFIX}pinkmonkey_all${EXT}.pk ${PREFIX}pinkmonkey${EXT}.pk --use-pickled --archived ${TAG}
echo -e '\ngradesaver'
python scraping/gradesaver_scrape.py ${PREFIX}gradesaver_all${EXT}.pk ${PREFIX}gradesaver${EXT}.pk --use-pickled --archived ${TAG}
echo -e '\nnovelguide'
python scraping/novelguide_scrape.py ${PREFIX}novelguide_all${EXT}.pk ${PREFIX}novelguide${EXT}.pk --use-pickled --archived ${TAG}
echo -e '\nsparknotes'
python scraping/sparknotes_scrape.py ${PREFIX}sparknotes_all${EXT}.pk ${PREFIX}sparknotes${EXT}.pk =-use-pickled --archived ${TAG}

## 5) Collect raw texts from Project Gutenberg
## Gutenberg raw texts object has raw text of each book by chapter
python scraping/gutenberg_scrape.py --use-pickled

## 6) Make the data splits.
## There should be 98 books in total. The script will fail if any are missing.
## This script prints missing/extra chapters based on pair_ids_expected.json. This might be because
## the websites updated, or something went wrong while scraping. Contact authors with questions.
python make_data_splits.py

## the data splits will be saved ./raw_splits/{train, test, val}.pk
