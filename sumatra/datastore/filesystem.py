"""
Datastore based on files written to and retrieved from a local filesystem.
"""

import os
import datetime
import shutil
import logging
import mimetypes
from subprocess import Popen
import warnings
from ..compatibility import string_type
from .base import DataStore, DataKey, DataItem, IGNORE_DIGEST


class DataFile(DataItem):
    """A file-like object, that represents a file in a local filesystem."""
    # current implementation just for real files
    
    def __init__(self, path, store):
        self.path = path
        self.full_path = os.path.join(store.root, path)
        if os.path.exists(self.full_path):
            stats = os.stat(self.full_path)
            self.size = stats.st_size
        else:
            raise IOError("File %s does not exist" % self.full_path)
            #self.size = None
        self.name = os.path.basename(self.full_path)
        self.extension = os.path.splitext(self.full_path)
        self.mimetype, self.encoding = mimetypes.guess_type(self.full_path)
    
    def get_content(self, max_length=None):
        f = open(self.full_path, 'rb')
        if max_length:
            content = f.read(max_length)
        else:
            content = f.read()
        f.close()
        return content
    content = property(fget=get_content)
    
    @property
    def sorted_content(self):
        sorted_path = "%s,sorted" % self.full_path
        if not os.path.exists(sorted_path):
            cmd = "sort %s > %s" % (self.full_path, sorted_path)
            job = Popen(cmd, shell=True)
            job.wait()
        f = open(sorted_path, 'rb')
        content = f.read()
        f.close()
        if len(content) != self.size: # sort adds a \n if the file does not end with one
            assert len(content) == self.size + 1
            content = content[:-1]
        return content
    
    # should probably override save_copy() from base class,
    # as a filesystem copy will be much faster
    

class FileSystemDataStore(DataStore):
    """
    Represents a locally-mounted filesystem. The root of the data store will
    generally be a subdirectory of the real filesystem.
    """
    data_item_class = DataFile
    
    def __init__(self, root):
        self.root = os.path.abspath(root or "./Data")

    def __str__(self):
        return self.root
    
    def __getstate__(self):
        return {'root': self.root}
    
    def __setstate__(self, state):
        self.__init__(**state)
    
    def __get_root(self):
        return self._root
    def __set_root(self, value):
        if not isinstance(value, string_type):
            raise TypeError("root must be a string")
        self._root = value
        if not os.path.exists(self._root):
            try:
                os.makedirs(self._root)
            except OSError:
                pass  # should perhaps emit warning
    root = property(fget=__get_root, fset=__set_root)
    
    def _find_new_data_files(self, timestamp, ignoredirs=[".smt", ".hg", ".svn", ".git", ".bzr"]):
        """Finds newly created/changed files in dataroot."""
        # The timestamp-based approach creates problems when running several
        # experiments at once, since datafiles created by other experiments may
        # be mixed in with this one.
        # For this reason, concurrently running computations should each use
        # their own datastore, each with a different root.
        timestamp = timestamp.replace(microsecond=0) # Round down to the nearest second
        # Find and add new data files
        length_dataroot = len(self.root) + len(os.path.sep)
        new_files = []
        for root, dirs, files in os.walk(self.root):
            for igdir in ignoredirs:
                if igdir in dirs:
                    dirs.remove(igdir)
            for file in files:
                full_path = os.path.join(root, file)
                relative_path = os.path.join(root[length_dataroot:],file)
                last_modified = datetime.datetime.fromtimestamp(os.stat(full_path).st_mtime)
                if  last_modified >= timestamp:
                    new_files.append(relative_path)
        return new_files
    
    def find_new_data(self, timestamp):
        """Finds newly created/changed data items"""
        return [DataFile(path, self).generate_key()
                for path in self._find_new_data_files(timestamp)]
    
    def get_data_item(self, key):
        """
        Return the file that matches the given key.
        """
        try:
            df = self.data_item_class(key.path, self)
        except IOError:
            raise KeyError("File %s does not exist." % key.path)
        if key.digest != IGNORE_DIGEST and df.digest != key.digest:
            raise KeyError("Digests do not match.") # add info about file sizes?
        return df
        
    def delete(self, *keys):
        """
        Delete the files corresponding to the given keys.
        """
        for key in keys:
            try:
                data_item = self.get_data_item(key)
            except KeyError:
                warnings.warn("Tried to delete %s, but it did not exist." % key)
            else:
                os.remove(data_item.full_path)

    def contains_path(self, path):
        return os.path.isfile(os.path.join(self.root, path))
