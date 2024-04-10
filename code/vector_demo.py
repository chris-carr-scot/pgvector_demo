import json
import sys
import argparse
import psycopg
import jsonschema
import csv
import os
from sentence_transformers import SentenceTransformer
import numpy as np
from pgvector.psycopg import register_vector

# Schemas for the import files deined to check imput files correctly fomratted.
record_schema = {
    "type": "object",
    "properties": {
        "information": {"type": "string"},
    },
}

def log_error(level,msg,e):
# errors logged to standard out
# TODO Mor ecomplete error logging to file
    print(f'{level}: {msg}')
    print(f'Full error: {e}')

def read_file(file_path):
# Function to open and read file, 
# Fatal error thrown on json error.
# Fatal error thrown on file not found.

    is_file = os.path.isfile(file_path)
    if not is_file:
        log_error('FATAL','Input file does not exist','')
        sys.exit(1)

    with open(file_path, 'r') as file:
        try:
            json_data = json.load(file)
        except json.JSONDecodeError as e:
            log_error('FATAL','Json decode issue',e)
            sys.exit(1)
    file.close()
    return json_data

def load_record(connection,record):
# Inserts record into the appropriate table.
# Uses the json schemas defined to confirm records complete.
# Insert error triggers rollback.
# TODO: bulk load data

    embeddingsql = "INSERT INTO embeddings (embedding, text) values (%s,%s);"

    model = SentenceTransformer("all-MiniLM-L6-v2")
    sentence_embedding = model.encode(record["information"])

    try:
        jsonschema.validate(instance=record, schema=record_schema)
    except jsonschema.exceptions.ValidationError as e:
        log_error("WARNING","Invalid Start record",e)

    try:
        cur = connection.cursor()
        cur.execute(embeddingsql,(sentence_embedding, record["information"]))
        connection.commit()
    except psycopg.Error as e:
        log_error("WARNING","insert errror record",e)
        connection.rollback()

def generate_report(connection,output_path,question):
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embedding = model.encode(question)

    searchsql = "SELECT text,  1 - (embedding <=> %(embedding)s) AS cosine_similarity FROM embeddings ORDER BY cosine_similarity desc LIMIT 3"
    cur = connection.cursor()

    cur.execute(searchsql,{'embedding': embedding})
    rows = cur.fetchall()
    column_names = [desc[0] for desc in cur.description]

    # Write the data to a CSV file
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(column_names)  # write the column names
        writer.writerows(rows)  # write the rows

def create_connection(HOST, DB, USER, PASSWORD):
# Create database connection.
    try:
        conn = psycopg.connect(
            host=HOST,
            dbname=DB,
            user=USER,
            password=PASSWORD
        )
        return conn
    except psycopg.Error as e:
        log_error("Fatal","Error connecting to the database", e)
        sys.exit(1)

if __name__ == "__main__":
# Parse command line and execute program.
    
    argParser = argparse.ArgumentParser()
    argParser.add_argument("-s", "--server", help="Database server")
    argParser.add_argument("-d", "--database", help="Database name")
    argParser.add_argument("-u", "--user", help="Database user")
    argParser.add_argument("-p", "--password", help="Database password")
    argParser.add_argument("-f", "--file", help="File To load")

    args = argParser.parse_args()
    connection = create_connection(args.server,args.database,args.user,args.password)
    register_vector(connection)
    
    data = read_file(args.file)
    for record in data:
        print(record)
        load_record(connection, record)

    generate_report(connection, 'cat_q1.csv', 'Did anyone adopt a cat this weekend?')

    generate_report(connection, 'breakfast_q1.csv', 'Whats for breakfast?')

    generate_report(connection, 'breakfast_q2.csv', 'Are cats nice to eat for breakfast?')
    
    connection.close
