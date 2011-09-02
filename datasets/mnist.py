"""
MNIST hand-drawn digit dataset.

Data available from and described at:
http://yann.lecun.com/exdb/mnist/

"""

import os
import gzip
import logging
import urllib
import shutil

import numpy as np

from data_home import get_data_home

logger = logging.getLogger(__name__)

URLS = dict(
    train_images="http://yann.lecun.com/exdb/mnist/train-images-idx3-ubyte.gz",
    train_labels="http://yann.lecun.com/exdb/mnist/train-labels-idx1-ubyte.gz",
    test_images="http://yann.lecun.com/exdb/mnist/t10k-images-idx3-ubyte.gz",
    test_labels="http://yann.lecun.com/exdb/mnist/t10k-labels-idx1-ubyte.gz",
    )

FILE_SIZES_PRETTY = dict(
    train_images='9.5M',
    train_labels='29K',
    test_images='1.6M',
    test_labels='4.5K',
    )

def _read_int32(f):
    """unpack a 4-byte integer from the current position in file f"""
    s = f.read(4)
    s_array = np.fromstring(s, dtype='int32')
    a = s_array.item()
    return s_array.item()


def _reverse_bytes_int32(i):
    a = np.asarray(i, 'int32')
    b = np.frombuffer(a.data, dtype='int8')
    assert b.shape == (4,)
    c = b[[3, 2, 1, 0]]
    d = np.frombuffer(c.data, dtype='int32')
    assert d.shape == (1,), d.shape
    return d.item()


def _read_header(f, debug=False, fromgzip=None):
    """
    :param f: an open file handle.
    :type f: a file or gzip.GzipFile object

    :param fromgzip: bool or None
    :type fromgzip: if None determine the type of file handle.

    :returns: data type, element size, rank, shape, size
    """
    if fromgzip is None:
        fromgzip = isinstance(f, gzip.GzipFile)

    magic = _read_int32(f)
    if magic in (2049, 2051):
        logger.info('Reading on big-endian machine.')
        endian = 'big'
        next_int32 = lambda : _read_int32(f)
    elif _reverse_bytes_int32(magic) in (2049, 2051):
        logger.info('Reading on little-endian machine.')
        magic = _reverse_bytes_int32(magic)
        endian = 'little'
        next_int32 = lambda : _reverse_bytes_int32(_read_int32(f))
    else:
        raise IOError('MNIST data file appears to be corrupt')

    if magic == 2049:
        logger.info('reading MNIST labels file')
        n_elements = next_int32()
        return (n_elements,)
    elif magic == 2051:
        logger.info('reading MNIST images file')
        n_elements = next_int32()
        n_rows = next_int32()
        n_cols = next_int32()
        return (n_elements, n_rows, n_cols)
    else:
        assert 0, magic


def read(f, debug=False):
    """Load all or part of file 'f' into a numpy ndarray

    :param f: file from which to read
    :type f: file-like object. Can be a gzip open file.

    """
    shape = _read_header(f, debug)
    data = f.read(np.prod(shape))
    return np.fromstring(data, dtype='uint8').reshape(shape)


class MNIST(object):
    """
    meta[i] is dict with keys:
        id: int identifier of this example
        label: int in range(10)
        split: 'train' or 'test'

    meta_const is dict with keys:
        image:
            shape: 28, 28
            dtype: 'uint8'

    """
    DOWNLOAD_IF_MISSING = True
    def __init__(self):
        self.meta_const = dict(
                image=dict(
                    shape=(28, 28),
                    dtype='uint8'))
        self.descr = dict(
                n_classes=10)

    def __get_meta(self):
        try:
            return self._meta
        except AttributeError:
            self.fetch(download_if_missing=self.DOWNLOAD_IF_MISSING)
            self._meta = self.build_meta()
            return self._meta
    meta = property(__get_meta)

    def home(self, *names):
        return os.path.join(get_data_home(), 'mnist', *names)

    def fetch(self, download_if_missing):
        if download_if_missing:
            if not os.path.isdir(self.home()):
                os.makedirs(self.home())

        for role, url in URLS.items():
            dest = self.home(os.path.basename(url))
            try:
                gzip.open(dest, 'rb').close()
            except IOError:
                if download_if_missing:
                    logger.warn("Downloading %s %s: %s => %s" % (
                        FILE_SIZES_PRETTY[role], role, url, dest))
                    downloader = urllib.urlopen(url)
                    data = downloader.read()
                    tmp = open(dest, 'wb')
                    tmp.write(data)
                    tmp.close()
                    gzip.open(dest, 'rb').close()
                else:
                    raise

    def erase(self):
        logger.info('recursively erasing %s' % self.home())
        if os.path.isdir(self.home()):
            shutil.rmtree(self.home())

    def build_meta(self):
        try:
            arrays = self.arrays
        except AttributeError:
            arrays = {}
            for role, url in URLS.items():
                dest = self.home(os.path.basename(url))
                logger.info('opening %s' % dest)
                arrays[role] = read(gzip.open(dest, 'rb'), debug=True)
            # cache the arrays in memory, the aren't that big (12M total)
            MNIST.arrays = arrays
        assert arrays['train_images'].shape == (60000, 28, 28)
        assert arrays['test_images'].shape == (10000, 28, 28)
        assert arrays['train_labels'].shape == (60000,)
        assert arrays['test_labels'].shape == (10000,)
        assert len(arrays['train_images']) == len(arrays['train_labels'])
        assert len(arrays['test_images']) == len(arrays['test_labels'])
        meta = [dict(id=i, split='train', label=l)
                for i,l in enumerate(arrays['train_labels'])]
        meta.extend([dict(id=i + j + 1, split='test', label=l)
                for j, l in enumerate(arrays['test_labels'])])
        assert i + j + 2 == 70000, (i, j)
        return meta

    def classification_task(self):
        Y = [m['label'] for m in self.meta]
        X = self.latent_structure_task()
        return X, np.asarray(Y)

    def latent_structure_task(self):
        self.meta  # read arrays
        X = np.empty((70000, 28**2), dtype='float32')
        self.arrays['train_images'].reshape((60000, 28**2))
        X[:60000] = self.arrays['train_images'].reshape((60000, 28**2))
        X[60000:] = self.arrays['test_images'].reshape((10000, 28**2))
        X /= 255   # put features onto (0.0, 1.0) range
        return X

    @classmethod
    def main_fetch(cls):
        return cls().fetch(download_if_missing=True)

    @classmethod
    def main_erase(cls):
        return cls().erase()

    @classmethod
    def main_show(cls):
        from utils.glviewer import glumpy_viewer, command, glumpy
        self = cls()
        Y = [m['label'] for m in self.meta]
        glumpy_viewer(
                img_array=cls.arrays['train_images'],
                arrays_to_print=[Y],
                cmap=glumpy.colormap.Grey)


def main_fetch():
    MNIST.main_fetch()


def main_show():
    MNIST.main_show()


def main_erase():
    logger.setLevel(logging.INFO)
    MNIST.main_erase()
