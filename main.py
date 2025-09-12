from src import create_app

app = create_app()

if __name__ == "__main__":
    app.logger.info("Starting the Octovox AI Agent")
    app.run(debug=app.config["DEBUG"])
