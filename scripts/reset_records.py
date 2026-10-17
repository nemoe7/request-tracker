"""Clear the records in one database and keep the accounts.

    python scripts/reset_records.py /data/pwedepa.db

The path is the database file. The script prints one count for each table it
clears, so an operator sees what left the file.
"""

import sys

from pwedepa.data import db as data_db
from pwedepa.data.reset import reset


def main(path: str) -> None:
  connection = data_db.connect(path)
  try:
    counts = reset(connection)
  finally:
    connection.close()
  for table, count in counts.items():
    print(f"{table}: {count} removed")
  print("the accounts stay")


if __name__ == "__main__":
  main(sys.argv[1] if len(sys.argv) > 1 else "pwedepa.db")
