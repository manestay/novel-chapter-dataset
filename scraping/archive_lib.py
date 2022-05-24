import re
from time import sleep
from datetime import datetime

import waybackpy

USER_AGENT = "Mozilla/5.0 (Windows NT 5.1; rv:40.0) Gecko/20100101 Firefox/40.0"

# get the nearest archived version to following date parameters
YEAR = 2021
MONTH = 1
DAY = 1
OLD_DATE = datetime(2018, 6, 1) # if archived version older than this, update

def get_archived(page_url, update_old=False, year=YEAR):
    try:
        waybackpy_url_obj = waybackpy.Url(page_url, USER_AGENT)
        archive_url_near = waybackpy_url_obj.near(year=year, month=MONTH, day=DAY)
    except waybackpy.exceptions.WaybackError as e:
        try: # try again
            sleep(5)
            waybackpy_url_obj = waybackpy.Url(page_url, USER_AGENT)
            archive_url_near = waybackpy_url_obj.near(year=year, month=MONTH, day=DAY)
        except waybackpy.exceptions.WaybackError as e:
            # print(e)
            print('  error in retrieving {} , using original url '.format(page_url))
            return page_url
    url_str = archive_url_near.archive_url
    if update_old:
        date = archive_url_near.timestamp
        if date < OLD_DATE:
            print('updating  {}'.format(url_str, date))
            archive_url_near = update_archive(waybackpy_url_obj)
            if archive_url_near is None:
                print('  could not save page {}'.format(page_url))
            else:
                url_str = archive_url_near.archive_url
                print('  updated to {}'.format(url_str))
    url_str = url_str.replace(':80', '', 1)
    return url_str


def update_archive(waybackpy_url_obj):
    if isinstance(waybackpy_url_obj, str):
        waybackpy_url_obj = waybackpy.Url(waybackpy_url_obj, USER_AGENT)
    try:
        archive_obj = waybackpy_url_obj.save()
    except waybackpy.exceptions.WaybackError as e:
        print(e)
        return None
    return archive_obj


def get_orig_url(url):
    matches = re.split('(https?://)', url)
    return ''.join(matches[-2:])


if __name__ == "__main__":
    print(get_archived('https://www.sparknotes.com/lit/#'))
