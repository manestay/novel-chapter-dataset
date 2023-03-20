This repository contains scripts to collect book chapter summaries, as well as their corresponding chapter texts. The dataset is intended for use by AI researchers who are building automatic summarization systems.

* summaries: novelguide, cliffsnotes, pinkmonkey\*, bookwolf, gradesaver
* full text: Project Gutenberg

By running these scripts, the user assumes all legal liability for any copyright issues or claims.

\*: note that the site pinkmonkey.com has two sources -- 'monkeynotes' and 'barrons'.

See the file `scrape_all.sh` for instructions on how to run the scripts.

This dataset was collected for the ACL 2020 paper https://arxiv.org/abs/2005.01840. If you use it, please cite accordingly:
> Faisal Ladhak, Bryan Li, Yaser Al-Onaizan, and Kathleen McKeown. 2020. Exploring content selection in summarization of novel chapters.  In *Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics*,  pages 5043–5054, Online. Association for Computational Linguistics.

See `FAQ.md` for common issues and crashes. Please create an issue on Github if you run into any other problems.

These scripts were last ran by the authors on 29 Mar 2021, on archived version only.

# Shared Task
This dataset was used as part of the shared task for the [Creative-Summ](https://creativesumm.github.io/) workshop at COLING 2022. A revised version of the novel chapter summarization task can be found at the associated [repository](https://github.com/fladhak/creative-summ-data/tree/main/booksum).
