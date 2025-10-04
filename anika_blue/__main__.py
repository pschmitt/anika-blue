from .app import BIND_HOST, BIND_PORT, DEBUG, app, init_db


def main():
    """Entry point for python -m anika_blue or the console script."""
    init_db()
    app.run(debug=DEBUG, host=BIND_HOST, port=BIND_PORT)


if __name__ == "__main__":
    main()
