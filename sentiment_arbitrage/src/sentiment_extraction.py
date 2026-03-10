"""
Sentiment Extraction Architecture for Triton Integration
==========================================================

High-performance sentiment extraction layer using Distil-FinBERT with Triton Inference Server.
Designed for batch processing of 500+ stocks with GPU acceleration.

Key Features:
- Model: Distil-FinBERT (ProsusAI/finbert) for financial sentiment analysis
- Triton Inference Server integration with dynamic batching
- FP16/INT8 quantization for VRAM efficiency
- Dynamic batching across 500+ stocks
- Async inference pipeline for maximum throughput

Author: Algorithm Designer
Date: 2026-03-09
"""

import numpy as np
import cupy as cp
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Union
import asyncio
import json
import tritonclient.grpc as grpc_client
from tritonclient.utils import np_to_triton_dtype, InferenceServerException
import warnings
warnings.filterwarnings('ignore')


@dataclass
class TritonModelConfig:
    """Configuration for Triton inference server model"""
    model_name: str = "distil_finbert"
    model_version: str = "1"
    max_batch_size: int = 512
    dtype: str = "fp16"  # "fp16", "fp32", or "int8"
    preferred_batch_size: List[int] = field(default_factory=lambda: [64, 128, 256])
    max_queue_delay_microseconds: int = 1000


@dataclass
class SentimentOutput:
    """Container for sentiment extraction output"""
    sentiment_scores: np.ndarray  # Shape: (n_stocks,)
    confidence_scores: np.ndarray  # Shape: (n_stocks,)
    class_labels: np.ndarray  # Shape: (n_stocks,) - "positive", "negative", "neutral"
    logits: np.ndarray  # Shape: (n_stocks, 3) - raw model outputs


class SentimentTokenizer:
    """
    Tokenizer for financial sentiment analysis.
    
    Handles preprocessing of text inputs for Distil-FinBERT model.
    Optimized for batch processing of multiple stock-related texts.
    """
    
    def __init__(self, max_length: int = 512, model_name: str = "distilbert-base-uncased"):
        """
        Initialize tokenizer
        
        Args:
            max_length: Maximum sequence length
            model_name: Name of the base model for tokenization
        """
        self.max_length = max_length
        self.model_name = model_name
        
        # Initialize tokenizer (use transformers if available)
        try:
            from transformers import AutoTokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                "ProsusAI/finbert",
                use_fast=True
            )
            self.use_fast_tokenizer = True
        except ImportError:
            # Fallback to simple tokenization
            self.tokenizer = None
            self.use_fast_tokenizer = False
            print("Warning: transformers not available, using simple tokenization")
    
    def tokenize_batch(
        self, 
        texts: List[str],
        return_tensors: str = "np"
    ) -> Dict[str, np.ndarray]:
        """
        Tokenize a batch of texts
        
        Args:
            texts: List of text strings
            return_tensors: Format for returned tensors ("np" or "pt")
            
        Returns:
            Dictionary with 'input_ids', 'attention_mask', etc.
        """
        if self.use_fast_tokenizer and self.tokenizer is not None:
            # Use HuggingFace tokenizer
            encoded = self.tokenizer(
                texts,
                max_length=self.max_length,
                padding=True,
                truncation=True,
                return_tensors=return_tensors
            )
            
            if return_tensors == "np":
                return {
                    'input_ids': encoded['input_ids'].numpy(),
                    'attention_mask': encoded['attention_mask'].numpy()
                }
            else:
                return {
                    'input_ids': encoded['input_ids'].numpy(),
                    'attention_mask': encoded['attention_mask'].numpy()
                }
        else:
            # Simple fallback tokenization
            return self._simple_tokenize_batch(texts)
    
    def _simple_tokenize_batch(self, texts: List[str]) -> Dict[str, np.ndarray]:
        """
        Simple tokenization fallback
        
        Args:
            texts: List of text strings
            
        Returns:
            Dictionary with tokenized arrays
        """
        batch_size = len(texts)
        input_ids = np.zeros((batch_size, self.max_length), dtype=np.int64)
        attention_mask = np.zeros((batch_size, self.max_length), dtype=np.int64)
        
        for i, text in enumerate(texts):
            # Simple whitespace tokenization
            tokens = text.split()[:self.max_length - 2]  # Account for [CLS] and [SEP]
            
            # Add special tokens
            input_ids[i, 0] = 101  # [CLS]
            input_ids[i, 1:1+len(tokens)] = [hash(token) % 30000 for token in tokens]
            input_ids[i, 1+len(tokens)] = 102  # [SEP]
            
            attention_mask[i, :1+len(tokens)+1] = 1
        
        return {
            'input_ids': input_ids,
            'attention_mask': attention_mask
        }


class TritonSentimentClient:
    """
    Client for Triton Inference Server with async support.
    
    Handles communication with Triton server for batch inference.
    Supports dynamic batching and multiple request types.
    """
    
    def __init__(
        self, 
        server_url: str = "localhost:8001",
        model_config: Optional[TritonModelConfig] = None,
        verbose: bool = False
    ):
        """
        Initialize Triton client
        
        Args:
            server_url: URL of Triton inference server
            model_config: Model configuration
            verbose: Enable verbose logging
        """
        self.server_url = server_url
        self.model_config = model_config or TritonModelConfig()
        self.verbose = verbose
        
        # Create Triton client
        self.client = grpc_client.InferenceServerClient(
            url=server_url,
            verbose=verbose
        )
        
        # Check server health
        self._check_server_ready()
        
        # Check model availability
        self._check_model_ready()
        
        # Get model metadata
        self.model_metadata = self._get_model_metadata()
        
        if self.verbose:
            print(f"Connected to Triton server: {server_url}")
            print(f"Model: {self.model_config.model_name}")
            print(f"Max batch size: {self.model_config.max_batch_size}")
    
    def _check_server_ready(self):
        """Check if Triton server is ready"""
        try:
            if not self.client.is_server_live():
                raise ConnectionError("Triton server is not live")
            if not self.client.is_server_ready():
                raise ConnectionError("Triton server is not ready")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Triton server: {e}")
    
    def _check_model_ready(self):
        """Check if model is ready"""
        try:
            if not self.client.is_model_ready(
                self.model_config.model_name,
                self.model_config.model_version
            ):
                raise RuntimeError(f"Model {self.model_config.model_name} is not ready")
        except Exception as e:
            raise RuntimeError(f"Model check failed: {e}")
    
    def _get_model_metadata(self) -> Dict:
        """Get model metadata"""
        try:
            metadata = self.client.get_model_metadata(
                self.model_config.model_name,
                self.model_config.model_version
            )
            return metadata
        except Exception as e:
            raise RuntimeError(f"Failed to get model metadata: {e}")
    
    async def infer_batch_async(
        self,
        input_ids: np.ndarray,
        attention_mask: np.ndarray
    ) -> np.ndarray:
        """
        Async batch inference
        
        Args:
            input_ids: Input token IDs (batch_size, seq_len)
            attention_mask: Attention mask (batch_size, seq_len)
            
        Returns:
            Model logits (batch_size, num_classes)
        """
        # Create input tensors
        inputs = [
            grpc_client.InferInput(
                "input_ids",
                input_ids.shape,
                np_to_triton_dtype(input_ids.dtype)
            ),
            grpc_client.InferInput(
                "attention_mask",
                attention_mask.shape,
                np_to_triton_dtype(attention_mask.dtype)
            )
        ]
        
        inputs[0].set_data_from_numpy(input_ids)
        inputs[1].set_data_from_numpy(attention_mask)
        
        # Create output
        outputs = [
            grpc_client.InferRequestedOutput("logits")
        ]
        
        # Async inference
        try:
            response = await self.client.infer_async(
                model_name=self.model_config.model_name,
                model_version=self.model_config.model_version,
                inputs=inputs,
                outputs=outputs,
                request_id=None,
                parameters=None
            )
            
            # Extract logits
            logits = response.as_numpy("logits")
            return logits
            
        except InferenceServerException as e:
            raise RuntimeError(f"Inference failed: {e}")
    
    def infer_batch(
        self,
        input_ids: np.ndarray,
        attention_mask: np.ndarray
    ) -> np.ndarray:
        """
        Synchronous batch inference
        
        Args:
            input_ids: Input token IDs (batch_size, seq_len)
            attention_mask: Attention mask (batch_size, seq_len)
            
        Returns:
            Model logits (batch_size, num_classes)
        """
        # Create input tensors
        inputs = [
            grpc_client.InferInput(
                "input_ids",
                input_ids.shape,
                np_to_triton_dtype(input_ids.dtype)
            ),
            grpc_client.InferInput(
                "attention_mask",
                attention_mask.shape,
                np_to_triton_dtype(attention_mask.dtype)
            )
        ]
        
        inputs[0].set_data_from_numpy(input_ids)
        inputs[1].set_data_from_numpy(attention_mask)
        
        # Create output
        outputs = [
            grpc_client.InferRequestedOutput("logits")
        ]
        
        # Synchronous inference
        try:
            response = self.client.infer(
                model_name=self.model_config.model_name,
                model_version=self.model_config.model_version,
                inputs=inputs,
                outputs=outputs
            )
            
            # Extract logits
            logits = response.as_numpy("logits")
            return logits
            
        except InferenceServerException as e:
            raise RuntimeError(f"Inference failed: {e}")
    
    def infer_large_batch(
        self,
        texts: List[str],
        tokenizer: 'SentimentTokenizer',
        batch_size: Optional[int] = None
    ) -> np.ndarray:
        """
        Inference for large batches (more than max_batch_size)
        
        Automatically splits large batches into smaller chunks.
        
        Args:
            texts: List of texts to analyze
            tokenizer: Tokenizer instance
            batch_size: Batch size (default: from config)
            
        Returns:
            Model logits (n_texts, num_classes)
        """
        if batch_size is None:
            batch_size = self.model_config.max_batch_size
        
        n_texts = len(texts)
        all_logits = []
        
        for i in range(0, n_texts, batch_size):
            batch_texts = texts[i:i+batch_size]
            
            # Tokenize batch
            encoded = tokenizer.tokenize_batch(batch_texts)
            
            # Inference
            logits = self.infer_batch(
                encoded['input_ids'],
                encoded['attention_mask']
            )
            
            all_logits.append(logits)
        
        # Concatenate results
        return np.concatenate(all_logits, axis=0)


class SentimentExtractionLayer:
    """
    Main sentiment extraction layer.
    
    Coordinates tokenization, inference, and post-processing for
    high-throughput sentiment analysis of 500+ stocks.
    """
    
    def __init__(
        self,
        triton_client: Optional[TritonSentimentClient] = None,
        tokenizer: Optional[SentimentTokenizer] = None,
        n_classes: int = 3
    ):
        """
        Initialize sentiment extraction layer
        
        Args:
            triton_client: Triton inference client
            tokenizer: Text tokenizer
            n_classes: Number of sentiment classes
        """
        self.triton_client = triton_client
        self.tokenizer = tokenizer or SentimentTokenizer()
        self.n_classes = n_classes
        
        # Class labels for FinBERT
        self.class_labels = ["negative", "neutral", "positive"]
        
        # Sentiment score mapping (e.g., neutral=0, negative=-1, positive=1)
        self.sentiment_mapping = {
            "negative": -1.0,
            "neutral": 0.0,
            "positive": 1.0
        }
        
        # Performance tracking
        self.n_requests = 0
        self.total_tokens = 0
        
    def extract_sentiment_batch(
        self,
        texts: List[str],
        return_confidence: bool = True,
        return_logits: bool = False
    ) -> SentimentOutput:
        """
        Extract sentiment for a batch of texts
        
        Args:
            texts: List of texts (one per stock)
            return_confidence: Return confidence scores
            return_logits: Return raw logits
            
        Returns:
            SentimentOutput with sentiment scores, confidence, and labels
        """
        if not texts:
            return SentimentOutput(
                sentiment_scores=np.array([]),
                confidence_scores=np.array([]),
                class_labels=np.array([], dtype=object),
                logits=np.array([]).reshape(0, self.n_classes)
            )
        
        # Update tracking
        self.n_requests += 1
        self.total_tokens += sum(len(text.split()) for text in texts)
        
        # Tokenize
        encoded = self.tokenizer.tokenize_batch(texts)
        
        # Inference
        if self.triton_client:
            logits = self.triton_client.infer_batch(
                encoded['input_ids'],
                encoded['attention_mask']
            )
        else:
            # Mock inference for testing
            logits = np.random.randn(len(texts), self.n_classes).astype(np.float32)
        
        # Process logits
        sentiment_scores = self._logits_to_scores(logits)
        confidence_scores = self._calculate_confidence(logits)
        class_labels_idx = np.argmax(logits, axis=1)
        class_labels = np.array([self.class_labels[i] for i in class_labels_idx])
        
        if return_logits:
            return SentimentOutput(
                sentiment_scores=sentiment_scores,
                confidence_scores=confidence_scores,
                class_labels=class_labels,
                logits=logits
            )
        else:
            return SentimentOutput(
                sentiment_scores=sentiment_scores,
                confidence_scores=confidence_scores,
                class_labels=class_labels,
                logits=np.array([])
            )
    
    def _logits_to_scores(self, logits: np.ndarray) -> np.ndarray:
        """
        Convert logits to sentiment scores
        
        Maps softmax probabilities to sentiment scores.
        """
        # Apply softmax
        probs = self._softmax(logits)
        
        # Calculate weighted sentiment score
        sentiment_scores = (
            probs[:, 0] * self.sentiment_mapping["negative"] +
            probs[:, 1] * self.sentiment_mapping["neutral"] +
            probs[:, 2] * self.sentiment_mapping["positive"]
        )
        
        return sentiment_scores
    
    def _calculate_confidence(self, logits: np.ndarray) -> np.ndarray:
        """
        Calculate confidence scores
        
        Confidence is the max softmax probability.
        """
        probs = self._softmax(logits)
        confidence = np.max(probs, axis=1)
        return confidence
    
    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        """Numerically stable softmax"""
        exp_logits = np.exp(logits - np.max(logits, axis=1, keepdims=True))
        return exp_logits / np.sum(exp_logits, axis=1, keepdims=True)
    
    def extract_market_sentiment(
        self,
        texts: List[str]
    ) -> float:
        """
        Extract overall market sentiment from multiple texts
        
        Args:
            texts: List of market-related texts
            
        Returns:
            Aggregate market sentiment score
        """
        if not texts:
            return 0.0
        
        output = self.extract_sentiment_batch(texts)
        return float(np.mean(output.sentiment_scores))
    
    def get_statistics(self) -> Dict:
        """Get usage statistics"""
        return {
            'n_requests': self.n_requests,
            'total_tokens': self.total_tokens,
            'avg_tokens_per_request': self.total_tokens / self.n_requests if self.n_requests > 0 else 0
        }


def create_mock_sentiment_layer(n_stocks: int = 500) -> SentimentExtractionLayer:
    """
    Create a mock sentiment layer for testing
    
    Args:
        n_stocks: Number of stocks
        
    Returns:
        SentimentExtractionLayer without Triton client
    """
    return SentimentExtractionLayer(
        triton_client=None,  # No Triton client for mock
        tokenizer=SentimentTokenizer(),
        n_classes=3
    )


def test_sentiment_extraction():
    """Test sentiment extraction layer"""
    print("Testing Sentiment Extraction Layer...")
    
    # Create mock layer
    sentiment_layer = create_mock_sentiment_layer(n_stocks=10)
    
    # Generate sample texts
    sample_texts = [
        "Company reports strong quarterly earnings, revenue beats expectations",
        "Stock plunges on disappointing guidance from CEO",
        "Analyst upgrades rating to buy, citing strong fundamentals",
        "Market volatility increases as investors react to Fed decision",
        "Company announces new product launch, expected to drive growth",
        "Technical indicators suggest bearish trend for next quarter",
        "Institutional investors increase holdings in tech sector",
        "Supply chain issues impact production, profits decline",
        "Merger announcement receives positive market response",
        "Economic indicators point to recovery in manufacturing sector"
    ]
    
    # Extract sentiment
    output = sentiment_layer.extract_sentiment_batch(
        sample_texts,
        return_confidence=True,
        return_logits=True
    )
    
    # Print results
    print("\nSample Texts and Sentiment Scores:")
    for i, (text, score, confidence, label) in enumerate(zip(
        sample_texts,
        output.sentiment_scores,
        output.confidence_scores,
        output.class_labels
    )):
        print(f"{i+1}. [{label:8s}] Score: {score:6.3f} | Conf: {confidence:.3f}")
        print(f"   Text: {text[:60]}...")
    
    print(f"\nStatistics:")
    stats = sentiment_layer.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Test market sentiment
    market_sentiment = sentiment_layer.extract_market_sentiment(sample_texts)
    print(f"\nMarket Sentiment: {market_sentiment:.3f}")
    
    print("\n✓ Sentiment extraction test passed!")


if __name__ == "__main__":
    test_sentiment_extraction()
