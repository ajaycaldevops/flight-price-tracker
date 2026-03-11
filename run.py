"""Entry point for the Flight Price Tracker app."""
from app import create_app

if __name__ == "__main__":
    app = create_app()
    print("\n  Flight Price Tracker is running!")
    print("  Open http://localhost:5000 in your browser.\n")
    app.run(debug=False, host="0.0.0.0", port=5000)
