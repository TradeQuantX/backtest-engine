"""
Exit condition evaluation functions for the Position Manager.

Pure functions optimized for the hot path - no classes, no allocations in loops.
Nuitka-compatible: pure Python, no dynamic dispatch, type hints for optimization.

Exit Priority Order (enforced by PositionManager.evaluate_exits):
1. Stop Loss (highest priority - capital protection)
2. Trailing Stop (protects profits)
3. Take Profit (locks in gains)
4. Custom Exit (lowest priority - researcher-defined logic)

This priority ensures that protective exits always trigger before profit-taking
exits, preventing scenarios where a stop loss and take profit are both hit
in the same bar but the wrong one executes.
"""

from typing import Optional, Callable

from backtest_engine.data_provider.interfaces.models import NormalizedOHLC
from backtest_engine.engine.interfaces import BacktestContext
from backtest_engine.engine.position import Position, PositionSide


# =============================================================================
# Stop Loss Evaluation
# =============================================================================

def check_stop_loss(position: Position, ohlc: NormalizedOHLC) -> tuple[bool, float]:
    """
    Check if stop loss is triggered within the current bar.
    
    Uses OHLC to detect intra-bar stop triggers (no lookahead bias).
    Returns (triggered, exit_price).
    
    For LONG: stop triggered if low <= stop_price
    For SHORT: stop triggered if high >= stop_price
    
    Exit price = stop_price (if hit within bar range).
    Gap protection: if price gapped beyond stop, exit at open.
    """
    if position.stop_loss is None:
        return False, 0.0
    
    stop_price = position.stop_loss
    
    if position.side == PositionSide.LONG:
        # Long stop loss: price falls to or below stop
        if ohlc.low <= stop_price:
            # Gap protection: if open is below stop, price gapped down
            if ohlc.open <= stop_price:
                exit_price = ohlc.open
            else:
                exit_price = stop_price
            return True, exit_price
    else:
        # Short stop loss: price rises to or above stop
        if ohlc.high >= stop_price:
            # Gap protection: if open is above stop, price gapped up
            if ohlc.open >= stop_price:
                exit_price = ohlc.open
            else:
                exit_price = stop_price
            return True, exit_price
    
    return False, 0.0


# =============================================================================
# Take Profit Evaluation
# =============================================================================

def check_take_profit(position: Position, ohlc: NormalizedOHLC) -> tuple[bool, float]:
    """
    Check if take profit is triggered within the current bar.
    
    Returns (triggered, exit_price).
    
    For LONG: TP triggered if high >= tp_price
    For SHORT: TP triggered if low <= tp_price
    
    Exit price = tp_price (if hit within bar range).
    Gap protection: if price gapped beyond TP, exit at open.
    """
    if position.take_profit is None:
        return False, 0.0
    
    tp_price = position.take_profit
    
    if position.side == PositionSide.LONG:
        if ohlc.high >= tp_price:
            # Gap protection: if open is above TP, price gapped up past TP
            if ohlc.open >= tp_price:
                exit_price = ohlc.open
            else:
                exit_price = tp_price
            return True, exit_price
    else:
        if ohlc.low <= tp_price:
            # Gap protection: if open is below TP, price gapped down past TP
            if ohlc.open <= tp_price:
                exit_price = ohlc.open
            else:
                exit_price = tp_price
            return True, exit_price
    
    return False, 0.0


# =============================================================================
# Trailing Stop Evaluation
# =============================================================================

def check_trailing_stop(position: Position, ohlc: NormalizedOHLC) -> tuple[bool, float, float, float]:
    """
    Check and update trailing stop.
    
    Returns (triggered, exit_price, new_highest, new_lowest).
    
    For LONG:
    - Update highest_price = max(highest_price, high)
    - Trailing stop = highest_price * (1 - trailing_pct)
    - Trigger if low <= trailing_stop
    - Exit price = trailing_stop (or open if gapped below trailing_stop)
    
    For SHORT:
    - Update lowest_price = min(lowest_price, low)
    - Trailing stop = lowest_price * (1 + trailing_pct)
    - Trigger if high >= trailing_stop
    - Exit price = trailing_stop (or open if gapped above trailing_stop)
    """
    if position.trailing_stop_pct is None or position.trailing_stop_pct <= 0:
        return False, 0.0, position.highest_price, position.lowest_price
    
    trail_pct = position.trailing_stop_pct
    
    if position.side == PositionSide.LONG:
        # Update highest price seen
        new_highest = max(position.highest_price, ohlc.high)
        trailing_stop = new_highest * (1.0 - trail_pct)
        
        # Check if triggered
        if ohlc.low <= trailing_stop:
            # Gap protection: if open gapped below trailing stop, exit at open
            if ohlc.open <= trailing_stop:
                exit_price = ohlc.open
            else:
                exit_price = trailing_stop
            return True, exit_price, new_highest, position.lowest_price
        
        return False, 0.0, new_highest, position.lowest_price
    
    else:
        # Update lowest price seen
        new_lowest = min(position.lowest_price, ohlc.low)
        trailing_stop = new_lowest * (1.0 + trail_pct)
        
        # Check if triggered
        if ohlc.high >= trailing_stop:
            # Gap protection: if open gapped above trailing stop, exit at open
            if ohlc.open >= trailing_stop:
                exit_price = ohlc.open
            else:
                exit_price = trailing_stop
            return True, exit_price, position.highest_price, new_lowest
        
        return False, 0.0, position.highest_price, new_lowest


# =============================================================================
# Custom Exit Evaluation
# =============================================================================

def check_custom_exit(
    position: Position, 
    ohlc: NormalizedOHLC, 
    context: BacktestContext
) -> tuple[bool, float]:
    """
    Evaluate custom exit condition.
    
    Returns (triggered, exit_price).
    Uses close price for custom exits (researcher controls logic).
    """
    if position.custom_exit_fn is None:
        return False, 0.0
    
    try:
        triggered = position.custom_exit_fn(position, context)
        if triggered:
            return True, ohlc.close
    except Exception:
        # Fail-safe: never let custom exit crash the engine
        pass
    
    return False, 0.0


# =============================================================================
# Priority-Based Exit Resolution
# =============================================================================

def evaluate_exits(
    position: Position, 
    ohlc: NormalizedOHLC, 
    context: BacktestContext
) -> tuple[bool, float, str, float, float]:
    """
    Evaluate all exit conditions in priority order.
    
    Priority: Stop Loss > Trailing Stop > Take Profit > Custom Exit
    
    Returns (triggered, exit_price, exit_reason, new_highest, new_lowest).
    """
    # 1. Stop Loss (highest priority - capital protection)
    triggered, exit_price = check_stop_loss(position, ohlc)
    if triggered:
        return True, exit_price, "STOP_LOSS", position.highest_price, position.lowest_price
    
    # 2. Trailing Stop
    triggered, exit_price, new_highest, new_lowest = check_trailing_stop(position, ohlc)
    if triggered:
        return True, exit_price, "TRAILING_STOP", new_highest, new_lowest
    
    # 3. Take Profit
    triggered, exit_price = check_take_profit(position, ohlc)
    if triggered:
        return True, exit_price, "TAKE_PROFIT", position.highest_price, position.lowest_price
    
    # 4. Custom Exit (lowest priority)
    triggered, exit_price = check_custom_exit(position, ohlc, context)
    if triggered:
        return True, exit_price, "CUSTOM", position.highest_price, position.lowest_price
    
    # No exit triggered - return updated trailing prices
    _, _, new_highest, new_lowest = check_trailing_stop(position, ohlc)
    return False, 0.0, "", new_highest, new_lowest