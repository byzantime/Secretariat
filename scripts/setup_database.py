#!/usr/bin/env python3
"""
Database setup script for the application.
Creates a new database, user, and password based on environment variables.
Uses the same configuration as src/config.py
"""

import os
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()

# Database configuration from environment variables (same as config.py)
DATABASE_HOST = os.environ.get("DATABASE_HOST", "localhost")
DATABASE_PORT = os.environ.get("DATABASE_PORT", "5432")
DATABASE_USER = os.environ.get("DATABASE_USER", "postgres")
DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD", "")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "src")


def run_psql_command(command, database="postgres", user="postgres", password=""):
    """Run a PostgreSQL command using psql."""
    env = os.environ.copy()
    if password:
        env["PGPASSWORD"] = password

    cmd = [
        "psql",
        "-h",
        DATABASE_HOST,
        "-p",
        DATABASE_PORT,
        "-U",
        user,
        "-d",
        database,
        "-c",
        command,
        "-q",
    ]

    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error executing: {command}")
            print(f"Error: {result.stderr}")
            return False
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error executing PostgreSQL command: {e}")
        return False
    except FileNotFoundError:
        print("Error: psql command not found. Please install PostgreSQL client.")
        return False


def database_exists():
    """Check if the database already exists."""
    command = f"SELECT 1 FROM pg_database WHERE datname = '{DATABASE_NAME}'"
    result = subprocess.run(
        [
            "psql",
            "-h",
            DATABASE_HOST,
            "-p",
            DATABASE_PORT,
            "-U",
            DATABASE_USER,
            "-d",
            "postgres",
            "-c",
            command,
            "-t",
            "-A",
            "-q",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PGPASSWORD": DATABASE_PASSWORD},
    )

    return result.returncode == 0 and result.stdout.strip() == "1"


def user_exists():
    """Check if the user already exists."""
    command = f"SELECT 1 FROM pg_user WHERE usename = '{DATABASE_USER}'"
    result = subprocess.run(
        [
            "psql",
            "-h",
            DATABASE_HOST,
            "-p",
            DATABASE_PORT,
            "-U",
            DATABASE_USER,
            "-d",
            "postgres",
            "-c",
            command,
            "-t",
            "-A",
            "-q",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PGPASSWORD": DATABASE_PASSWORD},
    )

    return result.returncode == 0 and result.stdout.strip() == "1"


def main():
    print("Database Setup Script")
    print("====================")
    print(f"Host: {DATABASE_HOST}:{DATABASE_PORT}")
    print(f"Database: {DATABASE_NAME}")
    print(f"User: {DATABASE_USER}")
    print()

    # Check if we can connect to PostgreSQL
    if not run_psql_command(
        "SELECT version();", "postgres", DATABASE_USER, DATABASE_PASSWORD
    ):
        print("Failed to connect to PostgreSQL. Please check your connection settings.")
        sys.exit(1)

    print("✓ Connected to PostgreSQL successfully")

    # Check if database already exists
    if database_exists():
        print(f"Database '{DATABASE_NAME}' already exists. Skipping creation.")
    else:
        print(f"Creating database '{DATABASE_NAME}'...")
        if run_psql_command(
            f"CREATE DATABASE {DATABASE_NAME};",
            "postgres",
            DATABASE_USER,
            DATABASE_PASSWORD,
        ):
            print(f"✓ Database '{DATABASE_NAME}' created successfully")
        else:
            print(f"✗ Failed to create database '{DATABASE_NAME}'")
            sys.exit(1)

    # Grant privileges to the user on the database
    print(
        f"Granting privileges to user '{DATABASE_USER}' on database"
        f" '{DATABASE_NAME}'..."
    )
    if run_psql_command(
        f"GRANT ALL PRIVILEGES ON DATABASE {DATABASE_NAME} TO {DATABASE_USER};",
        "postgres",
        DATABASE_USER,
        DATABASE_PASSWORD,
    ):
        print("✓ Privileges granted successfully")
    else:
        print("✗ Failed to grant privileges")
        sys.exit(1)

    print()
    print("Database setup completed successfully!")
    print("You can now run: alembic upgrade head")
    print(
        "To connect:"
        f" postgresql+asyncpg://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
    )


if __name__ == "__main__":
    main()
