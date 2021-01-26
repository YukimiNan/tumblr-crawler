import logging
import os
import sys
import time

from . import constant, fs


def setLogger(name=None,
              level=logging.INFO,
              stream=sys.stdout,
              dir_=None,
              filenamefmt=f'{constant.datefmt}.log',
              logfmt='[%(asctime)s] %(pathname)s:%(lineno)d: %(levelname)s: %(message)s',
              datetimefmt=constant.datetimefmt):
    logger = logging.getLogger(name=name)
    logger.setLevel(level)
    while logger.handlers:
        logger.removeHandler(logger.handlers[-1])

    formatter = logging.Formatter(fmt=logfmt, datefmt=datetimefmt)

    if stream:
        stream_handler = logging.StreamHandler(stream=stream)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    if dir_:
        fs.makedirs(dir_)
        filename = time.strftime(filenamefmt)
        path = os.path.join(dir_, filename)
        file_handler = logging.FileHandler(path, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
