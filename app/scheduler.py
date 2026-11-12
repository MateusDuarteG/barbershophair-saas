from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
from .models import WorkingHour, Appointment

def get_available_slots(db: Session, barber_id: int, target_date: date, service_duration: int):
    day_of_week = target_date.weekday()
    
    # 1. Busca o expediente do barbeiro nesse dia da semana
    work = db.query(WorkingHour).filter(
        WorkingHour.barber_id == barber_id,
        WorkingHour.day_of_week == day_of_week
    ).first()
    
    if not work:
        return [] # Barbeiro não trabalha nesse dia

    # 2. Busca agendamentos ativos desse barbeiro na data escolhida
    start_of_day = datetime.combine(target_date, work.start_time)
    end_of_day = datetime.combine(target_date, work.end_time)
    
    existing_appointments = db.query(Appointment).filter(
        Appointment.barber_id == barber_id,
        Appointment.status != "cancelado",
        Appointment.start_datetime >= start_of_day,
        Appointment.end_datetime <= end_of_day
    ).all()

    slots = []
    current_slot = start_of_day
    step = timedelta(minutes=30) # Grade de 30 em 30 min (pode ajustar para 15)
    duration = timedelta(minutes=service_duration)
    now = datetime.now()

    while current_slot + duration <= end_of_day:
        slot_end = current_slot + duration
        
        # Ignora horários que já passaram hoje
        if current_slot <= now:
            current_slot += step
            continue

        # Verifica conflito com horário de almoço
        in_lunch = False
        if work.lunch_start and work.lunch_end:
            lunch_s = datetime.combine(target_date, work.lunch_start)
            lunch_e = datetime.combine(target_date, work.lunch_end)
            if current_slot < lunch_e and slot_end > lunch_s:
                in_lunch = True

        # Verifica conflito com agendamentos já marcados
        has_conflict = False
        for appt in existing_appointments:
            if current_slot < appt.end_datetime and slot_end > appt.start_datetime:
                has_conflict = True
                break

        if not in_lunch and not has_conflict:
            slots.append(current_slot.strftime("%H:%M"))

        current_slot += step

    return slots