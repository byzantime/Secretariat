# Secretariat

An open-source AI-powered personal assistant.

## Running Secretariat

```bash
uv sync               # Install required dependencies
alembic upgrade head  # Setup the database
python main.py        # The application will now run on http://localhost:5000
```

### Scheduling tasks
```
You          14:38:00
remind me to take the rubbish out every other week, starting next thursday evening
Assistant    14:38:00
Done! I've set up a reminder to take the rubbish out every 14 days starting next Thursday (September 25th) at 7 PM.
```

### Online Shopping

Online shopping via Telegram demonstrating use of the shopping list, web browser and todo tools and requesting assistance from the user when necessary.

...

**You**: add homegrown orange juice to the shopping list - largest size

**Secretariat**: _Adding to shopping list..._
Added Homegrown Orange Juice (largest size) to your shopping list.

**You**: What's on the shopping list?

**Secretariat**: Getting shopping list...

Shopping List:
1. Colby Cheese
2. Whittaker's Hazelnut Chocolate
3. Proper Crisps (3 packs)
4. Big Pack Of Indomie Mi Goreng Noodles
5. Homegrown Orange Juice (largest size)

**You**: alright now go buy it all from newworld.co.nz.  lemme know when it's all in the basket

**Secretariat**: _Updating todos..._

_Using the web browser..._

I need your help with `https://www.newworld.co.nz/`

[Please log in (or start shopping by selecting your store) so I can add the requested groceries to the cart.]()

_Link expires in 5 minutes_

## Development

```bash
uv sync --extra dev  # Install optional dev dependencies

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
# Add the new dependency to pyproject.toml [project] dependencies section, then:
uv lock
uv sync
```
