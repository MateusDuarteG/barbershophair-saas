from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, date, time, timedelta
from .database import engine, SessionLocal, get_db
from . import models, schemas, scheduler

# Cria as tabelas no SQLite se não existirem
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="BarberSaaS API", version="1.0.0")

# Habilita CORS para o Frontend externo (Vercel / Lovable / Local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, você pode restringir ao domínio da Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- SEED DE DADOS INICIAIS ---
@app.on_event("startup")
def seed_data():
    db = SessionLocal()
    shop = db.query(models.Barbershop).filter(models.Barbershop.slug == "barbearia-dos-irmaos").first()
    if not shop:
        shop = models.Barbershop(
            slug="barbearia-dos-irmaos",
            name="Barbearia dos Irmãos",
            bio_text="✂️ O melhor corte da cidade | Estilo e Tradição 💈",
            whatsapp="5534999999999",
            instagram_url="https://instagram.com",
            maps_url="https://maps.google.com",
            address_text="Rua Principal, 100 - Centro"
        )
        db.add(shop)
        db.commit()
        db.refresh(shop)

        barber1 = models.Barber(barbershop_id=shop.id, name="Irmão Mais Velho (Famoso)", role="Master Barbeiro")
        barber2 = models.Barber(barbershop_id=shop.id, name="Irmão Mais Novo", role="Barbeiro")
        db.add_all([barber1, barber2])
        db.commit()
        db.refresh(barber1)
        db.refresh(barber2)

        service1 = models.Service(barbershop_id=shop.id, name="Corte Degradê", price=40.0, duration_minutes=40)
        service2 = models.Service(barbershop_id=shop.id, name="Barba Completa", price=30.0, duration_minutes=30)
        service3 = models.Service(barbershop_id=shop.id, name="Corte + Barba", price=65.0, duration_minutes=60)
        db.add_all([service1, service2, service3])
        db.commit()

        for b in [barber1, barber2]:
            for day in range(0, 6): # Segunda a Sábado
                wh = models.WorkingHour(
                    barber_id=b.id,
                    day_of_week=day,
                    start_time=time(9, 0),
                    end_time=time(19, 0),
                    lunch_start=time(12, 0),
                    lunch_end=time(13, 0)
                )
                db.add(wh)
        db.commit()
    db.close()


# --- ROTAS PÚBLICAS (Consumidas pelo Frontend) ---

@app.get("/api/barbershops/{slug}")
def get_barbershop(slug: str, db: Session = Depends(get_db)):
    shop = db.query(models.Barbershop).filter(models.Barbershop.slug == slug, models.Barbershop.is_active == True).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbearia não encontrada ou inativa.")
    
    return {
        "id": shop.id,
        "name": shop.name,
        "slug": shop.slug,
        "bio_text": shop.bio_text,
        "whatsapp": shop.whatsapp,
        "instagram_url": shop.instagram_url,
        "maps_url": shop.maps_url,
        "address_text": shop.address_text,
        "barbers": [{"id": b.id, "name": b.name, "role": b.role} for b in shop.barbers],
        "services": [{"id": s.id, "name": s.name, "price": s.price, "duration_minutes": s.duration_minutes} for s in shop.services]
    }


@app.get("/api/slots/{barber_id}")
def get_slots(barber_id: int, date_str: str, service_id: int, db: Session = Depends(get_db)):
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Data inválida. Use YYYY-MM-DD.")
    
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        return {"slots": []}
    
    slots = scheduler.get_available_slots(db, barber_id, target_date, service.duration_minutes)
    return {"slots": slots}


@app.post("/api/appointments")
def create_appointment(data: schemas.AppointmentCreate, db: Session = Depends(get_db)):
    service = db.query(models.Service).filter(models.Service.id == data.service_id).first()
    barber = db.query(models.Barber).filter(models.Barber.id == data.barber_id).first()
    
    if not service or not barber:
        raise HTTPException(status_code=400, detail="Serviço ou barbeiro inválido.")
    
    try:
        start_dt = datetime.strptime(f"{data.date} {data.time}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Data ou hora inválida.")
        
    end_dt = start_dt + timedelta(minutes=service.duration_minutes)
    
    appointment = models.Appointment(
        barbershop_id=barber.barbershop_id,
        barber_id=barber.id,
        service_id=service.id,
        client_name=data.client_name,
        client_phone=data.client_phone,
        start_datetime=start_dt,
        end_datetime=end_dt,
        status="agendado"
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    
    return {
        "success": True, 
        "message": "Agendamento realizado com sucesso!",
        "appointment_id": appointment.id
    }


# Portal do Cliente (Detalhes do agendamento via link do WhatsApp)
@app.get("/api/appointments/{appointment_id}")
def get_appointment_details(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    
    service = db.query(models.Service).filter(models.Service.id == appointment.service_id).first()
    barber = db.query(models.Barber).filter(models.Barber.id == appointment.barber_id).first()
    
    return {
        "id": appointment.id,
        "client_name": appointment.client_name,
        "client_phone": appointment.client_phone,
        "start_datetime": appointment.start_datetime,
        "status": appointment.status,
        "service_name": service.name if service else "Corte",
        "barber_name": barber.name if barber else "Barbeiro"
    }


@app.post("/api/appointments/{appointment_id}/confirm")
def client_confirm_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    
    appointment.status = "confirmado"
    db.commit()
    return {"success": True, "message": "Presença confirmada com sucesso!"}


# --- ROTAS DO PAINEL ADMIN / KANBAN ---

@app.get("/api/admin/appointments")
def get_admin_appointments(db: Session = Depends(get_db)):
    shop = db.query(models.Barbershop).filter(models.Barbershop.slug == "barbearia-dos-irmaos").first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbearia não encontrada.")
    
    appointments = db.query(models.Appointment).filter(
        models.Appointment.barbershop_id == shop.id,
        models.Appointment.status != "cancelado"
    ).all()

    services_map = {s.id: s for s in shop.services}
    today_date = date.today()

    total_revenue = sum(
        services_map[a.service_id].price for a in appointments 
        if a.status == "concluido" and a.start_datetime.date() == today_date and a.service_id in services_map
    )

    result = []
    for a in appointments:
        svc = services_map.get(a.service_id)
        result.append({
            "id": a.id,
            "client_name": a.client_name,
            "client_phone": a.client_phone,
            "date_str": a.start_datetime.strftime("%Y-%m-%d"),
            "time_str": a.start_datetime.strftime("%H:%M"),
            "status": a.status,
            "service_name": svc.name if svc else "Serviço",
            "price": svc.price if svc else 0.0,
            "barber_id": a.barber_id
        })

    return {
        "shop_name": shop.name,
        "total_revenue": total_revenue,
        "appointments": result,
        "barbers": [{"id": b.id, "name": b.name} for b in shop.barbers]
    }


@app.post("/api/appointments/{appointment_id}/status")
def update_appointment_status(appointment_id: int, status: str, db: Session = Depends(get_db)):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    
    appointment.status = status  # "concluido", "cancelado", "confirmado"
    db.commit()
    return {"success": status, "message": f"Status atualizado para {status}"}


@app.post("/api/appointments/{appointment_id}/reschedule")
def reschedule_appointment(appointment_id: int, data: dict, db: Session = Depends(get_db)):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    
    new_date_str = data.get("date")
    new_time_str = data.get("time")
    
    if not new_date_str or not new_time_str:
        raise HTTPException(status_code=400, detail="Data e hora são obrigatórias.")
        
    service = db.query(models.Service).filter(models.Service.id == appointment.service_id).first()
    
    try:
        start_dt = datetime.strptime(f"{new_date_str} {new_time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data ou hora inválido.")
        
    end_dt = start_dt + timedelta(minutes=service.duration_minutes)
    
    appointment.start_datetime = start_dt
    appointment.end_datetime = end_dt
    db.commit()
    return {"success": True, "message": "Reagendado com sucesso!"}