"""SQLite database module for website persistence.

Stores website metadata including site_id, description, place_id, and timestamps.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

# Database file location
DB_PATH = Path(__file__).parent / "websites.db"


def get_db_connection():
    """Get a database connection with proper configuration."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS websites (
            site_id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            place_id TEXT,
            place_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_count INTEGER DEFAULT 0,
            success BOOLEAN DEFAULT 1
        )
    """)
    
    # Create index for faster queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_created_at ON websites(created_at DESC)
    """)
    
    conn.commit()
    conn.close()
    print(f"✅ Database initialized at {DB_PATH}")


def save_website(
    site_id: str,
    description: str,
    place_id: Optional[str] = None,
    place_name: Optional[str] = None,
    file_count: int = 0,
    success: bool = True
) -> bool:
    """Save or update a website record.
    
    Args:
        site_id: Unique site identifier
        description: Website description/specification
        place_id: Optional Google Places place ID
        place_name: Optional business name
        file_count: Number of files created
        success: Whether the build was successful
    
    Returns:
        True if successful
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if site exists
        cursor.execute("SELECT site_id FROM websites WHERE site_id = ?", (site_id,))
        exists = cursor.fetchone()
        
        if exists:
            # Update existing record
            cursor.execute("""
                UPDATE websites 
                SET description = ?, 
                    place_id = ?,
                    place_name = ?,
                    updated_at = CURRENT_TIMESTAMP,
                    file_count = ?,
                    success = ?
                WHERE site_id = ?
            """, (description, place_id, place_name, file_count, success, site_id))
        else:
            # Insert new record
            cursor.execute("""
                INSERT INTO websites (site_id, description, place_id, place_name, file_count, success)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (site_id, description, place_id, place_name, file_count, success))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error saving website to database: {e}")
        return False


def get_website(site_id: str) -> Optional[Dict]:
    """Get a website record by site_id.
    
    Returns:
        Dictionary with website data or None if not found
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM websites WHERE site_id = ?
        """, (site_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    except Exception as e:
        print(f"❌ Error fetching website from database: {e}")
        return None


def list_websites(limit: int = 50) -> List[Dict]:
    """List all websites, ordered by creation date (newest first).
    
    Args:
        limit: Maximum number of websites to return
    
    Returns:
        List of website dictionaries
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM websites 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"❌ Error listing websites from database: {e}")
        return []


def delete_website(site_id: str) -> bool:
    """Delete a website record.
    
    Returns:
        True if successful
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM websites WHERE site_id = ?", (site_id,))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error deleting website from database: {e}")
        return False


# Initialize database on import
init_db()
