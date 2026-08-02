"""DEPRECATED: 请使用模块化导入
from gotchas.retriever import GotchasHybrid, GotchasBM25
"""
from .searcher import GotchasBM25, GotchasHybrid
from .tokenizer import ChineseTokenizer
from .bm25 import BM25
from .tfidf import TFIDFVector
from .reranker import FeatureReranker
