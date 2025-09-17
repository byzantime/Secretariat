# Database Setup Scripts

This directory contains scripts for setting up and managing the application database.

## setup_database.py

A Python script that creates the database and configures user privileges using the same environment variables as your application configuration.

### Usage

```bash
# Set your environment variables (same as used in your application)
export DATABASE_HOST=localhost
export DATABASE_PORT=5432
export DATABASE_USER=postgres
export DATABASE_PASSWORD=your_password
export DATABASE_NAME=src

# Run the setup script
python scripts/setup_database.py
```

### What it does

1. Connects to PostgreSQL using the provided credentials
2. Creates the database if it doesn't exist
3. Grants all privileges on the database to the specified user
4. Provides the connection string for your application

### Environment Variables

The script uses the same environment variables as `src/config.py`:

- `DATABASE_HOST` - PostgreSQL host (default: localhost)
- `DATABASE_PORT` - PostgreSQL port (default: 5432)
- `DATABASE_USER` - PostgreSQL user (default: postgres)
- `DATABASE_PASSWORD` - PostgreSQL password (default: empty)
- `DATABASE_NAME` - Database name to create (default: src)

### After Setup

Once the database is created, run the migrations:

```bash
alembic upgrade head
```

### Requirements

- PostgreSQL client tools (`psql` command)
- Python 3.x
- `python-dotenv` package (install with `pip install python-dotenv`)