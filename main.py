from src import create_app

app = create_app()

if __name__ == "__main__":
    app.logger.info("Starting Apparat")
    app.run(debug=app.config["DEBUG"])
