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

3. **Set environment variables**:
   ```bash
   export TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
   export TELEGRAM_WEBHOOK_URL="https://your-ngrok-url.ngrok.io"
   ```

4. **Start the app**:
   ```bash
   python main.py
   ```

The webhook will be automatically configured when the app starts. You can now message your bot on Telegram and it will communicate with your local development server!

### Updating dependencies:

```bash
# First add the new dependency to requirements.in, then:
uv pip compile requirements.in
uv pip install -r requirements.txt
```
