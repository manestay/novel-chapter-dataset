This repository contains scripts to collect book chapter summaries, as well as their corresponding chapter texts.
* summaries: novelguide, cliffsnotes, pinkmonkey\*, bookwolf, sparknotes, gradesaver
* full text: Project Gutenberg

By running these scripts, the user assumes all legal liability for any copyright issues or claims.

\*: note that the site pinkmonkey.com has two sources -- 'monkeynotes' and 'barrons'.

See the file `./scrape_all.sh` for instructions on how to run the scripts. Please create an issue on Github if you're stuck.

This dataset was collected for the ACL 2020 paper https://arxiv.org/abs/2005.01840. If you use it, please cite accordingly:
> Faisal Ladhak, Bryan Li, Yaser Al-Onaizan, and Kathleen McKeown. 2020. Exploring content selection in summarization of novel chapters.  In *Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics*,  pages 5043–5054, Online. Association for Computational Linguistics.

These scripts were last ran on 13 Nov 2020, on archived version only.

COMMON AND KNOWN ISSUES
---
Because of the changing nature of the web, the scripts are unfortunately not as robust as we would like. Therefore, you should monitor each command you run, and watch out for any error messages. Some common cases are listed below. Again, create a Github issue for further help.

* If you get an error like:
```waybackpy.exceptions.WaybackError: Error while retrieving https://archive.org/wayback/available?url={URL}```

Most likely this is an issue with archive.org servers being unreliable, and sometimes failing to load in time. Rerunning the same command should allow you to try retrieving the page again. Note that by default the commands save every 5 books, so if it's constantly crashing at the same page, try setting `--save-every` to 1 or 2. You can also try setting `--sleep` to 5 seconds or so.

* The archived cliffsnotes/gradesaver pages are particularly slow at loading, so you may see many messages like
```error in retrieving {URL}, using original url ```
This might cause errors if the websites update their formats (see next bullet on how to fix).

* To rescrape a book that was incorrectly scraped, you can use the `scraping/inspect_book.py` script to delete the corrupted entry from the pickled file and try again. To give an example, let's say "Far from the Madding Crowd" for source "gradesaver" is corrupted. Let's check the contents first:
```python scraping/inspect_book.py gradesaver "Far from the Madding Crowd" show```

We can delete by changing the flag, and confirming with 'y':
```python scraping/inspect_book.py gradesaver "Far from the Madding Crowd" del```

Then, run the same command from scrape_all.sh for gradesaver again.
