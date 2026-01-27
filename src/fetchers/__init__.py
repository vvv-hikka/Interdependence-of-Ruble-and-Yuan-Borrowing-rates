# Fetchers package - modules for data retrieval from various sources
from .akshare_cn import AKShareFetcher
from .moex import MOEXFetcher
from .cbr import CBRFetcher
from .fred import FREDFetcher
from .imf import IMFFetcher

__all__ = ['AKShareFetcher', 'MOEXFetcher', 'CBRFetcher', 'FREDFetcher', 'IMFFetcher']

