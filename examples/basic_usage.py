#!/usr/bin/env python
"""
Example usage of the Data Provider Layer.

This script demonstrates how to use the DataProviderClient to fetch
historical market data from different providers.
"""

import asyncio
from datetime import datetime

from backtest_engine.data_provider import DataProviderClient
from backtest_engine.data_provider.interfaces.models import (
    Exchange,
    Segment,
    Interval,
)


async def main():
    """Main example function."""
    # Initialize client (loads config from ./config.yml, ~/.tradex/config.yml, env vars)
    client = DataProviderClient()
    
    try:
        # Initialize (loads config, creates providers, authenticates)
        await client.initialize()
        
        print("Data Provider Client initialized successfully!")
        print(f"Default provider: {client.get_default_provider().name}")
        print(f"Available providers: {list(client._providers.keys())}")
        
        # Example 1: Get historical OHLC data
        print("\n--- Fetching Historical Data ---")
        
        data = await client.get_historical_ohlc_data(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            from_date="2024-01-01",
            to_date="2024-01-02",
        )
        
        print(f"Fetched {len(data.data)} candles")
        print(f"Provider: {data.provider}")
        print(f"Cached: {data.cached}")
        
        if data.data:
            first = data.data[0]
            print(f"First candle: {first.timestamp} O={first.open} H={first.high} L={first.low} C={first.close} V={first.volume}")
        
        # Example 2: Get instrument master
        print("\n--- Fetching Instruments ---")
        
        instruments = await client.get_instruments(
            exchange="NSE",
            segment="EQ",
        )
        
        print(f"Fetched {len(instruments)} instruments")
        
        if instruments:
            inst = instruments[0]
            print(f"First instrument: {inst.symbol} ({inst.instrument_token})")
        
        # Example 3: Get instrument token
        print("\n--- Getting Instrument Token ---")
        
        token = await client.get_instrument_token(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
        )
        
        print(f"Instrument token: {token}")
        
        # Example 4: Using specific provider
        print("\n--- Using Specific Provider ---")
        
        # If you have multiple providers configured, you can specify which one to use
        # data = await client.get_historical_ohlc_data(
        #     symbol="RELIANCE",
        #     exchange="NSE",
        #     segment="EQ",
        #     interval="minute",
        #     from_date="2024-01-01",
        #     to_date="2024-01-02",
        #     provider="dhan",  # Use Dhan instead of default
        # )
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        await client.close()


async def simple_usage():
    """Simple one-liner usage with convenience function."""
    from backtest_engine.data_provider import get_historical_data
    
    data = await get_historical_data(
        symbol="RELIANCE",
        exchange="NSE",
        segment="EQ",
        interval="minute",
        from_date="2026-01-01",
        to_date="2026-01-02",
    )
    
    print(f"Simple usage: Got {len(data.data)} candles")


if __name__ == "__main__":
    asyncio.run(main())