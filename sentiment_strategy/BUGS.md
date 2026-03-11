# Sentiment Strategy Bug Tracking

**Goal:** Run strategy live with zero errors

## Critical Issues (Must Fix First)

### [x] BUG-001: Import errors in signals.py
- **File:** `signals.py:15-16`
- **Problem:** Uses `from sentiment` instead of `from .sentiment`
- **Impact:** Module cannot be imported as package
- **Fix:** Change to relative imports
- **Status:** FIXED - Changed to relative imports

### [x] BUG-002: Crash on HOLD signal formatting None values
- **File:** `signals.py:659-660`
- **Problem:** `stop_loss` and `take_profit` are `None` for HOLD signals
- **Impact:** Example script crashes
- **Fix:** Add None check before formatting
- **Status:** Fixed - Added None checks for stop_loss and take_profit formatting

### [x] BUG-003: SignalGenerator doesn't implement common.interfaces.SignalGenerator
- **File:** `signals.py:84-94`
- **Problem:** Missing required interface methods
- **Impact:** Cannot use with TradingSystem or backtest engine
- **Fix:** Implement interface properly
- **Status:** FIXED - SignalGenerator now inherits from BaseSignalGenerator and implements all required interface methods

### [x] BUG-004: Import errors in example.py
- **File:** `example.py:9-13`
- **Problem:** Same relative import issue
- **Impact:** Example only works from specific directory
- **Fix:** Change to relative imports
- **Status:** FIXED - Changed to relative imports

## Major Issues

### [x] BUG-005: Cold start problem for sentiment extremes
- **File:** `sentiment.py:411-471`
- **Problem:** Needs 30+ observations before signals can be generated
- **Impact:** Strategy non-functional for new symbols
- **Fix:** Added fallback for insufficient history with absolute threshold check
- **Status:** FIXED - Added `min_observations_for_stats` and `fallback_threshold_abs` config options.
  When fewer than 10 observations exist, uses absolute threshold on raw score instead of z-score.
  Logs warning when using fallback mode.

### [x] BUG-006: EMA stores smoothed values instead of raw
- **File:** `sentiment.py:162-214`
- **Problem:** Double-smoothed ROC is dampened
- **Impact:** Missing rapid sentiment changes
- **Fix:** Store raw values separately, calculate ROC from smoothed values
- **Status:** FIXED - Added `_historical_raw_scores` dict to store raw scores separately.
  The `_historical_scores` now stores smoothed scores for ROC calculation.
  Both are kept in sync and trimmed to last 100 data points.

### [x] BUG-007: No validation for negative P/E ratios
- **File:** `valuation.py:94-104`
- **Problem:** Loss-making companies produce incorrect metrics
- **Impact:** Misleading valuation scores
- **Fix:** Handle negative/zero P/E properly
- **Status:** FIXED - Added validation for both company and sector PE must be positive.
  Loss-making companies (negative EPS) now receive neutral PE score of 0.0.

### [x] BUG-008: Dividend scale mismatch
- **File:** `valuation.py:106-107`
- **Problem:** Uses absolute diff vs relative percentage
- **Impact:** Dividend contribution is negligible
- **Fix:** Use relative calculation like PE/PB/PEG
- **Status:** FIXED - Changed dividend calculation from absolute difference to relative percentage
  `(company.dividend_yield / sector.dividend_yield) - 1`.
  This ensures consistent scaling across all valuation components.

### [x] BUG-009: Intrinsic value fails for negative earnings
- **File:** `valuation.py:335-336`
- **Problem:** Formula `pe_ratio * eps` produces negative price
- **Impact:** Incorrect intrinsic value for loss-making companies
- **Fix:** Add validation and fallback
- **Status:** FIXED - Added validation for positive company and sector EPS in P/E method.
  For loss-making companies, P/E method is skipped entirely.
  Current price calculation now falls back to P/B ratio when EPS is negative.

### [x] BUG-010: Position dataclass conflicts with common.types.Position
- **File:** `signals.py:70-82`
- **Problem:** Different field names and missing fields
- **Impact:** Requires translation layers
- **Fix:** Use common.types.Position or create adapter
- **Status:** FIXED - Created internal Position dataclass with to_common_position() method for conversion to common.types.Position

### [x] BUG-011: TradingSignal uses strings instead of SignalType enum
- **File:** `signals.py:52-68`
- **Problem:** Not compatible with common module
- **Impact:** Signals need translation
- **Fix:** Use SignalType enum from common.types
- **Status:** FIXED - Internal TradingSignal now uses SignalType enum. Added to_common_signal() method for conversion to common.types.TradingSignal

## Minor Issues

### [x] BUG-012: Magic numbers without documentation
- **File:** `signals.py:131-144`
- **Problem:** Constants 3.5 and 0.5 unexplained
- **Fix:** Move to config or add documentation
- **Status:** FIXED - Added class-level constants `SENTIMENT_MAX_SCALE` (3.5) and `VALUATION_MAX_CAP` (0.5)
  with detailed docstrings explaining their purpose in the signal strength calculation.

### [x] BUG-013: Config load mismatch with config.json
- **File:** `valuation.py:350-365`
- **Problem:** Expects flat dict, config has nested structure
- **Fix:** Parse nested structure correctly
- **Status:** FIXED - Updated load_config() to parse nested JSON structure.
  The function now correctly extracts the "valuation" key and nested "weights" dict.

### [x] BUG-014: No unit tests directory
- **Problem:** No tests exist
- **Fix:** Create tests/ with comprehensive coverage
- **Status:** FIXED - Created `tests/` directory with `test_sentiment.py` containing 30 tests covering:
  - SentimentSource validation (confidence must be 0-1)
  - SentimentAnalyzer basic functionality (normalization, scoring, smoothing, interpretation)
  - Edge cases (empty data, single source, unknown sources, no historical data)
  - SentimentConfig defaults and validation
  - SentimentResult creation

### [x] BUG-015: Missing confidence validation
- **File:** `sentiment.py:41-50`
- **Problem:** No validation confidence is [0, 1]
- **Fix:** Add __post_init__ validation
- **Status:** FIXED - Added `__post_init__` method to SentimentSource dataclass that validates
  confidence is in the range [0, 1]. Raises ValueError if confidence is outside this range.

### [x] BUG-016: No thread safety for historical scores
- **File:** `sentiment.py:81-82`
- **Problem:** No locking for concurrent access
- **Fix:** Add threading.Lock or document single-threaded only
- **Status:** FIXED - Added `threading.Lock` to SentimentAnalyzer class. The lock (`_lock`) is used
  in `smooth_score()`, `calculate_roc()`, `get_historical_scores()`, `calculate_sentiment_stats()`,
  and `is_sentiment_extreme()` to protect concurrent access to `_historical_scores`,
  `_historical_raw_scores`, and `_historical_timestamps` dictionaries.

### [x] BUG-017: No persistence mechanism for state
- **File:** `signals.py:112-114`
- **Problem:** State lost on restart
- **Fix:** Add save/load methods
- **Status:** FIXED - Added `save_state(filepath)` and `load_state(filepath)` methods to
  SignalGenerator class. These methods use the existing `get_state()` and `set_state()` methods
  to serialize/deserialize internal state as JSON to/from a file.

### [x] BUG-018: Silent skipping of stocks without sector data
- **File:** `valuation.py:236-238`
- **Problem:** No warning when stocks skipped
- **Fix:** Add logging
- **Status:** FIXED - Added logging to batch_calculate() method.
  Individual warnings are logged for each skipped symbol, and a summary warning is logged at the end.

### [x] BUG-019: Zero std dev produces huge z-scores
- **File:** `sentiment.py:356-409`
- **Problem:** Magic epsilon 1e-8, no documentation
- **Impact:** Unreliable extreme sentiment detection when variance is low
- **Fix:** Added `MIN_STD_FOR_ZSCORE = 0.01` threshold with proper handling
- **Status:** FIXED - When std dev is below 0.01, z-score is set to 0.0 (neutral).
  Logs a warning when this occurs. The behavior is documented in code comments.

### [x] BUG-020: Missing __all__ exports consistency
- **File:** `__init__.py:47-69`
- **Problem:** load_config functions exported but don't work
- **Fix:** Fix or remove exports
- **Status:** FIXED - Updated load_config functions in sentiment.py and signals.py to correctly
  parse the nested config.json structure (matching the pattern used in valuation.py BUG-013 fix).
  All exported items in __all__ now work correctly with the actual config.json file.

## Progress Tracking

| Category | Total | Fixed | Remaining |
|----------|-------|-------|-----------|
| Critical | 4 | 4 | 0 |
| Major | 7 | 7 | 0 |
| Minor | 9 | 9 | 0 |
| **Total** | **20** | **20** | **0** |

## Test Coverage Goals
- [x] Unit tests for sentiment.py (all functions)
- [ ] Unit tests for valuation.py (all functions)
- [ ] Unit tests for signals.py (all functions)
- [ ] Integration tests with common module
- [x] Edge case tests (empty data, negative values, etc.)
- [ ] Live trading simulation tests
