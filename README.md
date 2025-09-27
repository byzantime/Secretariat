# Secretariat

An open-source AI-powered personal assistant.

## Installation

Install dependencies:

```bash
uv pip install -r requirements.txt
```

Set up the database:

```bash
alembic upgrade head
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

### Telegram Integration

To enable Telegram integration during local development:

1. **Create a Telegram bot**:
   - Message [@BotFather](https://t.me/botfather) on Telegram
   - Send `/newbot` and follow the instructions
   - Save the bot token you receive

2. **Install and start ngrok**:
   ```bash
   # Install ngrok (if not already installed)
   # Visit https://ngrok.com/ to download

   # Start ngrok tunnel to your local app
   ngrok http 5000
   ```

3. **Add Telegram envvars to your .env file**:
   ```bash
   TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
   TELEGRAM_WEBHOOK_URL=https://your-ngrok-url.ngrok.io
   TELEGRAM_ALLOWED_USERS=123456789,987654321  # Users you'd like to allow to use your bot.
   ```

4. **Start the app**:
   ```bash
   python main.py
   ```

The webhook will be automatically configured when the app starts. You can now message your bot on Telegram and it will communicate with your local development server!

### Qdrant Setup

Secretariat uses [Qdrant](https://qdrant.tech/) as a vector database for its memory system. You can run Qdrant locally with Docker or use Qdrant Cloud.

#### Local Docker Setup

Run Qdrant locally using Docker:

```bash
docker run -p 6333:6333 qdrant/qdrant
```

Add these environment variables to your `.env` file:

```bash
# Local Qdrant configuration (default values)
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

#### Qdrant Cloud Setup

1. **Create a Qdrant Cloud cluster**:
   - Visit [https://cloud.qdrant.io/](https://cloud.qdrant.io/)
   - Sign up and create a new cluster
   - Note your cluster URL and API key

2. **Configure cloud connection** in your `.env` file:
   ```bash
   # Qdrant Cloud configuration
   QDRANT_HOST=https://your-cluster-url.qdrant.tech
   QDRANT_API_KEY=your-api-key-here
   ```

The memory system will automatically create the required collection (`memories`) when the application starts.

### Updating dependencies:

```bash
# First add the new dependency to requirements.in, then:
uv pip compile requirements.in --output-file requirements.txt
uv pip install -r requirements.txt
```
