from os.path import abspath, dirname, join

from ykmlib.log import setLogger

logger = setLogger(name='tumblr-crawler', dir_=abspath(join(dirname(__file__), 'log')))

map_mime2exts = {
    'bmp': ['bmp'],
    'gif': ['gif'],
    'vnd.microsoft.icon': ['ico'],
    'jpeg': ['jpg', 'jpeg'],
    'png': ['png'],
    'svg+xml': ['svg'],
    'tiff': ['tif', 'tiff'],
    'webp': ['webp']
}
