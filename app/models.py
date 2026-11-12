from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Time
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Barbershop(Base):
    __tablename__ = "barbershops"
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False) # ex: irmaos-barber
    name = Column(String, nullable=False)
    bio_text = Column(String)
    whatsapp = Column(String, nullable=False) # formato: 5534999999999
    instagram_url = Column(String)
    maps_url = Column(String)
    address_text = Column(String)
    is_active = Column(Boolean, default=True)

    barbers = relationship("Barber", back_populates="barbershop")
    services = relationship("Service", back_populates="barbershop")

class Barber(Base):
    __tablename__ = "barbers"
    id = Column(Integer, primary_key=True, index=True)
    barbershop_id = Column(Integer, ForeignKey("barbershops.id"))
    name = Column(String, nullable=False)
    role = Column(String, default="Barbeiro")
    active = Column(Boolean, default=True)

    barbershop = relationship("Barbershop", back_populates="barbers")
    working_hours = relationship("WorkingHour", back_populates="barber")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    barbershop_id = Column(Integer, ForeignKey("barbershops.id"))
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    duration_minutes = Column(Integer, default=30)

    barbershop = relationship("Barbershop", back_populates="services")

class WorkingHour(Base):
    __tablename__ = "working_hours"
    id = Column(Integer, primary_key=True, index=True)
    barber_id = Column(Integer, ForeignKey("barbers.id"))
    day_of_week = Column(Integer, nullable=False) # 0 = Segunda ... 6 = Domingo
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    lunch_start = Column(Time, nullable=True)
    lunch_end = Column(Time, nullable=True)

    barber = relationship("Barber", back_populates="working_hours")

class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True, index=True)
    barbershop_id = Column(Integer, ForeignKey("barbershops.id"))
    barber_id = Column(Integer, ForeignKey("barbers.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    client_name = Column(String, nullable=False)
    client_phone = Column(String, nullable=False)
    start_datetime = Column(DateTime, nullable=False)
    end_datetime = Column(DateTime, nullable=False)
    status = Column(String, default="agendado") # agendado, concluido, cancelado