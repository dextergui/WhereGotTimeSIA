from dataclasses import dataclass
from typing import Optional

@dataclass(slots=True)
class FlightRow:
    start_date: str
    arrival_date: Optional[str] = None # for overnight flights
    flight_number: Optional[str] = None
    sector: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    duty_type: Optional[str] = None
    rpt: Optional[str] = None
    std: Optional[str] = None
    sta: Optional[str] = None
    flight_time: Optional[str] = None
    duty_time: Optional[str] = None
    fdp: Optional[str] = None
    raw_block: Optional[str] = None