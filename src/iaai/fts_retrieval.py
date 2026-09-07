"""Rebuildable snapshot-local FTS5 projection; unrelated documents cannot affect IDF."""

import re
import sqlite3

from iaai.errors import IAAIError


class FTS5Retriever:
    def runtime_version(self):
        return f"sqlite-{sqlite3.sqlite_version}/fts5-unicode61-bm25-v1"

    def available(self):
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
            return True
        except sqlite3.OperationalError:
            return False
        finally:
            connection.close()

    def search(self, chunks, query, limit):
        if not self.available():
            raise IAAIError(
                "FTS5_UNAVAILABLE", "FTS5 недоступен; корпус сохранён, поиск невозможен."
            )
        tokens = re.findall(r"[^\W_]+", query, re.UNICODE)
        if not tokens:
            raise IAAIError("EMPTY_QUERY", "Введите слова для поиска.")
        match = " OR ".join('"' + token + '"' for token in tokens)
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("CREATE VIRTUAL TABLE search USING fts5(text, tokenize='unicode61')")
            connection.executemany(
                "INSERT INTO search(rowid,text) VALUES (?,?)",
                [(i + 1, chunk.text) for i, chunk in enumerate(chunks)],
            )
            rows = connection.execute(
                "SELECT rowid, bm25(search) AS score FROM search WHERE search MATCH ? "
                "ORDER BY score ASC, rowid ASC LIMIT ?",
                (match, limit),
            ).fetchall()
            return [
                {"rank": rank, "score": score, "chunk": chunks[rowid - 1].model_dump(mode="json")}
                for rank, (rowid, score) in enumerate(rows, 1)
            ]
        finally:
            connection.close()
