# -*- coding: utf-8 -*-

import json
import os
import re
import sys
import xml.dom.minidom
from threading import Thread

import requests
import xmltodict
from six.moves import queue as Queue

from utils import logger, map_mime2exts
from ykmlib.fs import makedirs

# Setting timeout
TIMEOUT = 10

# Retry times
RETRY = 5

# Media Index Number that Starts from
START = 0

# Numbers of photos/videos per page
MEDIA_NUM = 50

# Numbers of downloading threads concurrently
THREADS = 1

# Do you like to dump each post as separate json (otherwise you have to extract from bulk xml files)
# This option is for convenience for terminal users who would like to query e.g. with ./jq (https://stedolan.github.io/jq/)
EACH_POST_AS_SEPARATE_JSON = False


def video_hd_match():
    hd_pattern = re.compile(r'.*"hdUrl":("([^\s,]*)"|false),')

    def match(video_player):
        hd_match = hd_pattern.match(video_player)
        try:
            if hd_match is not None and hd_match.group(1) != 'false':
                return hd_match.group(2).replace('\\', '')
        except:
            return None

    return match


def video_default_match():
    default_pattern = re.compile(r'.*src="(\S*)" ', re.DOTALL)

    def match(video_player):
        default_match = default_pattern.match(video_player)
        if default_match is not None:
            try:
                return default_match.group(1)
            except:
                return None

    return match


class DownloadWorker(Thread):
    def __init__(self, queue, proxies=None):
        Thread.__init__(self)
        self.queue = queue
        self.proxies = proxies
        self._register_regex_match_rules()

    def run(self):
        while True:
            media_type, post, target_folder = self.queue.get()
            self.download(media_type, post, target_folder)
            self.queue.task_done()

    def download(self, media_type, post, target_folder):
        try:
            media_url = self._handle_media_url(media_type, post)
            if media_url is not None:
                self._download(media_type, media_url, target_folder)
        except TypeError:
            pass

    # can register different regex match rules
    def _register_regex_match_rules(self):
        # will iterate all the rules
        # the first matched result will be returned
        self.regex_rules = [video_hd_match(), video_default_match()]

    def _handle_media_url(self, media_type, post):
        try:
            if media_type == "photo":
                return post["photo-url"][0]["#text"]

            if media_type == "video":
                video_player = post["video-player"][1]["#text"]
                for regex_rule in self.regex_rules:
                    matched_url = regex_rule(video_player)
                    if matched_url is not None:
                        return matched_url
                else:
                    raise Exception
        except:
            raise TypeError("Unable to find the right url for downloading. "
                            "Please open a new issue on "
                            "https://github.com/dixudx/tumblr-crawler/"
                            "issues/new attached with below information:\n\n"
                            "%s" % post)

    def _download(self, media_type, media_url, target_folder):
        media_name = media_url.split("/")[-1].split("?")[0]  # maybe changed later
        if media_type == "video":
            if not media_name.startswith("tumblr"):
                media_name = "_".join([media_url.split("/")[-2], media_name])

            media_name += ".mp4"
            media_url = 'https://vt.tumblr.com/' + media_name  # will not changed

        file_path = os.path.join(target_folder, media_name)  # maybe changed later
        if not os.path.isfile(file_path):
            logger.info("Downloading %s", media_url)
            retry_times = 0
            while retry_times < RETRY:
                try:
                    resp = requests.get(media_url, stream=True, proxies=self.proxies, timeout=TIMEOUT)

                    # check headers and correct filename
                    content_disposition = resp.headers.get('Content-Disposition')
                    if content_disposition is not None:
                        match = re.search('filename="(.+)"', content_disposition)
                        if match is not None:
                            logger.info(f'filename changes from {media_name} to {match.group(1)}')
                            media_name = match.group(1)

                    _media_name_base, _media_name_ext = os.path.splitext(media_name)

                    content_type = resp.headers.get('Content-Type')
                    if content_type is not None:
                        match = re.search('image/(.+)', content_type)
                        if match is not None:
                            mime_type = match.group(1)
                            if mime_type not in map_mime2exts.keys():
                                raise KeyError(f'unknown mime type image/{mime_type}')
                            if _media_name_ext[1:] in map_mime2exts[mime_type]:
                                logger.info(f'ext {_media_name_ext} matches mime image/{mime_type}')
                            else:
                                logger.info(f'ext changes from {_media_name_ext} to .{map_mime2exts[mime_type][0]}')
                                media_name = f'{_media_name_base}.{map_mime2exts[mime_type][0]}'

                    file_path = os.path.join(target_folder, media_name)
                    # check headers and correct filename

                    if resp.status_code == 403:
                        retry_times = RETRY
                        logger.info("Access Denied when retrieve %s.\n", media_url)
                        raise Exception("Access Denied")
                    with open(file_path, 'wb') as fh:
                        fh.write(resp.content)
                    logger.info('')
                    break
                except:
                    # try again
                    pass
                retry_times += 1
            else:
                try:
                    os.remove(file_path)
                except OSError:
                    pass
                logger.info("Failed to retrieve %s from %s.\n", media_type, media_url)


class CrawlerScheduler(object):
    def __init__(self, sites, proxies=None):
        self.sites = sites
        self.proxies = proxies
        self.queue = Queue.Queue()
        self.scheduling()

    def scheduling(self):
        # create workers
        for _ in range(THREADS):
            worker = DownloadWorker(self.queue, proxies=self.proxies)
            # Setting daemon to True will let the main thread exit
            # even though the workers are blocking
            worker.daemon = True
            worker.start()

        for site in self.sites:
            self.download_media(site)

    def download_media(self, site):
        self.download_photos(site)
        # self.download_videos(site)

    def download_videos(self, site):
        self._download_media(site, "video", START)
        # wait for the queue to finish processing all the tasks from one
        # single site
        self.queue.join()
        logger.info("Finish Downloading All the videos from %s", site)

    def download_photos(self, site):
        self._download_media(site, "photo", START)
        # wait for the queue to finish processing all the tasks from one
        # single site
        self.queue.join()
        logger.info("Finish Downloading All the photos from %s", site)

    def _download_media(self, site, media_type, start):
        current_folder = os.getcwd()
        target_folder = os.path.join(current_folder, site)
        if not os.path.isdir(target_folder):
            os.mkdir(target_folder)

        base_url = "https://{0}.tumblr.com/api/read?type={1}&num={2}&start={3}"
        start = START
        while True:
            media_url = base_url.format(site, media_type, MEDIA_NUM, start)
            response = requests.get(media_url, proxies=self.proxies)
            if response.status_code == 404:
                logger.info("Site %s does not exist", site)
                break

            try:
                response_file = "{0}/{0}_{1}_{2}_{3}.response.xml".format(site, media_type, start, MEDIA_NUM)
                with open(response_file, "w", encoding='utf-8') as text_file:
                    x = xml.dom.minidom.parseString(response.text).toprettyxml()
                    text_file.write(x)

                data = xmltodict.parse(response.text)
                posts = data["tumblr"]["posts"]["post"]
                for post in posts:
                    # by default it is switched to false to generate less files,
                    # as anyway you can extract this from bulk xml files.
                    if EACH_POST_AS_SEPARATE_JSON:
                        post_json_file = "{0}/{0}_post_id_{1}.post.json".format(site, post['@id'])
                        with open(post_json_file, "w") as text_file:
                            text_file.write(json.dumps(post))

                    try:
                        # if post has photoset, walk into photoset for each photo
                        photoset = post["photoset"]["photo"]
                        for photo in photoset:
                            self.queue.put((media_type, photo, target_folder))
                    except:
                        # select the largest resolution
                        # usually in the first element
                        self.queue.put((media_type, post, target_folder))
                start += MEDIA_NUM
            except KeyError:
                break
            except UnicodeDecodeError:
                logger.info("Cannot decode response data from URL %s", media_url)
                continue
            except:
                logger.info("Unknown xml-vulnerabilities from URL %s", media_url)
                continue


def usage():
    print("1. Please create file sites.txt under this same directory.\n"
          "2. In sites.txt, you can specify tumblr sites separated by "
          "comma/space/tab/CR. Accept multiple lines of text\n"
          "3. Save the file and retry.\n\n"
          "Sample File Content:\nsite1,site2\n\n"
          "Or use command line options:\n\n"
          "Sample:\npython tumblr-photo-video-ripper.py site1,site2\n\n\n")
    print(u"未找到sites.txt文件，请创建.\n"
          u"请在文件中指定Tumblr站点名，并以 逗号/空格/tab/表格鍵/回车符 分割，支持多行.\n"
          u"保存文件并重试.\n\n"
          u"例子: site1,site2\n\n"
          u"或者直接使用命令行参数指定站点\n"
          u"例子: python tumblr-photo-video-ripper.py site1,site2")


def illegal_json():
    print("Illegal JSON format in file 'proxies.json'.\n"
          "Please refer to 'proxies_sample1.json' and 'proxies_sample2.json'.\n"
          "And go to http://jsonlint.com/ for validation.\n\n\n")
    print(u"文件proxies.json格式非法.\n" u"请参照示例文件'proxies_sample1.json'和'proxies_sample2.json'.\n" u"然后去 http://jsonlint.com/ 进行验证.")


def parse_sites(filename):
    with open(filename, "r") as f:
        raw_sites = f.read().rstrip().lstrip()

    raw_sites = raw_sites.replace("\t", ",") \
                         .replace("\r", ",") \
                         .replace("\n", ",") \
                         .replace(" ", ",")
    raw_sites = raw_sites.split(",")

    sites = list()
    for raw_site in raw_sites:
        site = raw_site.lstrip().rstrip()
        if site:
            sites.append(site)
    return sites


if __name__ == "__main__":
    cur_dir = os.path.dirname(os.path.realpath(__file__))
    sites = None

    proxies = None
    proxy_path = os.path.join(cur_dir, "proxies.json")
    if os.path.exists(proxy_path):
        with open(proxy_path, "r") as fj:
            try:
                proxies = json.load(fj)
                if proxies is not None and len(proxies) > 0:
                    logger.info("You are using proxies.\n%s", proxies)
            except:
                illegal_json()
                sys.exit(1)

    if len(sys.argv) < 2:
        # check the sites file
        filename = os.path.join(cur_dir, "sites.txt")
        if os.path.exists(filename):
            sites = parse_sites(filename)
        else:
            usage()
            sys.exit(1)
    else:
        sites = sys.argv[1].split(",")

    if len(sites) == 0 or sites[0] == "":
        usage()
        sys.exit(1)

    CrawlerScheduler(sites, proxies=proxies)
