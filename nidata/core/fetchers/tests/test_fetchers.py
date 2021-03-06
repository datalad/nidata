"""
Test the fetchers module
"""
# Author: Alexandre Abraham
# License: simplified BSD

import contextlib
import os
import shutil
import numpy as np
import zipfile
import tarfile
import gzip
from tempfile import mkdtemp, mkstemp

import nibabel
from nose import with_setup
from nose.tools import assert_true, assert_false, assert_equal, assert_raises

from nidata.core import fetchers
from nidata.core._utils import compat
from nidata.core._utils.testing import assert_raises_regex
from nidata.core._utils.compat import _basestring
from nidata.core.fetchers.tests import (mock_request, wrap_chunk_read_,
                                        FetchFilesMock)

currdir = os.path.dirname(os.path.abspath(__file__))
datadir = os.environ.get('NIDATA_PATH', os.path.join(currdir, 'data'))
tmpdir = None
url_request = None
file_mock = None


def get_datadir():
    global datadir
    print("datadir, " + datadir)
    return datadir


def get_tmpdir():
    global tmpdir
    print ("tmpdir, " + tmpdir)
    return tmpdir


def get_url_request():
    global url_request
    print ("url_request, " + url_request)
    return url_request


def get_file_mock():
    global file_mock
    print ("file_mock, " + str(file_mock))
    return file_mock


def setup_tmpdata():
    # create temporary dir
    global tmpdir
    tmpdir = mkdtemp()


def setup_mock():
    global url_request
    url_request = mock_request()
    # compat._urllib.request = url_request
    fetchers.http_fetcher._chunk_read_ = wrap_chunk_read_(fetchers.http_fetcher._chunk_read_)
    global file_mock
    file_mock = FetchFilesMock()
    fetchers.fetch_files = file_mock


def teardown_tmpdata():
    # remove temporary dir
    global tmpdir
    if tmpdir is not None:
        shutil.rmtree(tmpdir)


def testmd5_sum_file():
    # Create dummy temporary file
    out, f = mkstemp()
    os.write(out, b'abcfeg')
    os.close(out)
    assert_equal(fetchers.md5_sum_file(f), '18f32295c556b2a1a3a8e68fe1ad40f7')
    os.remove(f)


@with_setup(setup_tmpdata, teardown_tmpdata)
def testget_dataset_dir():
    # testing folder creation under different environments, enforcing
    # a custom clean install
    os.environ.pop('NIDATA_PATH', None)

    expected_base_dir = os.path.expanduser('~/nidata_path')
    data_dir = fetchers.get_dataset_dir('test', verbose=0)
    assert_equal(data_dir, os.path.join(expected_base_dir, 'test'))
    assert os.path.exists(data_dir)
    shutil.rmtree(data_dir)

    expected_base_dir = os.path.join(tmpdir, 'test_nidata_path')
    os.environ['NIDATA_PATH'] = expected_base_dir
    data_dir = fetchers.get_dataset_dir('test', verbose=0)
    assert_equal(data_dir, os.path.join(expected_base_dir, 'test'))
    assert os.path.exists(data_dir)
    shutil.rmtree(data_dir)

    no_write = os.path.join(tmpdir, 'no_write')
    os.makedirs(no_write)
    os.chmod(no_write, 0o400)

    # Verify exception is raised on read-only directories
    assert_raises_regex(OSError, 'Permission denied',
                        fetchers.get_dataset_dir, 'test', no_write,
                        verbose=0)

    # Verify exception for a path which exists and is a file
    test_file = os.path.join(tmpdir, 'some_file')
    with open(test_file, 'w') as out:
        out.write('abcfeg')
    assert_raises_regex(OSError, 'Not a directory',
                        fetchers.get_dataset_dir, 'test', test_file,
                        verbose=0)


def test_readmd5_sum_file():
    # Create dummy temporary file
    out, f = mkstemp()
    os.write(out, b'20861c8c3fe177da19a7e9539a5dbac  /tmp/test\n'
             b'70886dcabe7bf5c5a1c24ca24e4cbd94  test/some_image.nii')
    os.close(out)
    h = fetchers.readmd5_sum_file(f)
    assert_true('/tmp/test' in h)
    assert_false('/etc/test' in h)
    assert_equal(h['test/some_image.nii'], '70886dcabe7bf5c5a1c24ca24e4cbd94')
    assert_equal(h['/tmp/test'], '20861c8c3fe177da19a7e9539a5dbac')
    os.remove(f)


def test_tree():
    # Create a dummy directory tree
    parent = mkdtemp()

    open(os.path.join(parent, 'file1'), 'w').close()
    open(os.path.join(parent, 'file2'), 'w').close()
    dir1 = os.path.join(parent, 'dir1')
    dir11 = os.path.join(dir1, 'dir11')
    dir12 = os.path.join(dir1, 'dir12')
    dir2 = os.path.join(parent, 'dir2')
    os.mkdir(dir1)
    os.mkdir(dir11)
    os.mkdir(dir12)
    os.mkdir(dir2)
    open(os.path.join(dir1, 'file11'), 'w').close()
    open(os.path.join(dir1, 'file12'), 'w').close()
    open(os.path.join(dir11, 'file111'), 'w').close()
    open(os.path.join(dir2, 'file21'), 'w').close()

    tree_ = fetchers._tree(parent)

    # Check the tree
    #assert_equal(tree_[0]['dir1'][0]['dir11'][0], 'file111')
    #assert_equal(len(tree_[0]['dir1'][1]['dir12']), 0)
    #assert_equal(tree_[0]['dir1'][2], 'file11')
    #assert_equal(tree_[0]['dir1'][3], 'file12')
    #assert_equal(tree_[1]['dir2'][0], 'file21')
    #assert_equal(tree_[2], 'file1')
    #assert_equal(tree_[3], 'file2')
    assert_equal(tree_[0][1][0][1][0], os.path.join(dir11, 'file111'))
    assert_equal(len(tree_[0][1][1][1]), 0)
    assert_equal(tree_[0][1][2], os.path.join(dir1, 'file11'))
    assert_equal(tree_[0][1][3], os.path.join(dir1, 'file12'))
    assert_equal(tree_[1][1][0], os.path.join(dir2, 'file21'))
    assert_equal(tree_[2], os.path.join(parent, 'file1'))
    assert_equal(tree_[3], os.path.join(parent, 'file2'))

    # Clean
    shutil.rmtree(parent)


def test_movetree():
    # Create a dummy directory tree
    parent = mkdtemp()

    dir1 = os.path.join(parent, 'dir1')
    dir11 = os.path.join(dir1, 'dir11')
    dir12 = os.path.join(dir1, 'dir12')
    dir2 = os.path.join(parent, 'dir2')
    os.mkdir(dir1)
    os.mkdir(dir11)
    os.mkdir(dir12)
    os.mkdir(dir2)
    os.mkdir(os.path.join(dir2, 'dir12'))
    open(os.path.join(dir1, 'file11'), 'w').close()
    open(os.path.join(dir1, 'file12'), 'w').close()
    open(os.path.join(dir11, 'file111'), 'w').close()
    open(os.path.join(dir12, 'file121'), 'w').close()
    open(os.path.join(dir2, 'file21'), 'w').close()

    fetchers.movetree(dir1, dir2)

    assert_false(os.path.exists(dir11))
    assert_false(os.path.exists(dir12))
    assert_false(os.path.exists(os.path.join(dir1, 'file11')))
    assert_false(os.path.exists(os.path.join(dir1, 'file12')))
    assert_false(os.path.exists(os.path.join(dir11, 'file111')))
    assert_false(os.path.exists(os.path.join(dir12, 'file121')))
    dir11 = os.path.join(dir2, 'dir11')
    dir12 = os.path.join(dir2, 'dir12')

    assert_true(os.path.exists(dir11))
    assert_true(os.path.exists(dir12))
    assert_true(os.path.exists(os.path.join(dir2, 'file11')))
    assert_true(os.path.exists(os.path.join(dir2, 'file12')))
    assert_true(os.path.exists(os.path.join(dir11, 'file111')))
    assert_true(os.path.exists(os.path.join(dir12, 'file121')))


def test_filter_columns():
    # Create fake recarray
    value1 = np.arange(500)
    strings = np.asarray(['a', 'b', 'c'])
    value2 = strings[value1 % 3]

    values = np.asarray(list(zip(value1, value2)),
                        dtype=[('INT', int), ('STR', 'S1')])

    f = fetchers.filter_columns(values, {'INT': (23, 46)})
    assert_equal(np.sum(f), 24)

    f = fetchers.filter_columns(values, {'INT': [0, 9, (12, 24)]})
    assert_equal(np.sum(f), 15)

    value1 = value1 % 2
    values = np.asarray(list(zip(value1, value2)),
                        dtype=[('INT', int), ('STR', b'S1')])

    # No filter
    f = fetchers.filter_columns(values, [])
    assert_equal(np.sum(f), 500)

    f = fetchers.filter_columns(values, {'STR': b'b'})
    assert_equal(np.sum(f), 167)

    f = fetchers.filter_columns(values, {'INT': 1, 'STR': b'b'})
    assert_equal(np.sum(f), 84)

    f = fetchers.filter_columns(values, {'INT': 1, 'STR': b'b'},
            combination='or')
    assert_equal(np.sum(f), 333)


def test_uncompress():
    # Create dummy file
    fd, temp = mkstemp()
    os.close(fd)
    # Create a zipfile
    dtemp = mkdtemp()
    ztemp = os.path.join(dtemp, 'test.zip')
    with contextlib.closing(zipfile.ZipFile(ztemp, 'w')) as testzip:
        testzip.write(temp)
    fetchers._uncompress_file(ztemp, verbose=0)
    assert(os.path.exists(os.path.join(dtemp, temp)))
    shutil.rmtree(dtemp)

    dtemp = mkdtemp()
    ztemp = os.path.join(dtemp, 'test.tar')
    with contextlib.closing(tarfile.open(ztemp, 'w')) as tar:
        tar.add(temp)
    fetchers._uncompress_file(ztemp, verbose=0)
    assert(os.path.exists(os.path.join(dtemp, temp)))
    shutil.rmtree(dtemp)

    dtemp = mkdtemp()
    ztemp = os.path.join(dtemp, 'test.gz')
    f = gzip.open(ztemp, 'wb')
    f.close()
    fetchers._uncompress_file(ztemp, verbose=0)
    assert(os.path.exists(os.path.join(dtemp, temp)))
    shutil.rmtree(dtemp)

    os.remove(temp)
