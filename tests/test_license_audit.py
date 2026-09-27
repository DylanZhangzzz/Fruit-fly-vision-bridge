"""The release check must catch missing notices and unauthorized additions."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from scripts.audit_licenses import inspect


class LicenseBoundaryTests(unittest.TestCase):
    def test_changed_notice_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'notice.txt').write_text('changed',encoding='utf8')
            inventory={'preserved_files':[{'path':'notice.txt','sha256':hashlib.sha256(b'original').hexdigest()}],
                       'reviewed_binary_files':[]}
            self.assertTrue(any('changed: notice.txt' in x for x in inspect(root,['notice.txt'],inventory)))

    def test_unreviewed_notebook_and_weight_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            failures=inspect(Path(directory),['author.ipynb','best.pth','camera.png'],
                             {'preserved_files':[],'reviewed_binary_files':[]})
            for name in ['author.ipynb','best.pth','camera.png']:
                self.assertTrue(any(x.endswith(name) for x in failures),name)

    def test_missing_required_notices_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            failures=inspect(Path(directory),[],{'preserved_files':[],'reviewed_binary_files':[]})
            self.assertTrue(any('Missing publication notice: LICENSE'==x for x in failures))


if __name__=='__main__':unittest.main()
