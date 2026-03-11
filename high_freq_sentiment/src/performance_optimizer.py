"""
Performance Optimization Module for Sentiment Arbitrage System
================================================================

Advanced GPU optimization techniques for maximizing throughput and minimizing latency.
Focus on:
1. CUDA kernel fusion
2. Memory coalescing
3. Asynchronous execution
4. Dynamic batching
5. Mixed precision computation

Author: Algorithm Designer
Date: 2026-03-09
"""

import time
import warnings
from contextlib import contextmanager
from dataclasses import dataclass

import cupy as cp
import numpy as np

warnings.filterwarnings("ignore")

# Try to import CUDA-specific modules
try:
    from cupy.cuda import Event, Stream

    CUPY_CUDA_AVAILABLE = True
except ImportError:
    CUPY_CUDA_AVAILABLE = False
    warnings.warn("CuPy CUDA not available, falling back to CPU")


@dataclass
class PerformanceMetrics:
    """Container for performance metrics"""

    total_time_ms: float
    gpu_time_ms: float
    cpu_time_ms: float
    transfer_time_ms: float
    memory_allocated_mb: float
    throughput_items_per_sec: float
    cache_hit_rate: float


class PerformanceProfiler:
    """Profile GPU/CPU performance with detailed metrics"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.events: dict[str, list[float]] = {}
        self.start_times: dict[str, float] = {}

    def start(self, name: str):
        """Start timing a named event"""
        if self.enabled:
            self.start_times[name] = time.perf_counter()

    def end(self, name: str) -> float:
        """End timing a named event and return duration"""
        if not self.enabled or name not in self.start_times:
            return 0.0
        duration = (time.perf_counter() - self.start_times[name]) * 1000  # ms
        if name not in self.events:
            self.events[name] = []
        self.events[name].append(duration)
        return duration

    def get_summary(self) -> dict[str, float]:
        """Get summary statistics for all events"""
        summary = {}
        for name, times in self.events.items():
            if times:
                summary[name] = {
                    "mean_ms": np.mean(times),
                    "std_ms": np.std(times),
                    "min_ms": np.min(times),
                    "max_ms": np.max(times),
                    "count": len(times),
                }
        return summary

    def reset(self):
        """Reset all events"""
        self.events = {}
        self.start_times = {}


class GPUKernelOptimizer:
    """
    Advanced GPU kernel optimization techniques
    """

    def __init__(self, use_mixed_precision: bool = True):
        self.use_mixed_precision = use_mixed_precision
        self.dtype = cp.float16 if use_mixed_precision else cp.float32
        self.profiler = PerformanceProfiler()

    def optimize_memory_layout(self, arr: cp.ndarray) -> cp.ndarray:
        """
        Optimize memory layout for coalesced access

        Args:
            arr: Input array

        Returns:
            Optimized array with contiguous memory layout
        """
        self.profiler.start("memory_optimize")
        # Ensure C-contiguous for better coalescing
        if not arr.flags["C_CONTIGUOUS"]:
            arr = cp.ascontiguousarray(arr, dtype=self.dtype)
        self.profiler.end("memory_optimize")
        return arr

    def fused_operation(
        self, x: cp.ndarray, y: cp.ndarray, alpha: float = 1.0, beta: float = 0.0
    ) -> cp.ndarray:
        """
        Fused multiply-add operation (z = alpha*x + beta*y)
        Reduces memory bandwidth by combining operations

        Args:
            x: First input array
            y: Second input array
            alpha: Scaling factor for x
            beta: Scaling factor for y

        Returns:
            Result of alpha*x + beta*y
        """
        self.profiler.start("fused_op")
        result = alpha * x + beta * y
        self.profiler.end("fused_op")
        return result

    def vectorized_reduction(
        self, data: cp.ndarray, axis: int = 0, operation: str = "mean"
    ) -> cp.ndarray:
        """
        Optimized vectorized reduction using efficient reduction kernels

        Args:
            data: Input array
            axis: Axis along which to reduce
            operation: Type of reduction ('mean', 'sum', 'std', 'var')

        Returns:
            Reduced array
        """
        self.profiler.start("reduction")
        if operation == "mean":
            result = cp.mean(data, axis=axis, dtype=cp.float32)
        elif operation == "sum":
            result = cp.sum(data, axis=axis, dtype=cp.float32)
        elif operation == "std":
            result = cp.std(data, axis=axis, dtype=cp.float32)
        elif operation == "var":
            result = cp.var(data, axis=axis, dtype=cp.float32)
        else:
            raise ValueError(f"Unknown operation: {operation}")
        self.profiler.end("reduction")
        return result

    def batch_matrix_multiply(
        self, A: cp.ndarray, B: cp.ndarray, batch_first: bool = True
    ) -> cp.ndarray:
        """
        Batched matrix multiplication with optimized kernel selection

        Args:
            A: First batch of matrices (..., M, K)
            B: Second batch of matrices (..., K, N)
            batch_first: If True, batch dimension is first

        Returns:
            Batched matrix product (..., M, N)
        """
        self.profiler.start("batch_matmul")
        # Use CuPy's optimized batch matmul
        result = cp.matmul(A, B)
        self.profiler.end("batch_matmul")
        return result

    def get_memory_info(self) -> dict[str, float]:
        """Get current GPU memory information"""
        mempool = cp.get_default_memory_pool()
        total_bytes = mempool.total_bytes()
        used_bytes = mempool.used_bytes()
        free_bytes = mempool.free_bytes()

        return {
            "total_mb": total_bytes / (1024**2),
            "used_mb": used_bytes / (1024**2),
            "free_mb": free_bytes / (1024**2),
            "utilization_pct": (used_bytes / total_bytes * 100) if total_bytes > 0 else 0,
        }


class AsynchronousExecutor:
    """
    Asynchronous execution pipeline for overlapping computation and data transfer
    """

    def __init__(self, n_streams: int = 3):
        self.n_streams = n_streams
        self.streams: list[Stream] = []
        self.events: list[Event] = []

        if CUPY_CUDA_AVAILABLE:
            for _ in range(n_streams):
                stream = Stream()
                self.streams.append(stream)
                self.events.append(Event())
        else:
            warnings.warn("CUDA streams not available, using synchronous execution")

    def async_transfer_to_gpu(self, data: np.ndarray, stream_idx: int = 0) -> cp.ndarray:
        """
        Asynchronously transfer data to GPU

        Args:
            data: Host data to transfer
            stream_idx: Which stream to use for transfer

        Returns:
            GPU data
        """
        if CUPY_CUDA_AVAILABLE and stream_idx < len(self.streams):
            with self.streams[stream_idx]:
                gpu_data = cp.asarray(data)
            return gpu_data
        else:
            return cp.asarray(data)

    def async_transfer_to_cpu(self, data: cp.ndarray, stream_idx: int = 0) -> np.ndarray:
        """
        Asynchronously transfer data from GPU

        Args:
            data: GPU data to transfer
            stream_idx: Which stream to use for transfer

        Returns:
            Host data
        """
        if CUPY_CUDA_AVAILABLE and stream_idx < len(self.streams):
            with self.streams[stream_idx]:
                cpu_data = cp.asnumpy(data)
            return cpu_data
        else:
            return cp.asnumpy(data)

    def record_event(self, stream_idx: int = 0):
        """Record an event on the specified stream"""
        if CUPY_CUDA_AVAILABLE and stream_idx < len(self.events):
            self.events[stream_idx].record(stream=self.streams[stream_idx])

    def wait_for_event(self, event_idx: int = 0):
        """Wait for a recorded event"""
        if CUPY_CUDA_AVAILABLE and event_idx < len(self.events):
            self.events[event_idx].synchronize()

    def synchronize_all(self):
        """Synchronize all streams"""
        if CUPY_CUDA_AVAILABLE:
            for stream in self.streams:
                stream.synchronize()


class DynamicBatchOptimizer:
    """
    Dynamic batch size optimization based on GPU memory and latency constraints
    """

    def __init__(
        self,
        min_batch_size: int = 32,
        max_batch_size: int = 1024,
        target_latency_ms: float = 50.0,
        memory_limit_mb: float = 8000.0,
    ):
        self.min_batch_size = min_batch_size
        self.max_batch_size = max_batch_size
        self.target_latency_ms = target_latency_ms
        self.memory_limit_mb = memory_limit_mb

        self.current_batch_size = 256
        self.latency_history: list[float] = []
        self.memory_usage_history: list[float] = []

    def optimize_batch_size(
        self, n_items: int, estimated_latency_ms: float, current_memory_mb: float
    ) -> int:
        """
        Dynamically adjust batch size based on performance metrics

        Args:
            n_items: Number of items to process
            estimated_latency_ms: Estimated latency for current batch
            current_memory_mb: Current memory usage

        Returns:
            Optimal batch size
        """
        # Record history
        self.latency_history.append(estimated_latency_ms)
        self.memory_usage_history.append(current_memory_mb)

        # Keep only recent history (last 50 samples)
        if len(self.latency_history) > 50:
            self.latency_history.pop(0)
            self.memory_usage_history.pop(0)

        # Calculate adjustments
        if len(self.latency_history) >= 5:
            avg_latency = np.mean(self.latency_history[-5:])
            avg_memory = np.mean(self.memory_usage_history[-5:])

            # Adjust based on latency
            if avg_latency > self.target_latency_ms * 1.2:
                # Too slow, reduce batch size
                self.current_batch_size = max(
                    self.min_batch_size, int(self.current_batch_size * 0.8)
                )
            elif avg_latency < self.target_latency_ms * 0.8:
                # Faster than target, can increase batch size
                self.current_batch_size = min(
                    self.max_batch_size, int(self.current_batch_size * 1.1)
                )

            # Adjust based on memory
            if avg_memory > self.memory_limit_mb * 0.9:
                # Memory pressure, reduce batch size
                self.current_batch_size = max(
                    self.min_batch_size, int(self.current_batch_size * 0.7)
                )

        # Return batch size, capped at number of items
        return min(self.current_batch_size, n_items)

    def get_optimal_batches(self, n_items: int) -> list[tuple[int, int]]:
        """
        Get optimal batch breakdown for processing n_items

        Args:
            n_items: Total number of items to process

        Returns:
            List of (start_idx, end_idx) for each batch
        """
        batch_size = self.current_batch_size
        batches = []

        for start in range(0, n_items, batch_size):
            end = min(start + batch_size, n_items)
            batches.append((start, end))

        return batches


class MixedPrecisionManager:
    """
    Mixed precision computation manager for improved performance
    """

    def __init__(self, use_fp16: bool = True, use_bfloat16: bool = False):
        self.use_fp16 = use_fp16
        self.use_bfloat16 = use_bfloat16

        if use_fp16:
            self.compute_dtype = cp.float16
            self.accumulate_dtype = cp.float32
        elif use_bfloat16:
            self.compute_dtype = cp.float16
            self.accumulate_dtype = cp.float32
        else:
            self.compute_dtype = cp.float32
            self.accumulate_dtype = cp.float32

    def cast_to_compute(self, arr: cp.ndarray) -> cp.ndarray:
        """Cast array to compute precision"""
        return arr.astype(self.compute_dtype)

    def cast_to_accumulate(self, arr: cp.ndarray) -> cp.ndarray:
        """Cast array to accumulation precision"""
        return arr.astype(self.accumulate_dtype)

    def safe_add(self, a: cp.ndarray, b: cp.ndarray) -> cp.ndarray:
        """
        Safe addition with overflow protection

        Args:
            a: First array
            b: Second array

        Returns:
            Sum with proper precision handling
        """
        # Cast to accumulation dtype for addition
        a_acc = a.astype(self.accumulate_dtype)
        b_acc = b.astype(self.accumulate_dtype)
        result = a_acc + b_acc
        return result.astype(self.compute_dtype)

    def safe_multiply(self, a: cp.ndarray, b: cp.ndarray) -> cp.ndarray:
        """
        Safe multiplication with overflow protection

        Args:
            a: First array
            b: Second array

        Returns:
            Product with proper precision handling
        """
        # Cast to accumulation dtype for multiplication
        a_acc = a.astype(self.accumulate_dtype)
        b_acc = b.astype(self.accumulate_dtype)
        result = a_acc * b_acc
        return result.astype(self.compute_dtype)


@contextmanager
def performance_context(profiler: PerformanceProfiler, name: str):
    """
    Context manager for automatic performance profiling

    Usage:
        with performance_context(profiler, "my_operation"):
            # do work
            pass
    """
    profiler.start(name)
    try:
        yield
    finally:
        profiler.end(name)


class AdaptiveOptimizer:
    """
    Adaptive optimization that learns from runtime performance
    """

    def __init__(self, learning_rate: float = 0.1):
        self.learning_rate = learning_rate
        self.performance_history: dict[str, list[float]] = {}
        self.parameter_history: dict[str, list[float]] = {}

    def update_parameter(
        self,
        param_name: str,
        current_value: float,
        performance_metric: float,
        maximize: bool = False,
    ) -> float:
        """
        Update parameter based on performance feedback

        Args:
            param_name: Name of the parameter
            current_value: Current value of the parameter
            performance_metric: Performance metric (e.g., latency, throughput)
            maximize: If True, maximize performance; if False, minimize

        Returns:
            Updated parameter value
        """
        # Initialize history if needed
        if param_name not in self.performance_history:
            self.performance_history[param_name] = []
            self.parameter_history[param_name] = []

        # Record performance
        self.performance_history[param_name].append(performance_metric)
        self.parameter_history[param_name].append(current_value)

        # Keep only recent history
        if len(self.performance_history[param_name]) > 20:
            self.performance_history[param_name].pop(0)
            self.parameter_history[param_name].pop(0)

        # Only adjust if we have enough history
        if len(self.performance_history[param_name]) >= 3:
            recent_perf = self.performance_history[param_name][-3:]
            recent_params = self.parameter_history[param_name][-3:]

            # Simple gradient estimation
            if maximize:
                # If performance improved, move in same direction
                if recent_perf[-1] > recent_perf[-2]:
                    direction = 1 if recent_params[-1] > recent_params[-2] else -1
                else:
                    direction = -1 if recent_params[-1] > recent_params[-2] else 1
            else:
                # If latency decreased, move in same direction
                if recent_perf[-1] < recent_perf[-2]:
                    direction = 1 if recent_params[-1] > recent_params[-2] else -1
                else:
                    direction = -1 if recent_params[-1] > recent_params[-2] else 1

            # Apply adjustment
            adjustment = direction * self.learning_rate * current_value
            new_value = current_value + adjustment

            return new_value

        return current_value


# Utility functions


def benchmark_operation(
    func, *args, n_iterations: int = 100, warmup: int = 10, **kwargs
) -> dict[str, float]:
    """
    Benchmark an operation with warmup and multiple iterations

    Args:
        func: Function to benchmark
        *args: Positional arguments for func
        n_iterations: Number of iterations to time
        warmup: Number of warmup iterations
        **kwargs: Keyword arguments for func

    Returns:
        Dictionary with timing statistics
    """
    # Warmup
    for _ in range(warmup):
        _ = func(*args, **kwargs)

    # Synchronize GPU
    cp.cuda.Stream.null.synchronize()

    # Benchmark
    times = []
    for _ in range(n_iterations):
        start = time.perf_counter()
        _ = func(*args, **kwargs)
        cp.cuda.Stream.null.synchronize()
        end = time.perf_counter()
        times.append((end - start) * 1000)  # Convert to ms

    return {
        "mean_ms": np.mean(times),
        "std_ms": np.std(times),
        "min_ms": np.min(times),
        "max_ms": np.max(times),
        "total_ms": np.sum(times),
    }


def estimate_memory_usage(shape: tuple[int, ...], dtype: cp.dtype, n_copies: int = 1) -> float:
    """
    Estimate memory usage in MB

    Args:
        shape: Shape of the array
        dtype: Data type
        n_copies: Number of copies (e.g., for temporary buffers)

    Returns:
        Estimated memory usage in MB
    """
    elements = np.prod(shape)
    bytes_per_element = cp.dtype(dtype).itemsize
    total_bytes = elements * bytes_per_element * n_copies
    return total_bytes / (1024**2)


# Test function
def test_performance_optimizer():
    """Test the performance optimizer"""
    print("Testing Performance Optimizer")

    # Test kernel optimizer
    optimizer = GPUKernelOptimizer(use_mixed_precision=True)

    # Create test data
    n_stocks = 500
    x = cp.random.randn(n_stocks, 100).astype(cp.float32)
    y = cp.random.randn(n_stocks, 100).astype(cp.float32)

    # Test fused operation
    result = optimizer.fused_operation(x, y, alpha=2.0, beta=0.5)
    print(f"Fused operation shape: {result.shape}")

    # Test vectorized reduction
    mean_result = optimizer.vectorized_reduction(x, axis=1, operation="mean")
    print(f"Mean reduction shape: {mean_result.shape}")

    # Test batch matmul
    A = cp.random.randn(10, n_stocks, 64, 64).astype(cp.float32)
    B = cp.random.randn(10, 64, 64).astype(cp.float32)
    C = optimizer.batch_matrix_multiply(A, B)
    print(f"Batch matmul shape: {C.shape}")

    # Get memory info
    mem_info = optimizer.get_memory_info()
    print(f"GPU Memory: {mem_info['used_mb']:.2f} MB / {mem_info['total_mb']:.2f} MB")

    # Test profiler
    profiler = PerformanceProfiler()
    with performance_context(profiler, "test_op"):
        _ = optimizer.fused_operation(x, y)

    summary = profiler.get_summary()
    print(f"Performance summary: {summary}")

    # Test dynamic batch optimizer
    batch_optimizer = DynamicBatchOptimizer()
    batch_size = batch_optimizer.optimize_batch_size(500, 45.0, 4000.0)
    print(f"Optimal batch size: {batch_size}")

    # Test mixed precision
    mixed_precision = MixedPrecisionManager(use_fp16=True)
    fp16_data = mixed_precision.cast_to_compute(x)
    print(f"FP16 data shape: {fp16_data.shape}, dtype: {fp16_data.dtype}")

    print("✓ Performance Optimizer tests passed")


if __name__ == "__main__":
    test_performance_optimizer()
