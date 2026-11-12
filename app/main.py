from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, date, time, timedelta
from .database import engine, SessionLocal, get_db
from . import models, schemas, scheduler

# Cria as tabelas no SQLite se não existirem
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="BarberSaaS Multi-Tenant")
templates = Jinja2Templates(directory="templates")

# --- ROTAS DO PAINEL ADMIN / BARBEIRO ---

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
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

    # Pega a URL base automaticamente (ex: http://localhost:8000/ ou http://100.x.x.x:8000/)
    base_url = str(request.base_url).rstrip('/')

    return templates.TemplateResponse(
        request, 
        "admin.html", 
        {
            "shop": shop,
            "barbers": shop.barbers,
            "appointments": appointments,
            "services_map": services_map,
            "total_revenue": total_revenue,
            "today": today_date,
            "timedelta": timedelta,
            "base_url": base_url # <--- Injetando a URL base dinâmica aqui
        }
    )

# API para atualizar o status do agendamento (concluir ou cancelar)
@app.post("/api/appointments/{appointment_id}/status")
def update_appointment_status(appointment_id: int, status: str, db: Session = Depends(get_db)):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    
    appointment.status = status # "concluido" ou "cancelado"
    db.commit()
    return {"success": True, "message": f"Status atualizado para {status}"}

# Função de Seed: Cria dados iniciais para testes reais
@app.on_event("startup")
def seed_data():
    db = SessionLocal()
    # Verifica se já existe a barbearia padrão
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

        # Cadastra os dois irmãos
        barber1 = models.Barber(barbershop_id=shop.id, name="Irmão Mais Velho (Famoso)", role="Master Barbeiro")
        barber2 = models.Barber(barbershop_id=shop.id, name="Irmão Mais Novo", role="Barbeiro")
        db.add_all([barber1, barber2])
        db.commit()
        db.refresh(barber1)
        db.refresh(barber2)

        # Cadastra serviços padrão
        service1 = models.Service(barbershop_id=shop.id, name="Corte Degradê", price=40.0, duration_minutes=40)
        service2 = models.Service(barbershop_id=shop.id, name="Barba Completa", price=30.0, duration_minutes=30)
        service3 = models.Service(barbershop_id=shop.id, name="Corte + Barba", price=65.0, duration_minutes=60)
        db.add_all([service1, service2, service3])
        db.commit()

        # Cadastra horários de expediente (Segunda a Sábado, das 09:00 às 19:00, almoço 12:00 às 13:00)
        for b in [barber1, barber2]:
            for day in range(0, 6): # 0 = Segunda até 5 = Sábado
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

# Rota da Página Pública (Estilo Linktree + Agendamento)
@app.get("/{slug}", response_class=HTMLResponse)
def public_bio(slug: str, request: Request, db: Session = Depends(get_db)):
    shop = db.query(models.Barbershop).filter(models.Barbershop.slug == slug, models.Barbershop.is_active == True).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbearia não encontrada ou inativa.")
    
    return templates.TemplateResponse(
        request, 
        "bio_booking.html", 
        {
            "shop": shop,
            "barbers": shop.barbers,
            "services": shop.services
        }
    )

# API para buscar horários livres de um barbeiro em um dia específico
@app.get("/api/slots/{barber_id}")
def get_slots(barber_id: int, date_str: str, service_id: int, db: Session = Depends(get_db)):
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        return {"slots": []}
    
    slots = scheduler.get_available_slots(db, barber_id, target_date, service.duration_minutes)
    return {"slots": slots}

# API para realizar o agendamento
@app.post("/api/appointments")
def create_appointment(data: schemas.AppointmentCreate, db: Session = Depends(get_db)):
    service = db.query(models.Service).filter(models.Service.id == data.service_id).first()
    barber = db.query(models.Barber).filter(models.Barber.id == data.barber_id).first()
    
    if not service or not barber:
        raise HTTPException(status_code=400, detail="Serviço ou barbeiro inválido.")
    
    start_dt = datetime.strptime(f"{data.date} {data.time}", "%Y-%m-%d %H:%M")
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

    # API para remanejar / reagendar um atendimento pelo Painel Admin
@app.post("/api/appointments/{appointment_id}/reschedule")
def reschedule_appointment(appointment_id: int, data: dict, db: Session = Depends(get_db)):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    
    new_date_str = data.get("date")
    new_time_str = data.get("time")
    
    service = db.query(models.Service).filter(models.Service.id == appointment.service_id).first()
    
    start_dt = datetime.strptime(f"{new_date_str} {new_time_str}", "%Y-%m-%d %H:%M")
    end_dt = start_dt + timedelta(minutes=service.duration_minutes)
    
    appointment.start_datetime = start_dt
    appointment.end_datetime = end_dt
    db.commit()

    # Rota pública atualizada com suporte ao Portal do Cliente (?agendamento=ID)
@app.get("/{slug}", response_class=HTMLResponse)
def public_bio(request: Request, slug: str, agendamento: int = None, db: Session = Depends(get_db)):
    shop = db.query(models.Barbershop).filter(models.Barbershop.slug == slug).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbearia não encontrada.")
    
    # Se o cliente abriu pelo link do WhatsApp com um ID de agendamento
    client_appointment = None
    service_name = ""
    if agendamento:
        client_appointment = db.query(models.Appointment).filter(models.Appointment.id == agendamento).first()
        if client_appointment:
            svc = db.query(models.Service).filter(models.Service.id == client_appointment.service_id).first()
            service_name = svc.name if svc else "Corte"

    return templates.TemplateResponse(
        request, 
        "bio_booking.html", 
        {
            "shop": shop,
            "barbers": shop.barbers,
            "services": shop.services,
            "client_appointment": client_appointment,
            "service_name": service_name
        }
    )

# API para o cliente confirmar o agendamento pelo Portal do Cliente
@app.post("/api/appointments/{appointment_id}/confirm")
def client_confirm_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    
    appointment.status = "confirmado" # Status novo para diferenciar
    db.commit()
    return {"success": True, "message": "Presença confirmada com sucesso!"}
     
