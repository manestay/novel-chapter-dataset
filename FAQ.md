This document is intended to serve as a place documenting common issues.

## Section 1. Common Issues
Because of the changing nature of the web, the scripts are unfortunately not as robust as we would like. Therefore, you should monitor each command you run, and watch out for any error messages. Some common cases are listed below. Again, create a Github issue for further help.

* You can ignore several of the messages when running `scraping/pinkmonkey_scrape.py` for the most part. This website has many paywalled pages, as well as inconsistent formatting that we have mostly manually addressed, but can't fully fix.

* If you get an error like:
```
waybackpy.exceptions.WaybackError: Error while retrieving https://archive.org/wayback/available?url={URL}
```
Most likely this is an issue with archive.org servers being unreliable, and sometimes failing to load in time. Rerunning the same command should allow you to try retrieving the page again. Note that by default the commands save every 5 books, so if it's constantly crashing at the same page, try setting `--save-every` to 1 or 2. You can also try setting `--sleep` to 5 seconds or so.

* The archived cliffsnotes/gradesaver pages are particularly slow at loading, so you may see many messages like
```
error in retrieving {URL}, using original url
```
This might cause errors if the websites update their formats (see Section 2).

* When running make_data_splits.py, if you see error messages like
```
DEBUG: error for book {title} from source {source}
```
and corresponding printed chapters, try deleting the entry and rescraping.

* For `scraping/cliffsnotes_scrape.py` the following messages means a page was improperly processed, and the book needs to be rescraped:
```
{url} NO COPY CLASS!'
```
* For `scraping/pinkmonkey_scrape.py` the following message means a page was improperly processed, and the book needs to be rescraped:
```
cannot find section titles on {url}
```
Also, the following books are expected to return errors for pinkmonkey: [The Secret Sharer, Oliver Twist, Siddhartha]. The errors happen because the index pages have chapters with named titles, instead of "Chapter/Book/Volume <number>". We do not currently fix them. So you can ignore these error messages.

* Note that `make_data_splits.py` should catch any cases of missing chapter summaries as well.

## Section 2b. Rescraping corrupted or incompletely scraped books
Use `scraping/inspect_book.py` to delete the corrupted entries from the pickled file(s) and try again. To give an example, let's say "Far from the Madding Crowd" for source "gradesaver" is corrupted. Let's check the contents first:
```
python scraping/inspect_book.py gradesaver "Far from the Madding Crowd" show
```
This will print out the contents of that book, and displays error messages if the book was not found, or if any of the scraped chapter summaries is empty.

To delete, change the flag and confirm with 'y':
```
python scraping/inspect_book.py gradesaver "Far from the Madding Crowd" del
```

Then, run the same command from scrape_all.sh for that source again.
