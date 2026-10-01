import sqlite3

import pytest

from alr_tw.providers import data_pack
from test_v013_rc_workflows import make_pack


@pytest.mark.parametrize("failure", [None, "deserialize", "schema", "columns", "unexpected"])
def test_deserialized_connection_is_closed_on_all_exit_paths(tmp_path, monkeypatch, failure):
    args = make_pack(tmp_path)
    opened = []
    original = sqlite3.connect

    class ObservedConnection(sqlite3.Connection):
        closed = False

        def deserialize(self, image):
            if failure == "deserialize":
                raise sqlite3.DatabaseError("synthetic deserialize failure")
            return super().deserialize(image)

        def execute(self, sql, *args, **kwargs):
            if "SELECT type,name" in sql:
                if failure == "schema":
                    return super().execute("SELECT 'table', 'other'")
                if failure == "unexpected":
                    raise RuntimeError("synthetic unexpected failure")
            if "SELECT jid,title" in sql and failure == "columns":
                raise sqlite3.OperationalError("synthetic missing column")
            return super().execute(sql, *args, **kwargs)

        def close(self):
            self.closed = True
            super().close()

    def connect(*args, **kwargs):
        connection = original(*args, **kwargs, factory=ObservedConnection)
        opened.append(connection)
        return connection

    monkeypatch.setattr(data_pack.sqlite3, "connect", connect)
    if failure:
        with pytest.raises((ValueError, RuntimeError)):
            data_pack.DataPackJudgmentProvider(*args)
    else:
        data_pack.DataPackJudgmentProvider(*args)
    assert len(opened) == 1 and opened[0].closed
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")
