import urllib3
import os
import time
import psycopg2
from psycopg2.extras import DictCursor  # For dictionary-like results
from dotenv import load_dotenv
from psycopg2 import sql
import logging

# Load environment variables from .env file
load_dotenv()

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO)

# MySQL database configuration
db_host = os.getenv("DATABASE_HOST")
db_user = os.getenv("DATABASE_USER")
db_password = os.getenv("DATABASE_PASSWORD")
db_schema = os.getenv("DATABASE_SCHEMA")


db_config = {
    'host': db_host,  # Replace with your MySQL host
    'user': db_user,       # Replace with your MySQL username
    'password': db_password,  # Replace with your MySQL password
    'database': db_schema,  # Replace with your database name
    'port' : 5432
}

# Database connection function
def get_db_connection(retries=4, delay=2):
    for attempt in range(retries):
        try:
            conn = psycopg2.connect(**db_config)
            print("Database connection successful!")
            return conn
        except psycopg2.Error as err:
            print(f"Attempt {attempt + 1} failed: {err}")
            if attempt < retries - 1:
                time.sleep(delay)  # Wait before retrying
            else:
                print("Max retries reached. Failed to connect to the database.")
                return None
            





# # Check if the connection was successful
# conn = get_db_connection()
# if conn:
#     print("Database is connected!")
    
#     # Create a cursor
#     cur = conn.cursor()
    
#     # Execute a query
#     cur.execute("SELECT * FROM dummy_facultydata;")
    
#     # Fetch and print results
#     rows = cur.fetchall()
#     for row in rows:
#         print(row)
    
#     # Close the cursor and connection
#     cur.close()
#     conn.close()
# else:
#     print("Failed to connect to the database.")