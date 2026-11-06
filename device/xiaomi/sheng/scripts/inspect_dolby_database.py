#!/usr/bin/env python3
"""Read a copied DMS database without changing native or application settings."""
import sqlite3
import sys
from pathlib import Path

database = Path(sys.argv[1]).resolve()
connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
for (name,) in connection.execute("select name from sqlite_master where type='table'"):
    columns = [row[1] for row in connection.execute('pragma table_info("' + name + '")')]
    print('TABLE', name, columns)
    selected = [column for column in columns if column in
                ('_id', 'name', 'custom_name', 'endpoint', 'tuning_device', 'tuning',
                 'device', 'port', 'output_channels', 'output_mix_matrix')]
    if selected:
        print(list(connection.execute('select ' + ','.join('"' + c + '"' for c in selected)
                                      + ' from "' + name + '" limit 16')))
connection.close()
