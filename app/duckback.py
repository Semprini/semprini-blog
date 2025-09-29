import duckdb
from settings.dev import DATABASES

con = duckdb.connect()

con.install_extension("postgres_scanner")
con.load_extension("postgres_scanner")
# con.sql("SET memory_limit = '20GB';")
# con.sql("SET threads TO 3;")
# con.sql("SET enable_progress_bar = true;")
contxt = f"ATTACH 'dbname={DATABASES['prod']['NAME']} user={DATABASES['prod']['USER']} host={DATABASES['prod']['HOST']} password={DATABASES['prod']['PASSWORD']}' AS source (TYPE POSTGRES, READ_ONLY);"
con.sql(contxt)
con.sql("USE source;")
foo = con.sql("SELECT * from pg_class;").fetchall()
print(foo)
# all_tables = con.sql("SHOW ALL tables;").fetchall()
# source_tables = all_tables['name'].to_list()
# print(all_tables)
# con.sql(f"ATTACH 'dbname={DATABASES['default']['NAME']} user={DATABASES['default']['USER']} host={DATABASES['default']['HOST']} password={DATABASES['default']['PASSWORD']}' AS dest (TYPE POSTGRES, READ_ONLY);")
# con.sql("USE dest;")
# all_tables = con.sql("SHOW ALL tables;").fetchdf()
# dest_tables = all_tables['name'].to_list()

# for table in source_tables:
#     if table not in dest_tables:
#         print(f"Not copying table {table} from source to destination as it does not exist...")
#     else:
#         con.execute(f"COPY source.public.{table} TO dest.public.{table};")
#         print(f"Table {table} copied")

con.close()
