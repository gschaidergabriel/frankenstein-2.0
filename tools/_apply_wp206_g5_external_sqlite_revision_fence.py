#!/usr/bin/env python3
"""One-shot exact-source patch applicator for the active WP206 G5 branch.

This helper is intentionally removed after it applies the bounded source change.  It
fails closed unless both exact predecessor snippets occur exactly once.
"""
from pathlib import Path

PATH = Path("src/frankenstein2/persistent_agency_kernel.py")
text = PATH.read_text(encoding="utf-8")

old_init = '''        self.connection.execute("PRAGMA foreign_keys=ON")
'''
new_init = '''        self.connection.execute("PRAGMA foreign_keys=ON")
        data_version_row = self.connection.execute(
            "PRAGMA main.data_version"
        ).fetchone()
        if (
            data_version_row is None
            or len(data_version_row) != 1
            or type(data_version_row[0]) is not int
        ):
            raise PersistentAgencyError("UNIFIEDDB_DATA_VERSION_UNAVAILABLE")
        # Connection-local observation only.  SQLite advances data_version when a
        # *different* connection commits.  Never persist or compare it across reopen.
        self.sqlite_data_version_baseline = int(data_version_row[0])
'''

old_guard = '''        if (st.st_dev, st.st_ino) != (self.db_device, self.db_inode):
            raise PersistentAgencyError("UNIFIEDDB_FILE_IDENTITY_DRIFT")
'''
new_guard = '''        if (st.st_dev, st.st_ino) != (self.db_device, self.db_inode):
            raise PersistentAgencyError("UNIFIEDDB_FILE_IDENTITY_DRIFT")
        data_version_row = self.connection.execute(
            "PRAGMA main.data_version"
        ).fetchone()
        if (
            data_version_row is None
            or len(data_version_row) != 1
            or type(data_version_row[0]) is not int
        ):
            raise PersistentAgencyError("UNIFIEDDB_DATA_VERSION_UNAVAILABLE")
        if int(data_version_row[0]) != self.sqlite_data_version_baseline:
            raise PersistentAgencyError("UNIFIEDDB_EXTERNAL_SQLITE_REVISION_DRIFT")
'''

if text.count(old_init) != 1:
    raise SystemExit("expected exact foreign_keys predecessor snippet once")
if text.count(old_guard) != 1:
    raise SystemExit("expected exact file-identity predecessor snippet once")

text = text.replace(old_init, new_init, 1).replace(old_guard, new_guard, 1)
PATH.write_text(text, encoding="utf-8")
print("APPLIED_WP206_G5_EXTERNAL_SQLITE_REVISION_FENCE")
