from pydantic import BaseModel
from datetime import datetime, time

class AppointmentCreate(BaseModel):
    barber_id: int
    service_id: int
    client_name: str
    client_phone: str
    date: str  # Formato YYYY-MM-DD
    time: str  # Formato HH:MM