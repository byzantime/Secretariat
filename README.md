# Secretariat

An open-source AI-powered personal assistant.

## Installation

Install dependencies:

```bash
uv pip install -r requirements.txt
```

Run the application:

```bash
python main.py
```
The app will run on http://localhost:5000

### Scheduling tasks:

```
You          14:38:00
remind me to take the rubbish out every other week, starting next thursday evening
Assistant    14:38:00
Done! I've set up a reminder to take the rubbish out every 14 days starting next Thursday (September 25th) at 7 PM.
```

## Development

```bash
# Run the app using the following command - it activates the venv, rebuilds CSS the starts the app:
./local_build.sh
```

### Updating dependencies:

```bash
# First add the new dependency to requirements.in, then:
uv pip compile requirements.in
uv pip install -r requirements.txt
```
