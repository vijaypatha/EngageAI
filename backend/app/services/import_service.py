import csv
from sqlalchemy.orm import Session
from app.models import Customer

def import_customers_from_csv(file_path: str, db: Session):
    with open(file_path, newline='') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            name, phone = row
            db.add(Customer(name=name, phone=phone))
        db.commit()
