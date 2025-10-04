"""Tests for the Anika Blue application."""

import os
import sqlite3
import tempfile
from importlib import import_module

import pytest
from anika_blue.app import (
    app,
    init_db,
    generate_blue_shade,
    get_user_average,
    get_global_average,
    get_user_base_color,
    set_user_base_color,
    find_user_by_base_color,
    get_color_details,
)


def get_app_module():
    """Import the app module dynamically to access module-level constants."""

    return import_module("anika_blue.app")


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    db_fd, db_path = tempfile.mkstemp()
    app.config["TESTING"] = True
    app.config["DATABASE"] = db_path

    # Override the DATABASE environment variable for the app
    os.environ["DATABASE"] = db_path

    with app.test_client() as client:
        with app.app_context():
            init_db()
        yield client

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def db_connection():
    """Create a test database connection."""
    app_module = get_app_module()

    db_fd, db_path = tempfile.mkstemp()

    # Save the original DATABASE value
    original_database = app_module.DATABASE

    # Set the new DATABASE value
    app_module.DATABASE = db_path
    os.environ["DATABASE"] = db_path

    # Initialize the database
    init_db()

    yield db_path

    # Restore original DATABASE value
    app_module.DATABASE = original_database

    os.close(db_fd)
    os.unlink(db_path)


class TestDatabase:
    """Tests for database functionality."""

    def test_init_db(self, db_connection):
        """Test that database is initialized with correct tables."""
        conn = sqlite3.connect(db_connection)
        cursor = conn.cursor()

        # Check if tables exist
        cursor.execute(
            """SELECT name FROM sqlite_master
               WHERE type='table' AND name='votes'"""
        )
        assert cursor.fetchone() is not None

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='shown_shades'"
        )
        assert cursor.fetchone() is not None

        cursor.execute(
            """SELECT name FROM sqlite_master
               WHERE type='table' AND name='user_base_colors'"""
        )
        assert cursor.fetchone() is not None

        conn.close()


class TestColorGeneration:
    """Tests for color generation functions."""

    def test_generate_blue_shade(self):
        """Test that generated shades are valid blue colors."""
        for _ in range(100):
            shade = generate_blue_shade()

            # Check format
            assert shade.startswith("#")
            assert len(shade) == 7

            # Check that it's a valid hex color
            r = int(shade[1:3], 16)
            g = int(shade[3:5], 16)
            b = int(shade[5:7], 16)

            # Check blue shade constraints
            assert 0 <= r <= 100
            assert 0 <= g <= 200
            assert 150 <= b <= 255


class TestColorAveraging:
    """Tests for color averaging functions."""

    def test_get_color_details_exact(self):
        """Exact CSS color names are returned in the details payload."""
        details = get_color_details("#0000ff")
        assert details["css_name"] == "Blue"
        assert "Blue" in details["display_name"]

    def test_get_color_details_closest_match(self):
        """Nearest descriptive names are returned when no exact match exists."""
        details = get_color_details("#123456")
        assert isinstance(details["descriptive_name"], str)
        assert details["descriptive_name"] != "Unknown Color"
        if details["css_name"]:
            assert details["css_display_name"].startswith("~ ")

    def test_get_user_average_no_votes(self, db_connection):
        """Test that user average returns None when no votes exist."""
        app_module = get_app_module()

        app_module.DATABASE = db_connection
        result = get_user_average("test_user")
        assert result is None

    def test_get_user_average_with_votes(self, db_connection):
        """Test that user average is calculated correctly."""
        app_module = get_app_module()

        conn = sqlite3.connect(db_connection)
        cursor = conn.cursor()

        # Add some test votes
        cursor.execute(
            "INSERT INTO votes (user_id, hex_color, is_anika_blue) VALUES (?, ?, ?)",
            ("test_user", "#0000ff", 1),
        )
        cursor.execute(
            "INSERT INTO votes (user_id, hex_color, is_anika_blue) VALUES (?, ?, ?)",
            ("test_user", "#000099", 1),
        )
        conn.commit()
        conn.close()

        # Set DATABASE for the test
        app_module.DATABASE = db_connection

        result = get_user_average("test_user")
        assert result is not None
        color, count = result
        assert count == 2
        assert color.startswith("#")
        assert len(color) == 7

    def test_get_global_average_no_votes(self, db_connection):
        """Test that global average returns None when no votes exist."""
        app_module = get_app_module()

        app_module.DATABASE = db_connection
        result = get_global_average()
        assert result is None

    def test_get_global_average_with_votes(self, db_connection):
        """Test that global average is calculated correctly."""
        app_module = get_app_module()

        conn = sqlite3.connect(db_connection)
        cursor = conn.cursor()

        # Add some test votes from different users
        cursor.execute(
            "INSERT INTO votes (user_id, hex_color, is_anika_blue) VALUES (?, ?, ?)",
            ("user1", "#0000ff", 1),
        )
        cursor.execute(
            "INSERT INTO votes (user_id, hex_color, is_anika_blue) VALUES (?, ?, ?)",
            ("user2", "#000099", 1),
        )
        conn.commit()
        conn.close()

        # Set DATABASE for the test
        app_module.DATABASE = db_connection

        result = get_global_average()
        assert result is not None
        color, count = result
        assert count == 2
        assert color.startswith("#")
        assert len(color) == 7


class TestBaseColor:
    """Tests for base color functionality."""

    def test_get_user_base_color_not_set(self, db_connection):
        """Test that base color returns None when not set."""
        app_module = get_app_module()

        app_module.DATABASE = db_connection
        result = get_user_base_color("test_user")
        assert result is None

    def test_set_and_get_user_base_color(self, db_connection):
        """Test setting and getting user base color."""
        app_module = get_app_module()

        app_module.DATABASE = db_connection
        test_color = "#667eea"

        set_user_base_color("test_user", test_color)
        result = get_user_base_color("test_user")

        assert result == test_color

    def test_find_user_by_base_color(self, db_connection):
        """Test finding user by base color."""
        app_module = get_app_module()

        app_module.DATABASE = db_connection
        test_color = "#667eea"
        test_user = "test_user_123"

        set_user_base_color(test_user, test_color)
        result = find_user_by_base_color(test_color)

        assert result == test_user

    def test_find_user_by_base_color_not_found(self, db_connection):
        """Test finding user by base color when not found."""
        app_module = get_app_module()

        app_module.DATABASE = db_connection
        result = find_user_by_base_color("#ffffff")
        assert result is None


class TestRoutes:
    """Tests for Flask routes."""

    def test_index_route(self, client):
        """Test that index route returns successfully."""
        response = client.get("/")
        assert response.status_code == 200

    def test_next_shade_route(self, client):
        """Test that next-shade route returns a shade with metadata."""
        response = client.get("/next-shade")
        assert response.status_code == 200
        assert b"#" in response.data
        assert b"shade-name" in response.data
        assert b"data-shade-combined" in response.data

    def test_vote_route(self, client):
        """Test that vote route processes votes correctly."""
        # First get a shade
        response = client.get("/next-shade")

        # Vote yes on it
        response = client.post("/vote", data={"shade": "#0000ff", "vote": "yes"})
        assert response.status_code == 200

    def test_vote_skip(self, client):
        """Test that skip vote doesn't save to database."""
        response = client.post("/vote", data={"shade": "#0000ff", "vote": "skip"})
        assert response.status_code == 200

    def test_vote_count_accuracy(self, client, db_connection):
        """Test that votes are counted correctly without duplicates."""
        app_module = get_app_module()
        app_module.DATABASE = db_connection

        # Set up a session
        with client.session_transaction() as sess:
            sess["user_id"] = "test_user"

        # Vote on three different shades
        client.post("/vote", data={"shade": "#0000ff", "vote": "yes"})
        client.post("/vote", data={"shade": "#00ff00", "vote": "yes"})
        client.post("/vote", data={"shade": "#ff0000", "vote": "no"})

        # Count votes in database
        conn = sqlite3.connect(db_connection)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM votes")
        count = c.fetchone()[0]
        conn.close()

        # Should have exactly 3 votes (one for each call)
        assert count == 3

    def test_stats_route(self, client):
        """Test that stats route returns successfully."""
        response = client.get("/stats")
        assert response.status_code == 200

    def test_save_base_color_no_average(self, client):
        """Test saving base color when no average exists."""
        response = client.post("/save-base-color")
        assert response.status_code == 400

    def test_save_base_color_with_average(self, client, db_connection):
        """Test saving base color when average exists."""
        # Set up a session with some votes
        with client.session_transaction() as sess:
            sess["user_id"] = "test_user"

        # Add a vote
        client.post("/vote", data={"shade": "#0000ff", "vote": "yes"})

        # Save base color
        response = client.post("/save-base-color")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "base_color" in data

    def test_load_base_color_invalid_format(self, client):
        """Test loading base color with invalid format."""
        response = client.post("/load-base-color", data={"base_color": "invalid"})
        assert response.status_code == 400

    def test_load_base_color_not_found(self, client):
        """Test loading base color when not found."""
        response = client.post("/load-base-color", data={"base_color": "#ffffff"})
        assert response.status_code == 404

    def test_favicon_route(self, client):
        """Test that favicon route returns an image."""
        response = client.get("/favicon.ico")
        assert response.status_code == 200
        assert response.mimetype == "image/x-icon"
