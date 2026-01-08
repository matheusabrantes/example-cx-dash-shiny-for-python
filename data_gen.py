import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

def generate_data(n=1000):
    np.random.seed(42)
    
    # Configuration
    countries = ["USA", "UK", "Canada", "Germany", "France", "Brazil", "Japan"]
    channels = ["Email", "Phone", "Chat", "Social Media", "Web Form"]
    categories = ["Billing", "Technical Support", "Product Quality", "Shipping", "Account Access"]
    statuses = ["Open", "Closed", "In Progress", "Escalated", "Resolved"]
    
    start_date = datetime(2025, 1, 1)
    
    data = {
        "complaint_id": range(1, n + 1),
        "date": [start_date + timedelta(days=np.random.randint(0, 365)) for _ in range(n)],
        "country": np.random.choice(countries, n),
        "channel": np.random.choice(channels, n),
        "category": np.random.choice(categories, n),
        "status": np.random.choice(statuses, n),
        "sla_hours": np.random.randint(12, 120, n),
        "amount": np.random.uniform(10, 500, n).round(2),
        "customer_id": [f"CUST-{np.random.randint(1000, 9999)}" for _ in range(n)],
        "is_escalated": np.random.choice([0, 1], n, p=[0.85, 0.15])
    }
    
    df = pd.DataFrame(data)
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
    
    # Create SQLite database
    db_path = "complaints.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn = sqlite3.connect(db_path)
    df.to_sql("complaints", conn, index=False, if_exists="replace")
    conn.close()
    print(f"Database created at {db_path} with {n} records.")

if __name__ == "__main__":
    generate_data()
