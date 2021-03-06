#!/usr/bin/env python3

import hashlib
import json
import math
import os
from datetime import timedelta
from flask import Flask
from lib.tinytag import TinyTag

def get_books(root_path, cache=None):
    '''
    Discover audiobooks under :root_path: and populate books object

    :cache: existing JSON cache, used to determine which content is new
            (existing content is not re-hashed)
    '''
    if not os.path.exists(root_path):
        raise ValueError('root path does not exist: %s' % root_path)

    # '/home/user/audiobooks/book': d815c7a3cc11f08558b4d91ca93de023
    existing_books = {}
    if cache:
        for k, _ in cache.items():
            existing_books[cache[k]['path']] = k

    book_dirs = list()
    for root, dirs, _ in os.walk(root_path):
        for d in dirs:
            book_dirs.append(os.path.join(root, d))

    books = dict()
    for book_path in book_dirs:
        # if already cached, populate books with existing k/v
        if book_path in existing_books:
            _hash = existing_books[book_path]
            books[_hash] = cache[_hash]
            continue
        book = is_book(book_path)
        if book:
            books[book[0]] = book[1]

    return books

def is_book(book_path):
    # book attributes to be populated
    book = {
        'author':       None,
        'duration':     0,
        'duration_str': None,
        'files':        dict(),
        'path':         book_path,
        'size_bytes':   0,
        'size_str':     None,
        'title':        None
    }

    # hash of each file in directory w/ MP3 extension
    folder_hash = hashlib.md5()

    # a book_path is only a book if it contains at least one MP3
    is_book = False
    for f in os.listdir(book_path):
        file_path = os.path.join(book_path, f)
        if not os.path.isfile(file_path) or not f.endswith('.mp3'):
            continue
        tag = TinyTag.get(file_path)
        if not tag.duration:
            continue

        # previous conditions met, we're a book! :D
        is_book = True
        print('[+] processing: %s' % book_path)

        # update collective hash of folder with MD5 of current file
        BLOCK = 1024
        file_hash = hashlib.md5()
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(BLOCK)
                if not data:
                    break
                folder_hash.update(data)
                file_hash.update(data)

        # per-MP3 atributes, some values are populated conditionally
        mp3 = {
            'album':        None,
            'author':       None,
            'duration':     tag.duration,
            'duration_str': None,
            'filename':     os.path.split(file_path)[1],
            'path':         file_path,
            'size_bytes':   None,
            'title':        None,
            'track':        None
        }

        mp3['album']  = validate(tag.album, os.path.split(book_path)[1])
        mp3['author'] = validate(tag.artist, 'Unknown')
        mp3['duration'] = tag.duration

        # 1 day, 10:59:58
        duration_str = str(timedelta(seconds=mp3['duration']))
        mp3['duration_str'] = duration_str.split('.')[0]

        mp3['title']  = validate(tag.title, os.path.split(file_path)[1])
        mp3['track'] = tag.track
        mp3['size_bytes'] = tag.filesize

        # we assume author and album attributes are unchanged between MP3s
        book['author'] = mp3['author']
        book['title'] = mp3['album']

        # increment book total size/duration
        book['duration'] += tag.duration
        book['size_bytes'] += tag.filesize

        # hexdigest: MP3 dict
        book['files'][file_hash.hexdigest()] = mp3

    # if we're a book, store formatted book size and duration
    if is_book:
        folder_hash = folder_hash.hexdigest()
        total_size = book['size_bytes']
        try:
            _i = int(math.floor(math.log(total_size, 1024)))
            _p = math.pow(1024, _i)
            _s = round(total_size / _p, 2)
        except:
            _i = 1
            _s = 0

        # e.g. 1.48 GB
        SIZES = ('B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB')
        book['size_str'] = '%s %s' % (str(_s), SIZES[_i])

        # e.g. 2 days, 5:47:47
        duration_str = str(timedelta(seconds=book['duration']))
        book['duration_str'] = duration_str.split('.')[0]
        return (folder_hash, book)

    return False

def write_cache(books, json_path):
    '''
    Dump contents of :books: to :json_path:
    '''
    cache_path = os.path.dirname(json_path)
    if not os.path.exists(cache_path):
        os.mkdir(cache_path)
    with open(json_path, 'w') as f:
        json.dump(books, f, indent=4)

def read_cache(json_path):
    with open(json_path, 'r') as cache:
        books = json.load(cache)

    return books

def validate(v, b):
    '''
    Returns :v: if v and v.isspace(), otherwise b

    :v: preferred value
    :b: backup value
    '''
    if v and not v.isspace():
        return v
    else:
        return b

if __name__ == '__main__':
    ABS_PATH = os.path.dirname(os.path.abspath(__file__))
    CACHE_PATH = os.path.join(ABS_PATH, 'cache')
    JSON_PATH = os.path.join(CACHE_PATH, 'audiobooks.json')

    # use Flask's config parser, configparser would be hacky
    APP = Flask(__name__)
    APP.config.from_pyfile(os.path.join(ABS_PATH, 'app.cfg'))

    if os.path.exists(JSON_PATH):
        cache = read_cache(JSON_PATH)
        BOOKS = get_books(APP.config['ROOT_PATH'], cache)
    else:
        BOOKS = get_books(APP.config['ROOT_PATH'])

    write_cache(BOOKS, JSON_PATH)
