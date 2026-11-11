"""File names and checksums from archive metadata are untrusted: the harvest cache path and the full-text
fetch's local folder and R2 keys never step outside their folder. (The internetarchive library's
File.download() had this bug, GHSA-wx3r-v6h7-frjp; the project never calls it, but builds its own
paths from the same metadata.)"""
from __future__ import annotations

import gzip
import json

import pytest

from archive_debugger.catalogue import fulltext
from archive_debugger.catalogue.net import HttpError
from archive_debugger.harvest import fetch


def test_content_ref_keeps_only_the_last_part_of_a_name():
    assert fetch.content_ref("0123abcd" * 4, "sub/x_djvu.txt") == f"ocr/01/{'0123abcd' * 4}__x_djvu.txt"


@pytest.mark.parametrize("md5,name", [
    ("../../etc", "x_djvu.txt"),
    ("ab/cd", "x_djvu.txt"),
    ("ab\\cd", "x_djvu.txt"),
    ("", "x_djvu.txt"),
    ("0123abcd", ".."),
    ("0123abcd", "sub/.."),
])
def test_content_ref_refuses_paths_that_leave_the_cache(md5, name):
    with pytest.raises(ValueError):
        fetch.content_ref(md5, name)


@pytest.mark.parametrize("value", ["../x", "a/../b", "/etc/x", "a\\b", "..", ".", "", "a//b"])
def test_safe_part_refuses_names_that_leave_the_folder(value):
    with pytest.raises(ValueError):
        fulltext.safe_part(value, "file name", folders=True)


def test_safe_part_allows_a_sub_folder_only_for_file_names():
    assert fulltext.safe_part("scans/x_djvu.txt", "file name", folders=True) == "scans/x_djvu.txt"
    with pytest.raises(ValueError):
        fulltext.safe_part("a/b", "identifier")


def _fake_get(files: dict, listed: list):
    """Serves the item's metadata (listing `listed`) and the downloads in `files`; 404 for the rest."""
    def get(url, refusals=None):
        if url.startswith("https://archive.org/metadata/"):
            return json.dumps({"files": [{"name": n} for n in listed]}).encode("utf-8")
        for name, body in files.items():
            if url.endswith("/" + name):
                return body
        raise HttpError(404, url)
    return get


def test_fetch_item_refuses_a_metadata_name_that_climbs_out():
    get = _fake_get({}, ["../../evil_hocr_searchtext.txt.gz"])
    with pytest.raises(ValueError):
        fulltext.fetch_item("someitem", get, refusals=None)


def test_fetch_item_refuses_a_djvu_name_that_climbs_out():
    get = _fake_get({}, ["..\\..\\evil_djvu.txt"])
    with pytest.raises(ValueError):
        fulltext.fetch_item("someitem", get, refusals=None)


def test_fetch_item_still_takes_ordinary_metadata_names():
    get = _fake_get({"other_djvu.txt": b"text"}, ["other_djvu.txt"])
    item = fulltext.fetch_item("someitem", get, refusals=None)
    assert item["kind"] == "djvu_txt"
    assert item["files"]["djvu_txt"][0] == "other_djvu.txt.gz"
    assert gzip.decompress(item["files"]["djvu_txt"][1]) == b"text"


def test_fetch_item_refuses_an_identifier_with_a_path():
    with pytest.raises(ValueError):
        fulltext.fetch_item("../x", _fake_get({}, []), refusals=None)
