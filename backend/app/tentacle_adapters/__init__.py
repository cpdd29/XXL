"""Tentacle adapter layer.

Each adapter maps unified gateway payloads to external tentacle protocols.
"""

from app.tentacle_adapters.crm_adapter import CRMAdapter
from app.tentacle_adapters.order_adapter import OrderAdapter
from app.tentacle_adapters.pdf_adapter import PDFAdapter
from app.tentacle_adapters.search_adapter import SearchAdapter
from app.tentacle_adapters.weather_adapter import WeatherAdapter
from app.tentacle_adapters.writer_adapter import WriterAdapter

__all__ = [
    "SearchAdapter",
    "PDFAdapter",
    "WriterAdapter",
    "WeatherAdapter",
    "OrderAdapter",
    "CRMAdapter",
]

