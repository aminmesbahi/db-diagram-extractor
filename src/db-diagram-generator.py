import configparser
import psycopg2
import os

def fetch_data_from_db(conn, schema='public', excluded_tables=None):
    excluded_tables = excluded_tables or []
    cursor = conn.cursor()

    cursor.execute(f"SELECT tablename FROM pg_tables WHERE schemaname = '{schema}' ORDER BY tablename;")
    tables = [table for table in cursor.fetchall() if table[0] not in excluded_tables]


    columns = {}
    foreign_keys = []

    for table in tables:
        cursor.execute(f"""
            SELECT
                a.attname as column_name,
                format_type(a.atttypid, a.atttypmod) as data_type,
                a.attnotnull,
                CASE
                    WHEN a.attnum = ANY(i.indkey) THEN 'PK'
                    ELSE ''
                END as column_key
            FROM
                pg_attribute a
                LEFT JOIN pg_index i ON a.attrelid = i.indrelid AND i.indisprimary
            WHERE
                a.attrelid = '{schema}."{table[0]}"'::regclass
                AND a.attnum > 0
                AND NOT a.attisdropped
            ORDER BY
                (CASE WHEN a.attnum = ANY(i.indkey) THEN 'PK' ELSE '' END) DESC,
                a.attname;
        """)
        columns[table[0]] = cursor.fetchall()

        cursor.execute(f"""
            SELECT
                conname AS constraint_name,
                conrelid::regclass::text AS table_name,
                a.attname AS column_name,
                a.attnotnull,
                confrelid::regclass::text AS referenced_table,
                af.attname AS referenced_column
            FROM
                pg_attribute AS a
            JOIN
                pg_constraint AS con ON a.attnum = ANY(con.conkey)
            JOIN
                pg_attribute AS af ON af.attnum = ANY(con.confkey) AND af.attrelid = con.confrelid
            WHERE
                con.contype = 'f' AND a.attrelid = con.conrelid AND con.connamespace = '{schema}'::regnamespace
            ORDER BY a.attname;
        """)
        foreign_keys.extend(cursor.fetchall())

    return tables, columns, foreign_keys

def to_plantuml(schema, tables, columns, foreign_keys):
    output = "@startuml\n\n"
    output += '''
skinparam class {
    BackgroundColor #f8f9fa
    BorderColor #0d6efd
    FontColor #212529
    FontName Arial
    FontSize 14
    AttributeFontColor #212529
    AttributeFontSize 14
    AttributeFontName Arial
    StereotypeFontColor #6c757d
}

skinparam package {
    BackgroundColor #e9ecef
    BorderColor #0d6efd
}

skinparam arrow {
    Color #0d6efd
    FontColor #212529
    FontName Arial
    FontSize 14
}

!define BS5FontColor #0d6efd
!define BS5SecondaryColor #6c757d
!define BS5SuccessColor #198754
!define BS5InfoColor #0dcaf0
!define BS5WarningColor #ffc107
!define BS5DangerColor #dc3545
!define BS5LightColor #f8f9fa
!define BS5DarkColor #212529
\n\n'''

    fk_columns = {(fk[1].split('"')[1], fk[2]) for fk in foreign_keys}

    for table in tables:
        table_name = table[0]
        output += f'entity "{table_name}" as {table_name.lower()} {{\n'
        for column in columns[table_name]:
            column_name, data_type, attnotnull, column_key = column
            nullable_str = "not null" if attnotnull else "null"
            
            column_indicator = 'FK' if (table_name, column_name) in fk_columns else ''
            column_indicator = 'PK' if column_key == 'PK' else column_indicator

            column_detail = f'  {column_name} : {data_type} {nullable_str} {column_indicator}'
            output += f'{column_detail}\n'
        output += "}\n"

    seen_relationships = set()
    for fk in foreign_keys:
        from_table = fk[1].split('"')[1].lower()
        to_table = fk[4].split('"')[1].lower()
        is_nullable = fk[3] == 'NULL'
        is_unique = False
        relationship_type = determine_relationship_type(is_nullable, is_unique)
        relationship = (from_table, to_table, relationship_type)

        if relationship not in seen_relationships:
            output += f'{from_table} {relationship_type} {to_table}\n'
            seen_relationships.add(relationship)

    output += "@enduml"
    return output

def determine_relationship_type(is_nullable, is_unique):
    if is_nullable:
        if is_unique:
            return "|o--"  # Zero or One
        else:
            return "}o--"  # Zero or Many
    else:
        if is_unique:
            return "||--"  # Exactly One
        else:
            return "}|--"  # One or Many

def main():

    config = configparser.ConfigParser()
    config_file = 'config.ini'
    exclude_file = 'exclude.ini'

    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    config.read(config_file)

    dbname = config['DATABASE'].get('DBName', 'ngda-fleetops-contract-management-db')
    user = config['DATABASE'].get('User', 'postgres')
    password = config['DATABASE'].get('Password', 'Pass123_')
    host = config['DATABASE'].get('Host', '127.0.0.1')
    port = config['DATABASE'].get('Port', '5432')
    schema = config['DATABASE'].get('Schema', 'public')

    output_file = config['OUTPUT'].get('OutputFile', 'output.puml')

    exclude_config = configparser.ConfigParser()
    exclude_config.read(exclude_file)
    excluded_tables = exclude_config['EXCLUDE'].get('tables', '').split(',')

    conn = psycopg2.connect(dbname=dbname, user=user, password=password, host=host, port=port)
    tables, columns, foreign_keys = fetch_data_from_db(conn, schema)
    plantuml_output = to_plantuml(schema, tables, columns, foreign_keys)

    with open(output_file, "w") as f:
        f.write(plantuml_output)

    conn.close()

if __name__ == "__main__":
    main()
