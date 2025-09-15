# Yet to be named

An open-source AI-powered personal assistant.

## Requirements

- Python 3.11+

## Installation

Install dependencies using uv:

```bash
uv pip install -r requirements.txt
```

## Running the Application

For basic startup:

```bash
python main.py
```

## Development

Run the app using the following command - it activates the venv and rebuilds CSS:

```bash
./local_build.sh
```
To update dependencies, recompile the requirements file:

```bash
uv pip compile requirements.in
```

### Code Quality

Lint code using ruff:

```bash
ruff check . --fix
```

Format code using black:

```bash
black .
```
