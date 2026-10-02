"""Couche données : simulation, historique synthétique, APIs réelles."""

from .simulation import simulate_market_data
from .connectors import DataConnector, SimulatedConnector, PolygonConnector
from .loader import load_backtest_universe, BACKTEST_UNIVERSE

__all__ = [
    "simulate_market_data",
    "DataConnector",
    "SimulatedConnector",
    "PolygonConnector",
    "load_backtest_universe",
    "BACKTEST_UNIVERSE",
]
